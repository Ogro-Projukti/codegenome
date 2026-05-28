"""Tests for graph builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.builder import GraphBuilder, file_node_id, symbol_node_id
from codegenome.parser import ParseResult, ParsedCall, ParsedImport, ParsedInheritance, ParsedSymbol, SourceParser
from codegenome.scanner import FileRecord, ScanResult, WorkspaceScanner


@pytest.fixture
def sample_scan(tmp_path: Path) -> tuple[ScanResult, dict[str, ParseResult]]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "alpha.py").write_text(
        "from beta import helper\n\n"
        "class Alpha:\n"
        "    def run(self):\n"
        "        helper()\n",
        encoding="utf-8",
    )
    (root / "beta.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )

    scanner = WorkspaceScanner(root, cache_db=root / ".watcher" / "cache.db")
    scan = scanner.scan(incremental=False)
    scanner.cache.close()

    parser = SourceParser()
    parses = {}
    for record in scan.files:
        parsed = parser.parse_file(record.absolute_path)
        if parsed:
            parses[record.path] = parsed
    return scan, parses


def test_builder_creates_file_and_symbol_nodes(sample_scan: tuple[ScanResult, dict[str, ParseResult]]) -> None:
    scan, parses = sample_scan
    builder = GraphBuilder()
    graph = builder.build(scan, parses)

    from codegenome.graph_api import Graph
    assert isinstance(graph, Graph) or hasattr(graph, 'has_node')
    assert graph.has_node(file_node_id("alpha.py"))
    assert builder.symbol_count("alpha.py") >= 2
    meta = builder.file_metadata("alpha.py")
    assert meta is not None
    assert meta["node_type"] == "file"
    assert meta.get("language") == "python"
    assert "last_seen" in meta


def test_builder_tracks_imports_inheritance_and_calls() -> None:
    builder = GraphBuilder()
    scan = ScanResult(root="/tmp")
    scan.files = [
        FileRecord(
            path="model.py",
            absolute_path="/tmp/model.py",
            sha256="x",
            size=10,
            mtime=1.0,
        )
    ]
    parse = ParseResult(path="model.py", language="python")
    parse.symbols = [
        ParsedSymbol(
            name="Child",
            kind="class",
            start_line=1,
            end_line=5,
            qualified_name="Child",
        ),
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=6,
            end_line=10,
            qualified_name="Child.run",
        ),
    ]
    parse.imports = [ParsedImport(module="os", names=["os"], start_line=1)]
    parse.inheritance = [ParsedInheritance(class_name="Child", base="Base", line=1)]
    parse.calls = [ParsedCall(caller="Child.run", callee="helper", line=8)]

    graph = builder.build(scan, {"model.py": parse})
    file_id = file_node_id("model.py")
    import_nodes = [
        node
        for node, attrs in graph.iter_nodes()
        if attrs.get("node_type") == "import" and graph.has_edge(file_id, node)
    ]
    assert import_nodes
    assert any(attrs.get("edge_type") == "inherits" for _, _, attrs in graph.iter_edges())
    assert any(attrs.get("edge_type") == "calls" for _, _, attrs in graph.iter_edges())


def test_builder_incremental_update(sample_scan: tuple[ScanResult, dict[str, ParseResult]]) -> None:
    scan, parses = sample_scan
    builder = GraphBuilder()
    builder.build(scan, parses)
    initial_symbols = builder.symbol_count()

    root = Path(scan.root)
    (root / "alpha.py").write_text(
        "def solo():\n    return 42\n",
        encoding="utf-8",
    )

    scanner = WorkspaceScanner(root, cache_db=root / ".watcher" / "cache.db")
    updated_scan = scanner.scan(incremental=True)
    scanner.cache.close()

    parser = SourceParser()
    updated_parses = {}
    for record in updated_scan.files:
        if record.path in updated_scan.modified or record.path in updated_scan.added:
            parsed = parser.parse_file(record.absolute_path)
            if parsed:
                updated_parses[record.path] = parsed
        elif record.path in parses:
            updated_parses[record.path] = parses[record.path]

    builder.update(updated_scan, updated_parses)
    assert builder.symbol_count() != initial_symbols or builder.symbol_count("alpha.py") >= 1
    alpha_meta = builder.file_metadata("alpha.py")
    assert alpha_meta is not None
    assert alpha_meta.get("churn", 0) >= 1


def test_builder_empty_scan_does_not_crash() -> None:
    builder = GraphBuilder()
    scan = ScanResult(root="/empty")
    graph = builder.build(scan, {})
    assert graph.number_of_nodes() == 0


def test_builder_node_ids_are_stable() -> None:
    assert file_node_id("src/a.py") == "file:src/a.py"
    assert symbol_node_id("src/a.py", "Foo.bar") == "symbol:src/a.py:Foo.bar"
