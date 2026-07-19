"""Tests for snapshot-scoped GDR persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.builder import GraphBuilder
from codegenome.core import CodeGenomeConfig, CodeGenomeEngine
from codegenome.graph_api import create_graph
from codegenome.parser import SourceParser
from codegenome.registry import GlobalDependencyRegistry, RegistryEntry
from codegenome.scanner import WorkspaceScanner
from codegenome.timeline import GraphTimeline


@pytest.fixture
def two_file_workspace(
    tmp_path: Path,
) -> tuple[Path, object, dict[str, set[str]], dict[str, set[str]]]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "alpha.py").write_text(
        "from beta import helper\n\n"
        "def run():\n"
        "    helper()\n",
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

    graph, provides, consumes = GraphBuilder().build(scan, parses)
    return root, graph, provides, consumes


def _populate_registry(
    registry: GlobalDependencyRegistry,
    provides: dict[str, set[str]],
    consumes: dict[str, set[str]],
) -> None:
    for path in set(provides) | set(consumes):
        registry.update_file(
            path,
            provides.get(path, set()),
            consumes.get(path, set()),
        )


def test_gdr_store_persist_and_hydrate_roundtrip(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)

    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    timeline.gdr_store.persist_snapshot(snapshot_id, registry)

    restored = timeline.gdr_store.hydrate_registry(snapshot_id)
    timeline.close()

    assert restored.files.keys() == registry.files.keys()
    for path, entry in registry.files.items():
        assert restored.files[path].provides == entry.provides
        assert restored.files[path].consumes == entry.consumes
    assert restored.providers == registry.providers
    for fqn, files in registry.consumers.items():
        assert restored.consumers.get(fqn, set()) == files


def test_gdr_store_provider_and_dependents(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)

    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    store = timeline.gdr_store
    store.persist_snapshot(snapshot_id, registry)

    assert store.get_provider(snapshot_id, "helper") == "beta.py"
    assert "alpha.py" in store.get_dependents(snapshot_id, "helper")
    assert store.load_file(snapshot_id, "beta.py") is not None
    assert store.load_file(snapshot_id, "missing.py") is None
    timeline.close()


def test_gdr_store_resolve_change_scope(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)

    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    store = timeline.gdr_store
    store.persist_snapshot(snapshot_id, registry)

    scope = store.resolve_change_scope(
        snapshot_id,
        changed_files={"beta.py"},
        removed_fqns={"helper"},
        new_consumes=consumes,
    )
    timeline.close()

    assert "beta.py" in scope.changed
    assert "alpha.py" in scope.dependents
    assert scope.all_files >= {"beta.py", "alpha.py"}


def test_gdr_backed_registry_lazy_lookup(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)

    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    store = timeline.gdr_store
    store.persist_snapshot(snapshot_id, registry)

    backed = store.create_backed_registry(snapshot_id)
    assert backed.get_provider("helper") == "beta.py"
    assert "alpha.py" in backed.get_dependents("helper")

    backed.ensure_files({"alpha.py"})
    timeline.close()

    assert "alpha.py" in backed.files
    assert backed.files["alpha.py"].provides


def test_gdr_store_partial_hydrate(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)

    snapshot_id = timeline.record_snapshot(graph, label="baseline")
    store = timeline.gdr_store
    store.persist_snapshot(snapshot_id, registry)

    partial = store.hydrate_registry(snapshot_id, file_paths={"alpha.py"})
    timeline.close()

    assert set(partial.files) == {"alpha.py"}
    assert partial.get_provider("helper") == "beta.py"
    assert "alpha.py" in partial.get_dependents("helper")


def test_gdr_store_has_snapshot(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    snapshot_id = timeline.record_snapshot(graph, label="baseline")

    assert timeline.gdr_store.has_snapshot(snapshot_id) is False

    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)
    timeline.gdr_store.persist_snapshot(snapshot_id, registry)
    assert timeline.gdr_store.has_snapshot(snapshot_id) is True
    timeline.close()


def test_gdr_store_persist_snapshot_patch(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)

    base_id = timeline.record_snapshot(graph, label="baseline")
    store = timeline.gdr_store
    store.persist_snapshot(base_id, registry)

    registry.update_file(
        "beta.py",
        {"renamed_helper"},
        registry.files["beta.py"].consumes,
    )
    patched_id = timeline.record_snapshot(graph, label="patched")
    store.persist_snapshot_patch(base_id, patched_id, {"beta.py"}, registry)

    full = store.hydrate_registry(patched_id)
    timeline.close()

    assert full.files["alpha.py"] == registry.files["alpha.py"]
    assert full.files["beta.py"].provides == {"renamed_helper"}
    assert full.get_provider("renamed_helper") == "beta.py"
    assert "alpha.py" not in full.get_dependents("renamed_helper")


def test_persist_snapshot_uses_canonical_providers_when_files_disagree(
    tmp_path: Path,
) -> None:
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    registry.files["alpha.py"] = RegistryEntry({"helper"}, set())
    registry.files["beta.py"] = RegistryEntry({"helper"}, set())
    registry.providers["helper"] = "beta.py"

    store = timeline.gdr_store
    snapshot_id = timeline.record_snapshot(create_graph("igraph"))
    store.persist_snapshot(snapshot_id, registry)
    assert store.get_provider(snapshot_id, "helper") == "beta.py"
    timeline.close()


def test_persist_snapshot_patch_rebinds_fqn_from_unchanged_file(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    _, graph, provides, consumes = two_file_workspace
    timeline = GraphTimeline(tmp_path / "codegenome.db")
    registry = GlobalDependencyRegistry()
    _populate_registry(registry, provides, consumes)

    base_id = timeline.record_snapshot(graph, label="baseline")
    store = timeline.gdr_store
    store.persist_snapshot(base_id, registry)
    assert store.get_provider(base_id, "helper") == "beta.py"

    registry.files["alpha.py"] = RegistryEntry(
        {"helper"},
        registry.files["alpha.py"].consumes,
    )
    registry.providers["helper"] = "alpha.py"
    patched_id = timeline.record_snapshot(graph, label="patched")
    store.persist_snapshot_patch(base_id, patched_id, {"alpha.py"}, registry)

    assert store.get_provider(patched_id, "helper") == "alpha.py"
    timeline.close()


def test_engine_loads_persisted_registry_on_startup(
    tmp_path: Path,
    two_file_workspace: tuple[Path, object, dict[str, set[str]], dict[str, set[str]]],
) -> None:
    root, _, provides, consumes = two_file_workspace
    config = CodeGenomeConfig(workspace=root, export_formats=("json",))
    engine = CodeGenomeEngine(config)
    try:
        engine.build(full=True)
        assert engine.registry.files
        expected_files = set(provides) | set(consumes)
        assert set(engine.registry.files) >= expected_files
        saved_registry = engine.registry
    finally:
        engine.close()

    restarted = CodeGenomeEngine(config)
    try:
        assert restarted._loaded_existing_graph
        assert set(restarted.registry.files) == set(saved_registry.files)
        for path, entry in saved_registry.files.items():
            assert restarted.registry.files[path].provides == entry.provides
            assert restarted.registry.files[path].consumes == entry.consumes
        assert restarted.registry.providers == saved_registry.providers
    finally:
        restarted.close()
