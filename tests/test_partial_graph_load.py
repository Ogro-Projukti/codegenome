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


def test_export_snapshot_html_uses_deferred_json(
    tmp_path: Path,
    two_file_graph: tuple[Path, object],
) -> None:
    _, graph = two_file_graph
    timeline = GraphTimeline(tmp_path / "timeline.db")
    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    export_dir = tmp_path / "exports"
    timeline.export_snapshot_json(snapshot_id, export_dir / "graph.json")
    html_path = timeline.export_snapshot_html(
        snapshot_id,
        export_dir / "graph.html",
        workspace_name="repo",
        report=None,
    )
    stats = timeline.compute_snapshot_statistics(snapshot_id)
    timeline.close()

    html = html_path.read_text(encoding="utf-8")
    assert '"liveJsonUrl": "graph.json"' in html
    assert '"nodes": []' in html
    assert stats.node_count == graph.number_of_nodes()


def test_memory_bounded_rebuild_incremental_patches_snapshot(
    tmp_path: Path,
    two_file_graph: tuple[Path, object],
) -> None:
    root, graph = two_file_graph
    config = CodeGenomeConfig(
        workspace=root,
        export_formats=("json",),
        memory_bounded=True,
        max_working_files=8,
    )
    engine = CodeGenomeEngine(config)
    try:
        first = engine.build(full=True)
        assert first.snapshot_id is not None
        baseline_nodes = engine.timeline.list_snapshots()[-1].node_count

        (root / "alpha.py").write_text(
            "from beta import helper\n\n"
            "def run():\n"
            "    helper()\n\n"
            "def extra():\n"
            "    return 2\n",
            encoding="utf-8",
        )

        second = engine.rebuild_incremental()
        assert second.snapshot_id != first.snapshot_id
        assert engine._working_set is not None
        assert len(engine._working_set.loaded_files) <= config.max_working_files
        assert engine.builder.graph.number_of_nodes() > 0
        latest = engine.timeline.list_snapshots()[-1]
        assert latest.node_count >= baseline_nodes
        assert engine.timeline.gdr_store.has_snapshot(second.snapshot_id)
    finally:
        engine.close()


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
