"""Tests for partial graph loading and snapshot patching."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.builder import GraphBuilder, file_node_id
from codegenome.core import CodeGenomeConfig, CodeGenomeEngine
from codegenome.parser import SourceParser
from codegenome.scanner import WorkspaceScanner
from codegenome.timeline import GraphTimeline
from codegenome.working_set import WorkingSetGraph


@pytest.fixture
def two_file_graph(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "alpha.py").write_text(
        "from beta import helper\n\ndef run():\n    helper()\n",
        encoding="utf-8",
    )
    (root / "beta.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )

    scanner = WorkspaceScanner(root, cache_db=root / ".genome" / "cache.db")
    scan = scanner.scan(incremental=False)
    scanner.cache.close()

    parser = SourceParser()
    parses = {}
    for record in scan.files:
        parsed = parser.parse_file(record.absolute_path)
        if parsed:
            parses[record.path] = parsed

    graph, _, _ = GraphBuilder().build(scan, parses)
    return root, graph


def test_load_file_subgraph_returns_single_file_nodes(
    tmp_path: Path,
    two_file_graph: tuple[Path, object],
) -> None:
    _, graph = two_file_graph
    timeline = GraphTimeline(tmp_path / "timeline.db")
    snapshot_id = timeline.record_snapshot(graph, label="baseline")

    subgraph = timeline.load_file_subgraph(snapshot_id, {"alpha.py"})
    full = timeline.load_snapshot(snapshot_id)
    timeline.close()

    assert subgraph.number_of_nodes() < full.number_of_nodes()
    assert subgraph.has_node(file_node_id("alpha.py"))
    assert not subgraph.has_node(file_node_id("beta.py"))


def test_record_snapshot_patch_updates_only_changed_file(
    tmp_path: Path,
    two_file_graph: tuple[Path, object],
) -> None:
    _, graph = two_file_graph
    timeline = GraphTimeline(tmp_path / "timeline.db")
    first_id = timeline.record_snapshot(graph, label="baseline")

    modified = graph.copy()
    modified.add_node(
        "symbol:alpha.py:extra",
        node_type="symbol",
        file_path="alpha.py",
        name="extra",
        qualified_name="extra",
        kind="function",
        complexity=1,
        churn=0,
    )
    modified.add_edge(file_node_id("alpha.py"), "symbol:alpha.py:extra", edge_type="contains")

    second_id = timeline.record_snapshot_patch(first_id, {"alpha.py"}, modified, label="patched")
    restored = timeline.load_snapshot(second_id)
    timeline.close()

    assert restored.has_node("symbol:alpha.py:extra")
    assert restored.has_node(file_node_id("beta.py"))
    assert restored.number_of_nodes() == graph.number_of_nodes() + 1


def test_working_set_eviction(tmp_path: Path, two_file_graph: tuple[Path, object]) -> None:
    _, graph = two_file_graph
    timeline = GraphTimeline(tmp_path / "timeline.db")
    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    working_set = WorkingSetGraph(timeline, snapshot_id, max_files=1)

    working_set.ensure_files({"alpha.py", "beta.py"})
    timeline.close()

    assert len(working_set.loaded_files) == 1
    assert working_set.graph.number_of_nodes() > 0


def test_memory_bounded_engine_keeps_empty_graph_after_build(
    tmp_path: Path,
    two_file_graph: tuple[Path, object],
) -> None:
    root, _ = two_file_graph
    config = CodeGenomeConfig(
        workspace=root,
        export_formats=("json",),
        memory_bounded=True,
        max_working_files=8,
    )
    engine = CodeGenomeEngine(config)
    try:
        result = engine.build(full=True)
        assert result.snapshot_id is not None
        assert engine.builder.graph.number_of_nodes() == 0
        assert engine._working_set is not None
        assert engine._working_set.loaded_files == set()
    finally:
        engine.close()
