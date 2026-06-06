"""Intelligence report dataclass and (de)serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntelligenceReport:
    """Aggregated architectural intelligence for a codebase graph.

    Attributes:
        dead_code (list[str]): List of node IDs representing unused symbols.
        circular_dependencies (list[list[str]]): List of cycles (each a list of nodes).
        god_nodes (list[tuple[str, float]]): Nodes with unusually high in/out degrees.
        entry_points (list[str]): File and symbol IDs that act as entry points.
        orphan_modules (list[str]): Files that are not imported by and do not import others.
        complexity_rankings (list[tuple[str, int]]): Symbols ranked by cyclomatic complexity.
        churn_rankings (list[tuple[str, int]]): Nodes ranked by churn rate.
        cbo_rankings (list[tuple[str, int]]): Classes ranked by coupling between objects (CBO).
        lcom_rankings (list[tuple[str, int]]): Classes ranked by lack of cohesion in methods (LCOM).
        tightly_coupled_classes (list[tuple[str, int]]): Classes with high CBO (tight coupling).
    """

    dead_code: list[str] = field(default_factory=list)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    god_nodes: list[tuple[str, float]] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    orphan_modules: list[str] = field(default_factory=list)
    complexity_rankings: list[tuple[str, int]] = field(default_factory=list)
    churn_rankings: list[tuple[str, int]] = field(default_factory=list)
    cbo_rankings: list[tuple[str, int]] = field(default_factory=list)
    lcom_rankings: list[tuple[str, int]] = field(default_factory=list)
    tightly_coupled_classes: list[tuple[str, int]] = field(default_factory=list)


def report_to_dict(report: IntelligenceReport) -> dict:
    """Serialize an intelligence report for snapshot storage or exports."""
    return {
        "dead_code": report.dead_code,
        "circular_dependencies": report.circular_dependencies,
        "god_nodes": [
            {"node": node, "score": score}
            for node, score in report.god_nodes
        ],
        "entry_points": report.entry_points,
        "orphan_modules": report.orphan_modules,
        "complexity_rankings": [
            {"node": node, "complexity": value}
            for node, value in report.complexity_rankings
        ],
        "churn_rankings": [
            {"node": node, "churn": value}
            for node, value in report.churn_rankings
        ],
        "cbo_rankings": [
            {"node": node, "cbo": value}
            for node, value in report.cbo_rankings
        ],
        "lcom_rankings": [
            {"node": node, "lcom": value}
            for node, value in report.lcom_rankings
        ],
        "tightly_coupled_classes": [
            {"node": node, "cbo": value}
            for node, value in report.tightly_coupled_classes
        ],
    }


def report_from_dict(data: dict | None) -> IntelligenceReport | None:
    """Deserialize an intelligence report from snapshot storage."""
    if data is None:
        return None
    return IntelligenceReport(
        dead_code=list(data.get("dead_code", [])),
        circular_dependencies=[
            list(cycle) for cycle in data.get("circular_dependencies", [])
        ],
        god_nodes=[
            (str(item["node"]), float(item["score"]))
            for item in data.get("god_nodes", [])
        ],
        entry_points=list(data.get("entry_points", [])),
        orphan_modules=list(data.get("orphan_modules", [])),
        complexity_rankings=[
            (str(item["node"]), int(item["complexity"]))
            for item in data.get("complexity_rankings", [])
        ],
        churn_rankings=[
            (str(item["node"]), int(item["churn"]))
            for item in data.get("churn_rankings", [])
        ],
        cbo_rankings=[
            (str(item["node"]), int(item["cbo"]))
            for item in data.get("cbo_rankings", [])
        ],
        lcom_rankings=[
            (str(item["node"]), int(item["lcom"]))
            for item in data.get("lcom_rankings", [])
        ],
        tightly_coupled_classes=[
            (str(item["node"]), int(item["cbo"]))
            for item in data.get("tightly_coupled_classes", [])
        ],
    )
