"""Tests for module health aggregation and G! alerting."""

from __future__ import annotations

from codegenome.builder import GraphBuilder
from codegenome.parser import ParseResult, ParsedImport, ParsedSymbol
from codegenome.registry import GlobalDependencyRegistry
from codegenome.scanner import FileRecord, ScanResult
from codegenome.serializers.health_aggregator import HealthAggregator
from codegenome.serializers.nucleotide_mapper import NucleotideBase


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
    graph, provides, consumes = builder.build(scan, files)
    registry = GlobalDependencyRegistry()
    for path in files:
        registry.update_file(path, provides.get(path, set()), consumes.get(path, set()))
    return graph, registry


def test_health_score_penalizes_circular_imports() -> None:
    alpha = ParseResult(path="alpha.py", language="python")
    alpha.imports = [ParsedImport(module="beta", names=["helper"], start_line=1)]
    beta = ParseResult(path="beta.py", language="python")
    beta.imports = [ParsedImport(module="alpha", names=["run"], start_line=1)]
    beta.symbols = [
        ParsedSymbol(name="helper", kind="function", start_line=2, end_line=3, qualified_name="helper"),
    ]

    graph, registry = _build_graph({"alpha.py": alpha, "beta.py": beta})
    aggregator = HealthAggregator(graph)

    alpha_health = aggregator.compute_module_health("alpha.py")
    assert alpha_health.circular_dep_rate == 1.0
    assert "circular_import" in alpha_health.alerts
    assert alpha_health.health_score < 1.0


def test_circular_import_targets_flags_g_alert() -> None:
    alpha = ParseResult(path="alpha.py", language="python")
    alpha.imports = [ParsedImport(module="beta", names=["helper"], start_line=1)]
    beta = ParseResult(path="beta.py", language="python")
    beta.imports = [ParsedImport(module="alpha", names=["run"], start_line=1)]

    graph, _ = _build_graph({"alpha.py": alpha, "beta.py": beta})
    aggregator = HealthAggregator(graph)
    targets = aggregator.circular_import_targets()

    assert targets
    import_attrs = {
        target: graph.get_node(target)
        for target in targets
    }
    edges = [
        (source, target, graph.get_edge(source, target))
        for source, target, attrs in graph.iter_edges()
        if attrs.get("edge_type") == "imports" and graph.get_node(source).get("file_path") == "alpha.py"
    ]
    sequence = aggregator.build_sequence("alpha.py", [], edges, [], import_node_attrs=import_attrs)
    assert any(entry.base == NucleotideBase.G_ALERT for entry in sequence.sequence)
    assert sequence.health_score < 1.0
    assert "circular_import" in sequence.alerts


def test_health_score_uses_mocked_coverage_by_default() -> None:
    solo = ParseResult(path="solo.py", language="python")
    solo.symbols = [
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=1,
            end_line=2,
            qualified_name="run",
            complexity=5,
        )
    ]
    graph, _ = _build_graph({"solo.py": solo})
    health = HealthAggregator(graph).compute_module_health("solo.py")

    assert health.test_coverage == HealthAggregator.DEFAULT_COVERAGE
    assert health.zombie_node_rate == 0.0
    assert 0.0 <= health.health_score <= 1.0


def test_health_score_accepts_custom_coverage() -> None:
    solo = ParseResult(path="solo.py", language="python")
    solo.symbols = [
        ParsedSymbol(name="run", kind="function", start_line=1, end_line=2, qualified_name="run"),
    ]
    graph, _ = _build_graph({"solo.py": solo})
    aggregator = HealthAggregator(graph, test_coverage={"solo.py": 1.0})
    health = aggregator.compute_module_health("solo.py")

    assert health.test_coverage == 1.0
    assert health.health_score >= HealthAggregator(graph).compute_module_health("solo.py").health_score
