"""Tree-sitter based multi-language source parser.

This module provides classes and functions to parse source code files
across multiple languages (Python, JS/TS, Go, Rust) and extract symbols,
imports, function calls, and inheritance relationships.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tree_sitter import Language, Node, Parser

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class ParsedSymbol:
    """Represents a parsed symbol (class, function, method) from source code.

    Attributes:
        name (str): The local name of the symbol.
        kind (str): The kind of symbol (e.g., 'class', 'function', 'method').
        start_line (int): The starting line number (1-indexed).
        end_line (int): The ending line number (1-indexed).
        docstring (str | None): The extracted docstring or leading comment.
        complexity (int | None): Cyclomatic complexity score, if calculated.
        qualified_name (str | None): Fully qualified name, including parent scopes.
    """
    name: str
    kind: str
    start_line: int
    end_line: int
    docstring: str | None = None
    complexity: int | None = None
    qualified_name: str | None = None


@dataclass(frozen=True)
class ParsedImport:
    """Represents an import statement in source code.

    Attributes:
        module (str): The name of the module being imported.
        names (list[str]): The specific symbols imported from the module.
        start_line (int): The line number where the import occurs.
        is_relative (bool): Whether the import is a relative import.
    """
    module: str
    names: list[str]
    start_line: int
    is_relative: bool = False


@dataclass(frozen=True)
class ParsedInheritance:
    """Represents an inheritance relationship extracted from source code.

    Attributes:
        class_name (str): The name of the derived class.
        base (str): The name of the base class or interface.
        line (int): The line number where the inheritance is declared.
    """
    class_name: str
    base: str
    line: int


@dataclass(frozen=True)
class ParsedCall:
    """Represents a function or method call extracted from source code.

    Attributes:
        caller (str): The fully qualified name of the calling function/method.
        callee (str): The name or path of the called function/method.
        line (int): The line number where the call occurs.
    """
    caller: str
    callee: str
    line: int


@dataclass
class ParseResult:
    """Aggregates all parsed information for a single source file.

    Attributes:
        path (str): File path.
        language (str): Language identifier.
        symbols (list[ParsedSymbol]): Extracted symbols.
        imports (list[ParsedImport]): Extracted imports.
        inheritance (list[ParsedInheritance]): Extracted inheritance relationships.
        calls (list[ParsedCall]): Extracted function calls.
        errors (list[str]): Any errors encountered during parsing.
    """
    path: str
    language: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    inheritance: list[ParsedInheritance] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _line_number(node: Node) -> int:
    return node.start_point[0] + 1


def _end_line(node: Node) -> int:
    return node.end_point[0] + 1


def _node_text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _count_complexity(source: bytes, node: Node) -> int:
    """Approximate cyclomatic complexity from branch-like AST nodes."""
    branch_types = {
        "if_statement",
        "elif_clause",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "case_clause",
        "catch_clause",
        "conditional_expression",
        "binary_expression",
        "match_arm",
        "guard",
    }
    count = 1

    def walk(current: Node) -> None:
        nonlocal count
        if current.type in branch_types:
            count += 1
            if current.type == "binary_expression":
                text = _node_text(source, current)
                if "&&" not in text and "||" not in text and " and " not in text and " or " not in text:
                    count -= 1
        for child in current.children:
            walk(child)

    walk(node)
    return count


def _python_docstring(source: bytes, body_node: Node | None) -> str | None:
    if body_node is None or not body_node.children:
        return None
    first = body_node.children[0]
    if first.type != "expression_statement":
        return None
    expr = first.children[0] if first.children else None
    if expr is None or expr.type != "string":
        return None
    text = _node_text(source, expr)
    for quote in ('"""', "'''", '"', "'"):
        if text.startswith(quote) and text.endswith(quote):
            return text[len(quote) : -len(quote)].strip()
    return text.strip()


def _leading_comment_doc(source: bytes, node: Node) -> str | None:
    start = node.start_byte
    prefix = source[:start].decode("utf-8", errors="replace")
    lines = prefix.splitlines()
    collected: list[str] = []
    for line in reversed(lines[-5:]):
        stripped = line.strip()
        if stripped.startswith("#"):
            collected.insert(0, stripped.lstrip("#").strip())
        elif stripped.startswith("//"):
            collected.insert(0, stripped.lstrip("/").strip())
        elif stripped.startswith("///") or stripped.startswith("//!"):
            collected.insert(0, stripped.lstrip("/!").strip())
        elif not stripped:
            continue
        else:
            break
    if not collected:
        return None
    return "\n".join(collected)


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
            languages[key] = Language(getattr(module, attr_name)(), lang_name)
        except Exception as exc:  # pragma: no cover - optional grammars
            logger.warning("Failed to load tree-sitter grammar %s: %s", key, exc)
    return languages


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
            parser = Parser()
            parser.set_language(language)
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


def _append_symbol(
    result: ParseResult,
    *,
    name: str,
    kind: str,
    node: Node,
    source: bytes,
    qualified_name: str | None = None,
    body_node: Node | None = None,
) -> str:
    docstring = _python_docstring(source, body_node) if body_node else None
    if docstring is None:
        docstring = _leading_comment_doc(source, node)
    qname = qualified_name or name
    result.symbols.append(
        ParsedSymbol(
            name=name,
            kind=kind,
            start_line=_line_number(node),
            end_line=_end_line(node),
            docstring=docstring,
            complexity=_count_complexity(source, node),
            qualified_name=qname,
        )
    )
    return qname


def _record_call(result: ParseResult, caller: str, callee_node: Node, source: bytes) -> None:
    callee = _call_target_name(callee_node, source)
    if not callee or not caller:
        return
    result.calls.append(
        ParsedCall(
            caller=caller,
            callee=callee,
            line=_line_number(callee_node),
        )
    )


def _call_target_name(node: Node, source: bytes) -> str | None:
    if node.type == "identifier":
        return _node_text(source, node)
    if node.type == "attribute":
        return _node_text(source, node)
    if node.type == "field_expression":
        return _node_text(source, node)
    if node.type == "member_expression":
        return _node_text(source, node)
    if node.type == "scoped_identifier":
        return _node_text(source, node)
    if node.type == "selector_expression":
        for child in reversed(node.children):
            if child.type == "field_identifier":
                return _node_text(source, child)
    if node.children:
        return _call_target_name(node.children[0], source)
    return None


def _extract_python(source: bytes, root: Node, result: ParseResult) -> None:
    scope_stack: list[str] = [""]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = _append_symbol(
                    result,
                    name=name,
                    kind="function",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                scope_stack.append(qname)
                body = node.child_by_field_name("body")
                if body:
                    _walk_calls(body, qname)
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
                return

        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = _append_symbol(
                    result,
                    name=name,
                    kind="class",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                supers = node.child_by_field_name("superclasses")
                if supers:
                    for child in supers.children:
                        if child.type in {"identifier", "attribute", "argument_list"}:
                            for base in child.children:
                                if base.type in {"identifier", "attribute"}:
                                    result.inheritance.append(
                                        ParsedInheritance(
                                            class_name=name,
                                            base=_node_text(source, base),
                                            line=_line_number(base),
                                        )
                                    )
                scope_stack.append(qname)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
                return

        if node.type == "import_statement":
            names = [_node_text(source, child) for child in node.children if child.type == "dotted_name"]
            if names:
                result.imports.append(
                    ParsedImport(module=names[0], names=[names[0]], start_line=_line_number(node))
                )
            return

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module = _node_text(source, module_node) if module_node else ""
            imported: list[str] = []
            for child in node.children:
                if child.type == "dotted_name":
                    imported.append(_node_text(source, child))
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        imported.append(_node_text(source, name_node))
            result.imports.append(
                ParsedImport(
                    module=module,
                    names=imported or [module],
                    start_line=_line_number(node),
                    is_relative=module.startswith("."),
                )
            )
            return

        for child in node.children:
            walk(child)

    def _walk_calls(node: Node, caller: str) -> None:
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func:
                _record_call(result, caller, func, source)
        for child in node.children:
            _walk_calls(child, caller)

    walk(root)


def _extract_js_like(source: bytes, root: Node, result: ParseResult, language: str) -> None:
    scope_stack: list[str] = [""]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type in {"function_declaration", "method_definition", "generator_function_declaration"}:
            name_node = node.child_by_field_name("name")
            name = _node_text(source, name_node) if name_node else "<anonymous>"
            kind = "method" if node.type == "method_definition" else "function"
            qname = f"{current_scope()}.{name}" if current_scope() else name
            qname = _append_symbol(
                result,
                name=name,
                kind=kind,
                node=node,
                source=source,
                qualified_name=qname,
                body_node=node.child_by_field_name("body"),
            )
            scope_stack.append(qname)
            body = node.child_by_field_name("body")
            if body:
                _walk_calls(body, qname)
            scope_stack.pop()
            return

        if node.type in {"class_declaration", "abstract_class_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = _append_symbol(
                    result,
                    name=name,
                    kind="class",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                heritage = None
                for child in node.children:
                    if child.type.endswith("class_heritage") or child.type == "extends_clause":
                        heritage = child
                        break
                if heritage:
                    for child in heritage.children:
                        if child.type in {"identifier", "member_expression", "type_identifier"}:
                            result.inheritance.append(
                                ParsedInheritance(
                                    class_name=name,
                                    base=_node_text(source, child),
                                    line=_line_number(child),
                                )
                            )
                scope_stack.append(qname)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
                return

        if node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            module = _node_text(source, source_node).strip("\"'") if source_node else ""
            names: list[str] = []
            for child in node.children:
                if child.type == "import_clause":
                    for part in child.children:
                        if part.type == "identifier":
                            names.append(_node_text(source, part))
                        elif part.type == "named_imports":
                            for spec in part.children:
                                if spec.type == "import_specifier":
                                    name_node = spec.child_by_field_name("name")
                                    if name_node:
                                        names.append(_node_text(source, name_node))
            result.imports.append(
                ParsedImport(
                    module=module,
                    names=names or [module],
                    start_line=_line_number(node),
                    is_relative=module.startswith("."),
                )
            )
            return

        if node.type == "lexical_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if name_node and value_node and value_node.type in {
                        "arrow_function",
                        "function_expression",
                        "function",
                    }:
                        name = _node_text(source, name_node)
                        qname = f"{current_scope()}.{name}" if current_scope() else name
                        qname = _append_symbol(
                            result,
                            name=name,
                            kind="function",
                            node=child,
                            source=source,
                            qualified_name=qname,
                            body_node=value_node.child_by_field_name("body"),
                        )
                        body = value_node.child_by_field_name("body")
                        if body:
                            _walk_calls(body, qname)

        for child in node.children:
            walk(child)

    def _walk_calls(node: Node, caller: str) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                _record_call(result, caller, func, source)
        for child in node.children:
            _walk_calls(child, caller)

    walk(root)


def _extract_go(source: bytes, root: Node, result: ParseResult) -> None:
    package_name = ""
    for child in root.children:
        if child.type == "package_clause":
            for part in child.children:
                if part.type == "package_identifier":
                    package_name = _node_text(source, part)

    scope_stack: list[str] = [package_name]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = _append_symbol(
                    result,
                    name=name,
                    kind="function",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                body = node.child_by_field_name("body")
                if body:
                    _walk_calls(body, qname)
            return

        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = _append_symbol(
                    result,
                    name=name,
                    kind="method",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                body = node.child_by_field_name("body")
                if body:
                    _walk_calls(body, qname)
            return

        if node.type == "type_declaration":
            for spec in node.children:
                if spec.type == "type_spec":
                    name_node = spec.child_by_field_name("name")
                    if name_node is not None:
                        name = _node_text(source, name_node)
                        _append_symbol(
                            result,
                            name=name,
                            kind="class",
                            node=spec,
                            source=source,
                            qualified_name=name,
                        )
            return

        if node.type == "import_declaration":
            for child in node.children:
                if child.type == "import_spec":
                    path_node = child.child_by_field_name("path")
                    module = _node_text(source, path_node).strip('"') if path_node else ""
                    result.imports.append(
                        ParsedImport(module=module, names=[module], start_line=_line_number(child))
                    )
            return

        for child in node.children:
            walk(child)

    def _walk_calls(node: Node, caller: str) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                _record_call(result, caller, func, source)
        for child in node.children:
            _walk_calls(child, caller)

    walk(root)


def _extract_rust(source: bytes, root: Node, result: ParseResult) -> None:
    scope_stack: list[str] = [""]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type == "function_item":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = _append_symbol(
                    result,
                    name=name,
                    kind="function",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                body = node.child_by_field_name("body")
                if body:
                    _walk_calls(body, qname)
            return

        if node.type in {"struct_item", "enum_item", "trait_item"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(source, name_node)
                kind = "trait" if node.type == "trait_item" else "class"
                qname = _append_symbol(
                    result,
                    name=name,
                    kind=kind,
                    node=node,
                    source=source,
                    qualified_name=name,
                )
                if node.type == "struct_item":
                    scope_stack.append(qname)
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            walk(child)
                    scope_stack.pop()
            return

        if node.type == "impl_item":
            type_node = node.child_by_field_name("type")
            trait_node = node.child_by_field_name("trait")
            if type_node is not None:
                type_name = _node_text(source, type_node)
                if trait_node is not None:
                    result.inheritance.append(
                        ParsedInheritance(
                            class_name=type_name,
                            base=_node_text(source, trait_node),
                            line=_line_number(trait_node),
                        )
                    )
                scope_stack.append(type_name)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
            return

        if node.type == "use_declaration":
            text = _node_text(source, node)
            module = re.sub(r"^use\s+", "", text).strip().strip(";")
            result.imports.append(
                ParsedImport(module=module, names=[module], start_line=_line_number(node))
            )
            return

        for child in node.children:
            walk(child)

    def _walk_calls(node: Node, caller: str) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                _record_call(result, caller, func, source)
        for child in node.children:
            _walk_calls(child, caller)

    walk(root)


_EXTRACTORS: dict[str, Callable[[bytes, Node, ParseResult], None]] = {
    "python": _extract_python,
    "javascript": lambda s, n, r: _extract_js_like(s, n, r, "javascript"),
    "typescript": lambda s, n, r: _extract_js_like(s, n, r, "typescript"),
    "tsx": lambda s, n, r: _extract_js_like(s, n, r, "tsx"),
    "go": _extract_go,
    "rust": _extract_rust,
}
