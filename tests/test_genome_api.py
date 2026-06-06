"""Tests for progressive-disclosure genome REST payloads."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.builder import GraphBuilder
from codegenome.graph_api import create_graph
from codegenome.mcp_server import GraphService, ServerConfig, create_server
from codegenome.parser import ParseResult, ParsedImport, ParsedSymbol
from codegenome.scanner import FileRecord, ScanResult
from codegenome.serializers.genome_provider import (
    GenomeProvider,
    ROOT_MODULE_ID,
    filter_graph_delta_for_module,
    module_id_for_file,
)
from codegenome.serializers.nucleotide_mapper import NucleotideBase
from codegenome.timeline import GraphTimeline


def _build_graph(files: dict[str, ParseResult]):
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
    return graph


def test_module_id_for_file() -> None:
    assert module_id_for_file("solo.py") == ROOT_MODULE_ID
    assert module_id_for_file("core/main.py") == "core"


def test_genome_summary_returns_lightweight_modules() -> None:
    core_main = ParseResult(path="core/main.py", language="python")
    core_main.symbols = [
        ParsedSymbol(name="run", kind="function", start_line=1, end_line=2, qualified_name="run"),
    ]
    core_util = ParseResult(path="core/util.py", language="python")
    core_util.symbols = [
        ParsedSymbol(name="helper", kind="function", start_line=1, end_line=2, qualified_name="helper"),
    ]
    graph = _build_graph({"core/main.py": core_main, "core/util.py": core_util})

    summary = GenomeProvider(graph).build_summary(snapshot_id=7)
    assert summary.snapshot_id == 7
    assert len(summary.modules) == 1
    module = summary.modules[0]
    assert module.module_id == "core"
    assert module.gene_count == 2
    assert 0.0 <= module.health_score <= 1.0
    # Two free functions map to two "A" nucleotides for the karyotype card.
    assert module.base_counts["A"] == 2
    assert set(module.base_counts) == {"A", "A*", "T", "G", "C"}


def test_genome_summary_groups_modules_by_leiden_community() -> None:
    core_main = ParseResult(path="core/main.py", language="python")
    core_main.symbols = [
        ParsedSymbol(name="Service", kind="class", start_line=1, end_line=4, qualified_name="Service"),
    ]
    graph = _build_graph({"core/main.py": core_main})
    # Simulate the Leiden annotation that build_service applies before snapshotting.
    graph.set_node_attr("file:core/main.py", "community_id", 3)

    summary = GenomeProvider(graph).build_summary()
    module = summary.modules[0]
    assert module.community_id == 3
    assert module.base_counts["T"] == 1


def test_helix_graph_returns_dense_nodes_and_edges() -> None:
    module_file = ParseResult(path="core/main.py", language="python")
    module_file.imports = [ParsedImport(module="os", names=["os"], start_line=1)]
    module_file.symbols = [
        ParsedSymbol(name="Worker", kind="class", start_line=3, end_line=6, qualified_name="Worker"),
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=8,
            end_line=10,
            qualified_name="run",
        ),
    ]
    graph = _build_graph({"core/main.py": module_file})

    payload = GenomeProvider(graph).build_helix_graph("core")
    assert payload is not None
    assert payload.module_id == "core"
    assert payload.nodes
    assert any(node.base == NucleotideBase.G for node in payload.nodes)
    assert any(node.base == NucleotideBase.T for node in payload.nodes)
    assert any(node.base == NucleotideBase.A for node in payload.nodes)


def test_structure_tree_nests_classes_and_methods() -> None:
    module_file = ParseResult(path="core/main.py", language="python")
    module_file.symbols = [
        ParsedSymbol(name="Worker", kind="class", start_line=1, end_line=8, qualified_name="Worker"),
        ParsedSymbol(
            name="save",
            kind="method",
            start_line=3,
            end_line=4,
            qualified_name="Worker.save",
        ),
        ParsedSymbol(name="run", kind="function", start_line=10, end_line=12, qualified_name="run"),
    ]
    graph = _build_graph({"core/main.py": module_file})

    payload = GenomeProvider(graph).build_structure_tree("core")
    assert payload is not None
    assert payload.package == "core"
    assert len(payload.files) == 1
    file_node = payload.files[0]
    assert file_node.path == "core/main.py"
    assert len(file_node.classes) == 1
    assert file_node.classes[0].methods[0].name == "save"
    assert file_node.functions[0].name == "run"


def test_filter_graph_delta_for_module() -> None:
    delta = {
        "type": "graph_delta",
        "added_nodes": ["file:core/main.py", "file:other/main.py"],
        "removed_nodes": [],
        "modified_nodes": ["symbol:core/main.py:run"],
        "added_edges": [("file:core/main.py", "symbol:core/main.py:run")],
        "removed_edges": [],
    }
    filtered = filter_graph_delta_for_module(delta, "core")
    assert filtered["added_nodes"] == ["file:core/main.py"]
    assert filtered["modified_nodes"] == ["symbol:core/main.py:run"]
    assert filtered["added_edges"] == [("file:core/main.py", "symbol:core/main.py:run")]


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    graph = create_graph("igraph")
    graph.add_node(
        "file:core/main.py",
        node_type="file",
        file_path="core/main.py",
    )
    graph.add_node(
        "symbol:core/main.py:run",
        node_type="symbol",
        file_path="core/main.py",
        name="run",
        qualified_name="run",
        kind="function",
        start_line=1,
        end_line=2,
    )
    graph.add_edge("file:core/main.py", "symbol:core/main.py:run", edge_type="contains")

    db_path = tmp_path / "test.db"
    timeline = GraphTimeline(db_path)
    timeline.record_snapshot(graph, label="baseline")
    timeline.close()
    return db_path


def test_graph_store_exposes_genome_graph(sample_db: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    try:
        create_server(service)
        summary = service.run(
            lambda: GenomeProvider(service.store.graph_for_genome()).build_summary(
                snapshot_id=service.store.snapshot_id
            )
        )
        assert summary.modules[0].module_id == "core"
        structure = service.run(
            lambda: GenomeProvider(service.store.graph_for_genome()).build_structure_tree("core")
        )
        assert structure is not None
        assert structure.files[0].path == "core/main.py"
    finally:
        service.shutdown()
