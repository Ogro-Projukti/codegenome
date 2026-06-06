"""Tests for memory-bounded GraphStore MCP queries."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.builder import file_node_id
from codegenome.graph_api import create_graph
from codegenome.graph_store import GraphStore, GraphStoreError
from codegenome.intelligence import GraphIntelligence
from codegenome.snapshot_metrics import SnapshotMetrics
from codegenome.timeline import GraphTimeline


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    graph = create_graph("igraph")
    graph.add_node(
        "file:alpha.py",
        node_type="file",
        file_path="alpha.py",
        churn=0,
        complexity=1,
    )
    graph.add_node(
        "file:beta.py",
        node_type="file",
        file_path="beta.py",
        churn=0,
        complexity=1,
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
    graph.add_edge("file:alpha.py", "file:beta.py", edge_type="imports")

    db_path = tmp_path / "bounded.db"
    timeline = GraphTimeline(db_path)
    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    report = GraphIntelligence(graph).analyze()
    timeline.metrics_store.persist_snapshot(
        snapshot_id,
        SnapshotMetrics(report=report),
    )
    timeline.close()
    return db_path


def test_bounded_store_keeps_empty_graph_in_memory(sample_db: Path) -> None:
    store = GraphStore(sample_db, memory_bounded=True)
    store.open()
    try:
        summary = store.summary()
        assert summary.node_count == 3
        assert summary.edge_count == 2
        assert store.graph.number_of_nodes() == 0
    finally:
        store.close()


def test_bounded_get_node_and_neighbors(sample_db: Path) -> None:
    store = GraphStore(sample_db, memory_bounded=True, neighborhood_depth=1)
    store.open()
    try:
        node = store.get_node("symbol:alpha.py:run")
        assert node is not None
        neighbors = store.get_neighbors("file:alpha.py")
        assert neighbors["memory_bounded"] is True
        assert neighbors["outgoing"]
    finally:
        store.close()


def test_bounded_search_nodes(sample_db: Path) -> None:
    store = GraphStore(sample_db, memory_bounded=True)
    store.open()
    try:
        results = store.search_nodes("alpha")
        assert any(item["node_id"] == file_node_id("alpha.py") for item in results)
    finally:
        store.close()


def test_bounded_global_analysis_uses_stored_metrics(sample_db: Path) -> None:
    store = GraphStore(sample_db, memory_bounded=True, full_analysis_on_demand=False)
    store.open()
    try:
        dead = store.get_dead_code()
        assert isinstance(dead, list)
        entry_points = store.get_entry_points()
        assert isinstance(entry_points, list)
    finally:
        store.close()


def test_bounded_global_analysis_without_metrics_raises(tmp_path: Path) -> None:
    graph = create_graph("igraph")
    graph.add_node("file:alpha.py", node_type="file", file_path="alpha.py")
    db_path = tmp_path / "no-metrics.db"
    timeline = GraphTimeline(db_path)
    timeline.record_snapshot(graph, label="baseline")
    timeline.close()

    store = GraphStore(db_path, memory_bounded=True, full_analysis_on_demand=False)
    store.open()
    try:
        with pytest.raises(GraphStoreError, match="precomputed global metrics"):
            store.get_dead_code()
    finally:
        store.close()


def test_bounded_global_analysis_with_opt_in(sample_db: Path) -> None:
    store = GraphStore(sample_db, memory_bounded=True, full_analysis_on_demand=True)
    store.open()
    try:
        dead = store.get_dead_code()
        assert isinstance(dead, list)
    finally:
        store.close()
