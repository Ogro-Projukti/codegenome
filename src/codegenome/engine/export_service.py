"""Graph artifact export service."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from codegenome.exporter import GraphExporter
from codegenome.intelligence import GraphIntelligence, IntelligenceReport

from codegenome.engine.context import EngineContext


class ExportService:
    """Render the current graph into the configured export formats."""

    def __init__(self, ctx: EngineContext) -> None:
        self.ctx = ctx

    def run_exports(
        self,
        exporter: GraphExporter,
        formats: Iterable[str] | None = None,
    ) -> dict[str, Path]:
        """Export all selected formats plus the canonical graph.json."""
        ctx = self.ctx
        selected = tuple(formats) if formats is not None else ctx.config.export_formats
        paths = exporter.export_all(ctx.export_dir, selected)
        json_path = exporter.export_json(ctx.graph_json_path)
        paths["graph_json"] = json_path
        return paths

    def run_exports_bounded(
        self,
        snapshot_id: int,
        analysis_graph: object,
        report: IntelligenceReport,
    ) -> dict[str, Path]:
        """Export artifacts after a bounded surgical update without a full reload."""
        ctx = self.ctx
        selected = tuple(ctx.config.export_formats)
        paths: dict[str, Path] = {}
        if "json" in selected or not selected:
            live_json_path = ctx.export_dir / "graph.json"
            paths["graph_json"] = ctx.timeline.export_snapshot_json(
                snapshot_id,
                live_json_path,
            )
            if live_json_path != ctx.graph_json_path:
                ctx.timeline.export_snapshot_json(snapshot_id, ctx.graph_json_path)
        if "html" in selected:
            paths["html"] = ctx.timeline.export_snapshot_html(
                snapshot_id,
                ctx.export_dir / "graph.html",
                workspace_name=ctx.workspace.name,
                report=report,
                graph_json_relative="graph.json",
            )
        return paths

    def export(
        self,
        formats: Iterable[str] | None = None,
        *,
        report: IntelligenceReport | None = None,
    ) -> dict[str, Path]:
        """Export the already-built graph, computing a report if needed.

        Raises:
            RuntimeError: If called before a graph has been built.
        """
        ctx = self.ctx
        graph = ctx.builder.graph
        if graph.number_of_nodes() == 0:
            raise RuntimeError("Cannot export before building a graph")

        if report is None:
            intelligence = GraphIntelligence(graph)
            intelligence.annotate_coupling_metrics()
            report = intelligence.analyze()

        exporter = GraphExporter(
            graph,
            report=report,
            workspace_name=ctx.workspace.name,
        )
        return self.run_exports(exporter, formats=formats)
