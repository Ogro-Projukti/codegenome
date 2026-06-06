"""Metric-based analyzers: god nodes, complexity, and churn rankings."""

from __future__ import annotations

import statistics

from codegenome.coupling_metrics import CLASS_KINDS
from codegenome.intelligence.context import AnalysisContext


class GodNodeAnalyzer:
    """Identify nodes with excessively high degree / coupling (god nodes)."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def detect(self, *, include_generated: bool = False) -> list[tuple[str, float]]:
        """Return (node, score) pairs above the god-node threshold, descending."""
        ctx = self.ctx
        graph = ctx.graph
        coupling_metrics = ctx.coupling_analyzer().compute_all()
        scores: dict[str, float] = {}
        for node, attrs in graph.iter_nodes():
            if attrs.get("node_type") not in {"file", "symbol"}:
                continue
            if not include_generated and ctx.classifier.is_generated_or_vendor(attrs):
                continue
            in_degree = graph.in_degree(node)
            out_degree = graph.out_degree(node)

            if ctx.registry and attrs.get("node_type") == "symbol":
                fqn = attrs.get("qualified_name") or attrs.get("name")
                if fqn:
                    in_degree += len(ctx.registry.get_dependents(fqn))

            score = float(in_degree + out_degree)
            if str(attrs.get("kind", "")) in CLASS_KINDS:
                class_metrics = coupling_metrics.get(node)
                if class_metrics is not None:
                    score = max(score, float(class_metrics.cbo + class_metrics.lcom))

            scores[node] = score

        if not scores:
            return []

        values = list(scores.values())
        if len(values) == 1:
            node, score = next(iter(scores.items()))
            return [(node, score)]

        mean = statistics.fmean(values)
        try:
            spread = statistics.pstdev(values)
        except statistics.StatisticsError:
            spread = 0.0
        threshold = mean + ctx.god_node_stddevs * spread
        return sorted(
            ((node, score) for node, score in scores.items() if score >= threshold),
            key=lambda item: (-item[1], item[0]),
        )


class RankingAnalyzer:
    """Rank symbols/nodes by cyclomatic complexity and churn."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def complexity_rankings(
        self,
        *,
        include_generated: bool = False,
    ) -> list[tuple[str, int]]:
        """Rank symbols by descending cyclomatic complexity."""
        ranked: list[tuple[str, int]] = []
        for node, attrs in self.ctx.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            if not include_generated and self.ctx.classifier.is_generated_or_vendor(attrs):
                continue
            complexity = attrs.get("complexity")
            if complexity is None:
                continue
            ranked.append((node, int(complexity)))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    def churn_rankings(self) -> list[tuple[str, int]]:
        """Rank nodes by descending churn rate."""
        ranked: list[tuple[str, int]] = []
        for node, attrs in self.ctx.graph.iter_nodes():
            if attrs.get("node_type") not in {"file", "symbol"}:
                continue
            churn = int(attrs.get("churn", 0))
            if churn <= 0:
                continue
            ranked.append((node, churn))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked
