"""Tests for Leiden community detection."""

from __future__ import annotations

from codegenome.builder import GraphBuilder, file_node_id
from codegenome.clusterer import GraphClusterer
from codegenome.graph_api import Graph
from codegenome.graph_api import create_graph
from codegenome.parser import ParseResult, ParsedCall, ParsedImport, ParsedSymbol
from codegenome.scanner import FileRecord, ScanResult


def _build_graph(files: dict[str, ParseResult]) -> Graph:
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
    graph, _, _ = GraphBuilder().build(scan, files)
    return graph


def test_clusterer_empty_graph() -> None:
    result = GraphClusterer().cluster(create_graph("igraph"))

    assert result.communities == {}
    assert result.bridge_nodes == []


def test_clusterer_single_file_project() -> None:
    solo = ParseResult(path="solo.py", language="python")
    solo.symbols = [
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="run",
        )
    ]
    graph = _build_graph({"solo.py": solo})
    result = GraphClusterer().cluster(graph)

    assert len(result.communities) == 1
    assert result.communities[file_node_id("solo.py")] == 0
    assert result.bridge_nodes == []


def test_clusterer_disconnected_graph_assigns_unique_communities() -> None:
    alpha = ParseResult(path="alpha.py", language="python")
    beta = ParseResult(path="beta.py", language="python")
    graph = _build_graph({"alpha.py": alpha, "beta.py": beta})

    result = GraphClusterer().cluster(graph)
    communities = set(result.communities.values())

    assert len(result.communities) == 2
    assert len(communities) == 2
    assert result.bridge_nodes == []


def test_clusterer_detects_bridge_node() -> None:
    left_a = ParseResult(path="left/a.py", language="python")
    left_a.symbols = [
        ParsedSymbol(
            name="work",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="work",
        )
    ]
    left_b = ParseResult(path="left/b.py", language="python")
    left_b.symbols = [
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="run",
        )
    ]
    left_b.calls = [ParsedCall(caller="run", callee="work", line=2)]
    left_b.imports = [ParsedImport(module="left.a", names=["work"], start_line=1)]

    right_a = ParseResult(path="right/a.py", language="python")
    right_a.symbols = [
        ParsedSymbol(
            name="work",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="work",
        )
    ]
    right_b = ParseResult(path="right/b.py", language="python")
    right_b.symbols = [
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="run",
        )
    ]
    right_b.calls = [ParsedCall(caller="run", callee="work", line=2)]
    right_b.imports = [ParsedImport(module="right.a", names=["work"], start_line=1)]

    bridge = ParseResult(path="bridge.py", language="python")
    bridge.symbols = [
        ParsedSymbol(
            name="connect",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="connect",
        )
    ]
    bridge.imports = [
        ParsedImport(module="left.b", names=["run"], start_line=1),
        ParsedImport(module="right.b", names=["run"], start_line=2),
    ]
    bridge.calls = [
        ParsedCall(caller="connect", callee="run", line=2),
    ]

    graph = _build_graph(
        {
            "left/a.py": left_a,
            "left/b.py": left_b,
            "right/a.py": right_a,
            "right/b.py": right_b,
            "bridge.py": bridge,
        }
    )
    clusterer = GraphClusterer()
    result = clusterer.cluster(graph)
    annotated = clusterer.annotate(graph.copy())

    assert len(result.communities) >= 3
    assert file_node_id("bridge.py") in result.bridge_nodes
    assert annotated.get_node(file_node_id("bridge.py")).get("is_bridge") is True
    assert "community_id" in annotated.get_node(file_node_id("bridge.py"))


def test_clusterer_annotate_adds_labels() -> None:
    alpha = ParseResult(path="alpha.py", language="python")
    beta = ParseResult(path="beta.py", language="python")
    beta.imports = [ParsedImport(module="alpha", names=["alpha"], start_line=1)]
    graph = _build_graph({"alpha.py": alpha, "beta.py": beta})

    annotated = GraphClusterer().annotate(graph)
    file_nodes = [
        attrs
        for node, attrs in annotated.iter_nodes()
        if attrs.get("node_type") == "file"
    ]
    assert file_nodes
    for attrs in file_nodes:
        assert "community_id" in attrs
        assert "is_bridge" in attrs
        assert "betweenness_centrality" in attrs


def test_clusterer_ranks_bridge_node_by_betweenness() -> None:
    left_a = ParseResult(path="left/a.py", language="python")
    left_a.symbols = [
        ParsedSymbol(
            name="work",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="work",
        )
    ]
    left_b = ParseResult(path="left/b.py", language="python")
    left_b.symbols = [
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="run",
        )
    ]
    left_b.calls = [ParsedCall(caller="run", callee="work", line=2)]
    left_b.imports = [ParsedImport(module="left.a", names=["work"], start_line=1)]

    right_a = ParseResult(path="right/a.py", language="python")
    right_a.symbols = [
        ParsedSymbol(
            name="work",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="work",
        )
    ]
    right_b = ParseResult(path="right/b.py", language="python")
    right_b.symbols = [
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="run",
        )
    ]
    right_b.calls = [ParsedCall(caller="run", callee="work", line=2)]
    right_b.imports = [ParsedImport(module="right.a", names=["work"], start_line=1)]

    bridge = ParseResult(path="bridge.py", language="python")
    bridge.symbols = [
        ParsedSymbol(
            name="connect",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="connect",
        )
    ]
    bridge.imports = [
        ParsedImport(module="left.b", names=["run"], start_line=1),
        ParsedImport(module="right.b", names=["run"], start_line=2),
    ]
    bridge.calls = [
        ParsedCall(caller="connect", callee="run", line=2),
    ]

    graph = _build_graph(
        {
            "left/a.py": left_a,
            "left/b.py": left_b,
            "right/a.py": right_a,
            "right/b.py": right_b,
            "bridge.py": bridge,
        }
    )
    clusterer = GraphClusterer()
    result = clusterer.cluster(graph)
    bridge_id = file_node_id("bridge.py")

    assert bridge_id in result.betweenness_centrality
    assert result.betweenness_centrality[bridge_id] > 0.0
    assert result.betweenness_centrality[bridge_id] == max(result.betweenness_centrality.values())

    annotated = clusterer.annotate(graph.copy())
    assert annotated.get_node(bridge_id).get("betweenness_centrality") == result.betweenness_centrality[bridge_id]
