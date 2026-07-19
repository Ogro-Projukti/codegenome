"""Tests for SQLite graph timeline."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

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

    scanner = WorkspaceScanner(root, cache_db=root / ".genome" / "cache.db")
    scan = scanner.scan(incremental=False)
    scanner.cache.close()

    parser = SourceParser()
    parses = {}
    for record in scan.files:
        parsed = parser.parse_file(record.absolute_path)
        if parsed:
            parses[record.path] = parsed

    return GraphBuilder().build(scan, parses)[0]


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

    timeline.record_snapshot(sample_graph, label="v1", created_at=1.0)
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


def test_multiedge_snapshot_roundtrip_invariant(tmp_path: Path) -> None:
    graph = create_graph("igraph")
    graph.add_node("file:a.py", node_type="file", file_path="a.py")
    graph.add_node("file:b.py", node_type="file", file_path="b.py")
    graph.add_edge("file:a.py", "file:b.py", edge_type="calls", line=10)
    graph.add_edge("file:a.py", "file:b.py", edge_type="calls", line=20)
    graph.add_edge("file:a.py", "file:b.py", edge_type="calls", line=20)

    expected_edges = Counter(
        (source, target, json.dumps(attrs, sort_keys=True))
        for source, target, attrs in graph.iter_edges()
    )
    timeline = GraphTimeline(tmp_path / "timeline.db")
    first_id = timeline.record_snapshot(graph, label="full")
    second_id = timeline.record_snapshot_patch(first_id, {"a.py"}, graph, label="patch")

    try:
        for snapshot_id in (first_id, second_id):
            restored = timeline.load_snapshot(snapshot_id)
            actual_edges = Counter(
                (source, target, json.dumps(attrs, sort_keys=True))
                for source, target, attrs in restored.iter_edges()
            )
            assert actual_edges == expected_edges
            assert restored.number_of_edges() == graph.number_of_edges() == 3
            assert len(timeline.list_snapshot_edges(snapshot_id)) == 3

            output_path = timeline.export_snapshot_json(
                snapshot_id,
                tmp_path / f"snapshot-{snapshot_id}.json",
            )
            exported = json.loads(output_path.read_text(encoding="utf-8"))
            assert exported["edge_count"] == len(exported["edges"]) == 3

        delta = timeline.compute_delta(first_id, second_id)
        assert delta.added_edges == []
        assert delta.removed_edges == []
        assert [snapshot.edge_count for snapshot in timeline.list_snapshots()] == [3, 3]
    finally:
        timeline.close()


def test_legacy_edge_schema_migrates_without_false_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            label TEXT,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL
        );
        CREATE TABLE graph_edges (
            snapshot_id INTEGER NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            attrs_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, source_id, target_id)
        );
        INSERT INTO snapshots
            (snapshot_id, created_at, label, node_count, edge_count)
        VALUES (1, 1.0, 'legacy', 2, 2);
        INSERT INTO graph_edges
            (snapshot_id, source_id, target_id, attrs_json)
        VALUES (1, 'a', 'b', '{"edge_type": "calls"}');
        """
    )
    connection.commit()
    connection.close()

    timeline = GraphTimeline(db_path)
    try:
        columns = timeline.connection.execute("PRAGMA table_info(graph_edges)").fetchall()
        primary_key = [
            row["name"]
            for row in sorted((row for row in columns if row["pk"]), key=lambda row: row["pk"])
        ]
        assert primary_key == ["snapshot_id", "source_id", "target_id", "edge_key"]
        assert timeline.list_snapshots()[0].edge_count == 1
    finally:
        timeline.close()
