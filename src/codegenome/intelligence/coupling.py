"""Coupling analyzer wrapping CBO/LCOM metrics with graph-aware filtering."""

from __future__ import annotations

from codegenome.intelligence.context import AnalysisContext


class CouplingAnalyzer:
    """Expose CBO/LCOM rankings, per-class metrics, and node annotation."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def cbo_rankings(self, *, include_generated: bool = False) -> list[tuple[str, int]]:
        """Rank classes by descending coupling between objects (CBO)."""
        return self._filtered(
            self.ctx.coupling_analyzer().cbo_rankings(),
            include_generated=include_generated,
        )

    def lcom_rankings(self, *, include_generated: bool = False) -> list[tuple[str, int]]:
        """Rank classes by descending lack of cohesion in methods (LCOM)."""
        return self._filtered(
            self.ctx.coupling_analyzer().lcom_rankings(),
            include_generated=include_generated,
        )

    def tightly_coupled_classes(
        self,
        *,
        include_generated: bool = False,
        min_cbo: int = 5,
    ) -> list[tuple[str, int]]:
        """Return classes with CBO at or above ``min_cbo``."""
        return self._filtered(
            self.ctx.coupling_analyzer().tightly_coupled_classes(min_cbo=min_cbo),
            include_generated=include_generated,
        )

    def coupling_metrics(
        self,
        *,
        include_generated: bool = False,
    ) -> list[dict[str, object]]:
        """Return per-class CBO and LCOM metrics as dict rows."""
        graph = self.ctx.graph
        classifier = self.ctx.classifier
        rows: list[dict[str, object]] = []
        for class_id, metrics in self.ctx.coupling_analyzer().compute_all().items():
            attrs = graph.get_node(class_id) if graph.has_node(class_id) else {}
            if not include_generated and classifier.is_generated_or_vendor(attrs):
                continue
            rows.append(
                {
                    "node_id": class_id,
                    "qualified_name": metrics.qualified_name,
                    "cbo": metrics.cbo,
                    "lcom": metrics.lcom,
                    "method_count": metrics.method_count,
                }
            )
        rows.sort(key=lambda row: (-int(row["cbo"]), -int(row["lcom"]), str(row["node_id"])))
        return rows

    def annotate_coupling_metrics(self) -> None:
        """Write computed CBO/LCOM values onto class symbol nodes."""
        graph = self.ctx.graph
        for class_id, metrics in self.ctx.coupling_analyzer().compute_all().items():
            if graph.has_node(class_id):
                graph.set_node_attr(class_id, "cbo", metrics.cbo)
                graph.set_node_attr(class_id, "lcom", metrics.lcom)

    def _filtered(
        self,
        rankings: list[tuple[str, int]],
        *,
        include_generated: bool,
    ) -> list[tuple[str, int]]:
        if include_generated:
            return rankings
        graph = self.ctx.graph
        classifier = self.ctx.classifier
        filtered: list[tuple[str, int]] = []
        for node_id, score in rankings:
            attrs = graph.get_node(node_id) if graph.has_node(node_id) else {}
            if classifier.is_generated_or_vendor(attrs):
                continue
            filtered.append((node_id, score))
        return filtered
