"""Tests for CBO and LCOM coupling metrics."""

from __future__ import annotations

from codegenome.builder import GraphBuilder, symbol_node_id
from codegenome.coupling_metrics import CouplingMetricsAnalyzer
from codegenome.intelligence import GraphIntelligence
from codegenome.parser import ParseResult, ParsedCall, ParsedInheritance, ParsedSymbol
from codegenome.scanner import FileRecord, ScanResult


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


def test_coupling_metrics_compute_cbo_from_inheritance_and_calls() -> None:
    service = ParseResult(path="service.py", language="python")
    service.symbols = [
        ParsedSymbol(
            name="Service",
            kind="class",
            start_line=1,
            end_line=10,
            qualified_name="Service",
        ),
        ParsedSymbol(
            name="run",
            kind="function",
            start_line=3,
            end_line=5,
            qualified_name="Service.run",
            instance_attrs=frozenset({"repo"}),
        ),
    ]
    service.inheritance = [ParsedInheritance(class_name="Service", base="BaseRepo", line=1)]
    service.calls = [ParsedCall(caller="Service.run", callee="repo.save", line=4)]

    repo = ParseResult(path="repo.py", language="python")
    repo.symbols = [
        ParsedSymbol(
            name="BaseRepo",
            kind="class",
            start_line=1,
            end_line=5,
            qualified_name="BaseRepo",
        ),
        ParsedSymbol(
            name="save",
            kind="function",
            start_line=2,
            end_line=3,
            qualified_name="BaseRepo.save",
        ),
    ]

    graph = _build_graph({"service.py": service, "repo.py": repo})
    metrics = CouplingMetricsAnalyzer(graph).compute_all()

    service_id = symbol_node_id("service.py", "Service")
    repo_id = symbol_node_id("repo.py", "BaseRepo")

    assert metrics[service_id].cbo >= 1
    assert metrics[repo_id].cbo == 0


def test_coupling_metrics_compute_lcom_from_shared_instance_attrs() -> None:
    parse = ParseResult(path="worker.py", language="python")
    parse.symbols = [
        ParsedSymbol(
            name="Worker",
            kind="class",
            start_line=1,
            end_line=20,
            qualified_name="Worker",
        ),
        ParsedSymbol(
            name="load",
            kind="function",
            start_line=3,
            end_line=5,
            qualified_name="Worker.load",
            instance_attrs=frozenset({"cache"}),
        ),
        ParsedSymbol(
            name="save",
            kind="function",
            start_line=7,
            end_line=9,
            qualified_name="Worker.save",
            instance_attrs=frozenset({"cache"}),
        ),
        ParsedSymbol(
            name="notify",
            kind="function",
            start_line=11,
            end_line=13,
            qualified_name="Worker.notify",
            instance_attrs=frozenset({"logger"}),
        ),
    ]

    graph = _build_graph({"worker.py": parse})
    worker_id = symbol_node_id("worker.py", "Worker")
    metrics = CouplingMetricsAnalyzer(graph).compute_all()[worker_id]

    assert metrics.method_count == 3
    assert metrics.lcom == 1


def test_intelligence_reports_coupling_rankings_and_god_class_signal() -> None:
    parse = ParseResult(path="hub.py", language="python")
    parse.symbols = [
        ParsedSymbol(
            name="Hub",
            kind="class",
            start_line=1,
            end_line=30,
            qualified_name="Hub",
        ),
        *[
            ParsedSymbol(
                name=f"method_{index}",
                kind="function",
                start_line=index + 2,
                end_line=index + 3,
                qualified_name=f"Hub.method_{index}",
                instance_attrs=frozenset({f"field_{index}"}),
            )
            for index in range(4)
        ],
    ]

    graph = _build_graph({"hub.py": parse})
    intelligence = GraphIntelligence(graph)
    intelligence.annotate_coupling_metrics()
    report = intelligence.analyze()

    hub_id = symbol_node_id("hub.py", "Hub")
    assert report.lcom_rankings[0][0] == hub_id
    assert graph.get_node(hub_id)["lcom"] == report.lcom_rankings[0][1]
    assert any(node_id == hub_id for node_id, _ in report.god_nodes)
