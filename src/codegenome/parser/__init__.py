"""Tree-sitter based multi-language source parser.

This package parses source files across multiple languages (Python, JS/TS, Go,
Rust) and extracts symbols, imports, function calls, and inheritance. The heavy
per-language extraction logic lives in :mod:`codegenome.parser.languages`; this
module keeps the grammar loading, the extractor registry, and the public
:class:`SourceParser` facade.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from tree_sitter import Language, Node, Parser

from codegenome.parser.languages import go as _go
from codegenome.parser.languages import javascript as _javascript
from codegenome.parser.languages import python as _python
from codegenome.parser.languages import rust as _rust
from codegenome.parser.types import (
    ParsedCall,
    ParsedImport,
    ParsedInheritance,
    ParsedSymbol,
    ParseResult,
)

logger = logging.getLogger(__name__)

__all__ = [
    "EXTENSIONS",
    "ParsedCall",
    "ParsedImport",
    "ParsedInheritance",
    "ParsedSymbol",
    "ParseResult",
    "SourceParser",
]

EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
}

_EXTRACTORS: dict[str, Callable[[bytes, Node, ParseResult], None]] = {
    "python": _python.extract,
    "javascript": lambda s, n, r: _javascript.extract(s, n, r, "javascript"),
    "typescript": lambda s, n, r: _javascript.extract(s, n, r, "typescript"),
    "tsx": lambda s, n, r: _javascript.extract(s, n, r, "tsx"),
    "go": _go.extract,
    "rust": _rust.extract,
}


def _load_languages() -> dict[str, Language]:
    languages: dict[str, Language] = {}
    specs: list[tuple[str, str, str, str]] = [
        ("python", "tree_sitter_python", "language", "python"),
        ("javascript", "tree_sitter_javascript", "language", "javascript"),
        ("typescript", "tree_sitter_typescript", "language_typescript", "typescript"),
        ("tsx", "tree_sitter_typescript", "language_tsx", "tsx"),
        ("go", "tree_sitter_go", "language", "go"),
        ("rust", "tree_sitter_rust", "language", "rust"),
    ]
    for key, module_name, attr_name, lang_name in specs:
        try:
            module = __import__(module_name)
            languages[key] = _build_language(module, attr_name, lang_name)
        except Exception as exc:  # pragma: no cover - optional grammars
            logger.warning("Failed to load tree-sitter grammar %s: %s", key, exc)
    return languages


def _build_language(module: object, attr_name: str, lang_name: str) -> Language:
    """Create a Language object across tree-sitter API variants."""
    language_capsule = getattr(module, attr_name)()
    try:
        return Language(language_capsule, lang_name)
    except TypeError:
        # Newer tree-sitter releases accept only the grammar capsule.
        return Language(language_capsule)


class SourceParser:
    """Parse source files and extract symbols, imports, calls, and inheritance.

    This class manages tree-sitter language parsers and coordinates the
    extraction process for supported languages.
    """

    def __init__(self) -> None:
        """Initialize the SourceParser and load available language grammars."""
        self._languages = _load_languages()
        self._parsers: dict[str, Parser] = {}
        for key, language in self._languages.items():
            try:
                parser = Parser()
                parser.set_language(language)
            except AttributeError:
                parser = Parser(language)
            self._parsers[key] = parser

    def detect_language(self, path: Path | str) -> str | None:
        """Detect the programming language based on file extension.

        Args:
            path (Path | str): File path.

        Returns:
            str | None: The language identifier if detected, else None.
        """
        return EXTENSIONS.get(Path(path).suffix.lower())

    def parse_file(self, path: Path | str, content: bytes | None = None) -> ParseResult | None:
        """Parse a source file and extract structural information.

        Args:
            path (Path | str): Path to the source file.
            content (bytes | None): Optional pre-read bytes content.

        Returns:
            ParseResult | None: The parsed data, or None if language is unsupported.
        """
        file_path = Path(path)
        language = self.detect_language(file_path)
        if language is None:
            return None

        if content is None:
            try:
                content = file_path.read_bytes()
            except OSError as exc:
                result = ParseResult(path=str(file_path), language=language)
                result.errors.append(str(exc))
                logger.warning("Failed to read %s: %s", file_path, exc)
                return result

        return self.parse_bytes(content, language, str(file_path))

    def parse_bytes(self, content: bytes, language: str, path: str = "<string>") -> ParseResult:
        """Parse raw bytes content for a specific language.

        Args:
            content (bytes): Source code bytes.
            language (str): Target language identifier.
            path (str): File path for reference in the result. Defaults to "<string>".

        Returns:
            ParseResult: Extracted data and any parse errors.
        """
        result = ParseResult(path=path, language=language)
        parser = self._parsers.get(language)
        if parser is None:
            result.errors.append(f"No parser available for language: {language}")
            logger.warning("No parser for language %s (%s)", language, path)
            return result

        try:
            tree = parser.parse(content)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            result.errors.append(str(exc))
            logger.warning("Parse failed for %s: %s", path, exc)
            return result

        if tree.root_node.has_error:
            result.errors.append("Syntax errors detected in AST")

        extractor = _EXTRACTORS.get(language)
        if extractor is None:
            result.errors.append(f"No extractor for language: {language}")
            return result

        try:
            extractor(content, tree.root_node, result)
        except Exception as exc:
            result.errors.append(str(exc))
            logger.warning("Extraction failed for %s: %s", path, exc)

        return result
