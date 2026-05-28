"""Tests for SQLite graph timeline."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from codegenome.builder import GraphBuilder, file_node_id
from codegenome.graph_api import Graph, create_graph
from codegenome.parser import SourceParser
from codegenome.scanner import WorkspaceScanner
from codegenome.timeline import GraphTimeline


@pytest.fixture
def sample_graph(tmp_path: Path) -> Graph:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "alpha.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    scanner = WorkspaceScanner(root, cache_db=root / ".watcher" / "cache.db")
    scan = scanner.scan(incremental=False)
    scanner.cache.close()

    parser = SourceParser()
    parses = {}
    for record in scan.files:
        parsed = parser.parse_file(record.absolute_path)
        if parsed:
            parses[record.path] = parsed

    return GraphBuilder().build(scan, parses)


def test_timeline_snapshot_roundtrip(tmp_path: Path, sample_graph: Graph) -> None:
    timeline = GraphTimeline(tmp_path / "timeline.db")
    snapshot_id = timeline.record_snapshot(sample_graph, label="baseline")
    restored = timeline.load_snapshot(snapshot_id)
    timeline.close()

    assert restored.number_of_nodes() == sample_graph.number_of_nodes()
    assert restored.number_of_edges() == sample_graph.number_of_edges()
    assert restored.get_node(file_node_id("alpha.py"))["node_type"] == "file"


def test_timeline_delta_tracking(tmp_path: Path, sample_graph: Graph) -> None:
    timeline = GraphTimeline(tmp_path / "timeline.db")
    first_id = timeline.record_snapshot(sample_graph, label="v1")

    modified = sample_graph.copy()
    modified.add_node(
        "symbol:alpha.py:new_fn",
        node_type="symbol",
        file_path="alpha.py",
        name="new_fn",
        qualified_name="new_fn",
        kind="function",
        complexity=1,
        churn=0,
    )
    modified.add_edge(file_node_id("alpha.py"), "symbol:alpha.py:new_fn", edge_type="contains")
    second_id = timeline.record_snapshot(modified, label="v2")

    delta = timeline.compute_delta(first_id, second_id)
    timeline.close()

    assert "symbol:alpha.py:new_fn" in delta.added_nodes
    assert delta.removed_nodes == []
    assert (file_node_id("alpha.py"), "symbol:alpha.py:new_fn") in delta.added_edges


def test_timeline_node_history_and_churn_rate(tmp_path: Path, sample_graph: Graph) -> None:
    timeline = GraphTimeline(tmp_path / "timeline.db")
    node_id = file_node_id("alpha.py")

    first_id = timeline.record_snapshot(sample_graph, label="v1", created_at=1.0)
    changed = sample_graph.copy()
    changed.set_node_attr(node_id, "churn", 1)
    timeline.record_snapshot(changed, label="v2", created_at=2.0)

    unchanged = changed.copy()
    timeline.record_snapshot(unchanged, label="v3", created_at=3.0)

    history = timeline.query_node_history(node_id)
    churn_rate = timeline.churn_rate("alpha.py")
    timeline.close()

    assert len(history) == 3
    assert history[-1].attrs.get("churn") in {0, 1}
    assert churn_rate == pytest.approx(0.5)


def test_timeline_empty_graph_snapshot(tmp_path: Path) -> None:
    timeline = GraphTimeline(tmp_path / "timeline.db")
    snapshot_id = timeline.record_snapshot(create_graph("igraph"), label="empty")
    restored = timeline.load_snapshot(snapshot_id)
    snapshots = timeline.list_snapshots()
    timeline.close()

    assert restored.number_of_nodes() == 0
    assert snapshots[0].node_count == 0
    assert snapshots[0].label == "empty"
