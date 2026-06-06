"""Tests for precomputed snapshot metrics persistence."""

from __future__ import annotations

from pathlib import Path

from codegenome.clusterer import GraphClusterer
from codegenome.graph_api import create_graph
from codegenome.intelligence import GraphIntelligence, IntelligenceReport
from codegenome.snapshot_metrics import SnapshotMetrics
from codegenome.timeline import GraphTimeline


def test_snapshot_metrics_persist_and_load_roundtrip(tmp_path: Path) -> None:
    graph = create_graph("igraph")
    graph.add_node("file:alpha.py", node_type="file", file_path="alpha.py")
    report = IntelligenceReport(
        dead_code=["symbol:alpha.py:unused"],
        entry_points=["file:alpha.py"],
    )
    betweenness = (("file:alpha.py", 0.5),)
    metrics = SnapshotMetrics(report=report, betweenness_rankings=betweenness)

    timeline = GraphTimeline(tmp_path / "codegenome.db")
    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    timeline.metrics_store.persist_snapshot(snapshot_id, metrics)

    loaded = timeline.metrics_store.load_snapshot(snapshot_id)
    timeline.close()

    assert loaded is not None
    assert loaded.report.dead_code == report.dead_code
    assert loaded.report.entry_points == report.entry_points
    assert loaded.betweenness_rankings == betweenness


def test_snapshot_metrics_copy_on_patch(tmp_path: Path) -> None:
    graph = create_graph("igraph")
    graph.add_node("file:alpha.py", node_type="file", file_path="alpha.py")
    report = IntelligenceReport(dead_code=["symbol:alpha.py:old"])

    timeline = GraphTimeline(tmp_path / "codegenome.db")
    base_id = timeline.record_snapshot(graph, label="baseline")
    timeline.metrics_store.persist_snapshot(base_id, SnapshotMetrics(report=report))

    graph.add_node("file:beta.py", node_type="file", file_path="beta.py")
    patched_id = timeline.record_snapshot_patch(
        base_id,
        {"beta.py"},
        graph,
        label="patched",
    )
    copied = timeline.metrics_store.load_snapshot(patched_id)
    timeline.close()

    assert copied is not None
    assert copied.report.dead_code == report.dead_code


def test_full_build_metrics_shape(tmp_path: Path) -> None:
    graph = create_graph("igraph")
    graph.add_node(
        "file:alpha.py",
        node_type="file",
        file_path="alpha.py",
        complexity=2,
        churn=1,
    )
    graph.add_node(
        "symbol:alpha.py:run",
        node_type="symbol",
        file_path="alpha.py",
        name="run",
        qualified_name="run",
        kind="function",
        complexity=1,
        churn=0,
    )
    graph.add_edge("file:alpha.py", "symbol:alpha.py:run", edge_type="contains")

    intelligence = GraphIntelligence(graph)
    report = intelligence.analyze()
    betweenness = tuple(GraphClusterer().betweenness_rankings(graph))

    timeline = GraphTimeline(tmp_path / "codegenome.db")
    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    timeline.metrics_store.persist_snapshot(
        snapshot_id,
        SnapshotMetrics(report=report, betweenness_rankings=betweenness),
    )
    loaded = timeline.metrics_store.load_snapshot(snapshot_id)
    timeline.close()

    assert loaded is not None
    assert isinstance(loaded.report.dead_code, list)
    assert isinstance(loaded.betweenness_rankings, tuple)
