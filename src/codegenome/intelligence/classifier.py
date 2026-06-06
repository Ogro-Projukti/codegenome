"""Node classification helpers (entry points, generated/vendor, API surface)."""

from __future__ import annotations

from codegenome.graph_api import Graph
from codegenome.intelligence.pathutil import PathLike


class NodeClassifier:
    """Classify graph nodes by role: entry, generated/vendor, dunder, public API."""

    ENTRY_SYMBOL_NAMES = frozenset({"main", "run", "cli", "app"})
    ENTRY_FILE_NAMES = frozenset(
        {"__main__.py", "main.py", "app.py", "index.js", "index.ts", "index.tsx"}
    )
    GENERATED_PATH_PARTS = frozenset(
        {
            ".cache",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            "build",
            "coverage",
            "dist",
            "node_modules",
            "site-packages",
            "vendor",
            "vendors",
            "venv",
        }
    )
    GENERATED_FILE_SUFFIXES = (
        ".bundle.css",
        ".bundle.js",
        ".generated.css",
        ".generated.js",
        ".map",
        ".min.css",
        ".min.js",
    )

    def is_generated_or_vendor(self, attrs: dict[str, object]) -> bool:
        """Return True for nodes that live in generated or vendored locations."""
        path = str(attrs.get("file_path") or attrs.get("absolute_path") or "")
        if not path:
            return False

        normalized = path.replace("\\", "/").casefold()
        parts = {part for part in normalized.split("/") if part}
        if parts & self.GENERATED_PATH_PARTS:
            return True

        name = PathLike(normalized).name
        return name.endswith(self.GENERATED_FILE_SUFFIXES)

    def entry_symbol_ids(self, graph: Graph) -> list[str]:
        """Return symbol node IDs that look like application entry points."""
        entries: list[str] = []
        for node, attrs in graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            name = str(attrs.get("name", ""))
            qname = str(attrs.get("qualified_name", ""))
            if name in self.ENTRY_SYMBOL_NAMES or qname.endswith(".main"):
                entries.append(node)
        return entries

    @staticmethod
    def is_dunder_name(name: str) -> bool:
        """Return True for dunder names like ``__init__``."""
        return len(name) > 4 and name.startswith("__") and name.endswith("__")

    @staticmethod
    def is_public_api_method(attrs: dict[str, object]) -> bool:
        """Return True for public methods on public classes (likely API surface)."""
        name = str(attrs.get("name", ""))
        if not name or name.startswith("_"):
            return False

        qname = str(attrs.get("qualified_name") or "")
        if "." not in qname:
            return False

        owner = qname.rsplit(".", 1)[0].rsplit(".", 1)[-1]
        return bool(owner) and owner[:1].isupper() and not owner.startswith("_")
