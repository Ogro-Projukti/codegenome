"""Tests for architectural intelligence analysis."""

from __future__ import annotations

import pytest

from codegenome.builder import GraphBuilder, file_node_id, symbol_node_id
from codegenome.intelligence import GraphIntelligence
from codegenome.parser import ParseResult, ParsedCall, ParsedImport, ParsedSymbol
from codegenome.scanner import FileRecord, ScanResult


from codegenome.graph_api import Graph, create_graph

def _build_graph(
    files: dict[str, ParseResult],
    *,
    churn: dict[str, int] | None = None,
) -> Graph:
    scan = ScanResult(root="/tmp")
    scan.files = [
        FileRecord(
            path=path,
            absolute_path=f"/tmp/{path}",
            sha256=f"hash-{path}",
            size=10,
            mtime=1.0,
        )
        for path in files
    ]
    builder = GraphBuilder()
    graph, _, _ = builder.build(scan, files)
    if churn:
        for path, value in churn.items():
            node_id = file_node_id(path)
            if graph.has_node(node_id):
                graph.set_node_attr(node_id, "churn", value)
    return graph


def test_intelligence_empty_graph() -> None:
    intelligence = GraphIntelligence(create_graph("igraph"))
    report = intelligence.analyze()

    assert report.dead_code == []
    assert report.circular_dependencies == []
    assert report.god_nodes == []
    assert report.entry_points == []
    assert report.orphan_modules == []
    assert report.complexity_rankings == []
    assert report.churn_rankings == []
    assert report.cbo_rankings == []
    assert report.lcom_rankings == []
    assert report.tightly_coupled_classes == []


def test_intelligence_detects_dead_code() -> None:
    parse = ParseResult(path="solo.py", language="python")
    parse.symbols = [
        ParsedSymbol(
            name="used",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="used",
        ),
        ParsedSymbol(
            name="unused",
            kind="function",
            start_line=4,
            end_line=5,
            qualified_name="unused",
        ),
    ]
    parse.calls = [ParsedCall(caller="used", callee="unused", line=2)]

    graph = _build_graph({"solo.py": parse})
    dead = GraphIntelligence(graph).detect_dead_code()

    assert symbol_node_id("solo.py", "unused") not in dead
    assert dead == []


def test_intelligence_detects_unreachable_dead_code() -> None:
    parse = ParseResult(path="solo.py", language="python")
    parse.symbols = [
        ParsedSymbol(
            name="orphaned",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="orphaned",
        )
    ]

    graph = _build_graph({"solo.py": parse})
    dead = GraphIntelligence(graph).detect_dead_code()

    assert dead == [symbol_node_id("solo.py", "orphaned")]


def test_intelligence_detects_circular_dependencies() -> None:
    alpha = ParseResult(path="alpha.py", language="python")
    alpha.imports = [ParsedImport(module="beta", names=["beta"], start_line=1)]

    beta = ParseResult(path="beta.py", language="python")
    beta.imports = [ParsedImport(module="alpha", names=["alpha"], start_line=1)]

    graph = _build_graph({"alpha.py": alpha, "beta.py": beta})
    cycles = GraphIntelligence(graph).detect_circular_dependencies()

    assert cycles
    assert {file_node_id("alpha.py"), file_node_id("beta.py")} == set(cycles[0])


def test_intelligence_detects_orphans_in_disconnected_graph() -> None:
    alpha = ParseResult(path="alpha.py", language="python")
    beta = ParseResult(path="beta.py", language="python")

    graph = _build_graph({"alpha.py": alpha, "beta.py": beta})
    orphans = GraphIntelligence(graph).detect_orphan_modules()

    assert orphans == ["alpha.py", "beta.py"]


def test_intelligence_single_file_project_has_no_orphans() -> None:
    solo = ParseResult(path="solo.py", language="python")
    graph = _build_graph({"solo.py": solo})

    assert GraphIntelligence(graph).detect_orphan_modules() == []


def test_intelligence_rankings() -> None:
    parse = ParseResult(path="rank.py", language="python")
    parse.symbols = [
        ParsedSymbol(
            name="easy",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="easy",
            complexity=2,
        ),
        ParsedSymbol(
            name="hard",
            kind="function",
            start_line=4,
            end_line=20,
            qualified_name="hard",
            complexity=9,
        ),
    ]

    graph = _build_graph({"rank.py": parse}, churn={"rank.py": 3})
    intelligence = GraphIntelligence(graph)

    complexity = intelligence.complexity_rankings()
    churn = intelligence.churn_rankings()

    assert complexity[0] == (symbol_node_id("rank.py", "hard"), 9)
    assert churn[0] == (file_node_id("rank.py"), 3)


def test_intelligence_filters_generated_complexity_by_default() -> None:
    graph = create_graph("igraph")
    graph.add_node(
        "symbol:src/app.py:hard",
        node_type="symbol",
        file_path="src/app.py",
        name="hard",
        qualified_name="hard",
        kind="function",
        complexity=5,
    )
    graph.add_node(
        "symbol:src/assets/vendor.min.js:a",
        node_type="symbol",
        file_path="src/assets/vendor.min.js",
        name="a",
        qualified_name="a",
        kind="function",
        complexity=99,
    )

    intelligence = GraphIntelligence(graph)

    assert intelligence.complexity_rankings()[0] == ("symbol:src/app.py:hard", 5)
    assert intelligence.complexity_rankings(include_generated=True)[0] == (
        "symbol:src/assets/vendor.min.js:a",
        99,
    )


def test_intelligence_filters_public_api_methods_from_dead_code_by_default() -> None:
    graph = create_graph("igraph")
    graph.add_node(
        "symbol:src/codegenome/graph_api.py:Graph.add_node",
        node_type="symbol",
        file_path="src/codegenome/graph_api.py",
        name="add_node",
        qualified_name="Graph.add_node",
        kind="method",
        complexity=1,
    )
    graph.add_node(
        "symbol:src/codegenome/graph_api.py:Graph._unused_helper",
        node_type="symbol",
        file_path="src/codegenome/graph_api.py",
        name="_unused_helper",
        qualified_name="Graph._unused_helper",
        kind="method",
        complexity=1,
    )

    intelligence = GraphIntelligence(graph)

    assert intelligence.detect_dead_code() == [
        "symbol:src/codegenome/graph_api.py:Graph._unused_helper"
    ]
    assert "symbol:src/codegenome/graph_api.py:Graph.add_node" in (
        intelligence.detect_dead_code(include_public_api=True)
    )


def test_intelligence_detects_entry_points() -> None:
    alpha = ParseResult(path="alpha.py", language="python")
    alpha.symbols = [
        ParsedSymbol(
            name="main",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="main",
        )
    ]
    beta = ParseResult(path="beta.py", language="python")
    beta.imports = [ParsedImport(module="alpha", names=["alpha"], start_line=1)]

    graph = _build_graph({"alpha.py": alpha, "beta.py": beta})
    entry_points = GraphIntelligence(graph).detect_entry_points()

    assert file_node_id("beta.py") in entry_points
    assert symbol_node_id("alpha.py", "main") in entry_points
    assert file_node_id("alpha.py") not in entry_points


@pytest.mark.parametrize(
    ("node_count", "expected_communities"),
    [
        (0, 0),
        (1, 1),
    ],
)
def test_intelligence_god_nodes_edge_cases(node_count: int, expected_communities: int) -> None:
    graph = create_graph("igraph")
    for index in range(node_count):
        node_id = f"file:node{index}.py"
        graph.add_node(node_id, node_type="file", file_path=f"node{index}.py")

    god_nodes = GraphIntelligence(graph).detect_god_nodes()
    assert len(god_nodes) == expected_communities
