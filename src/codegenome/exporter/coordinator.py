"""GraphExporter coordinator delegating to format-specific writers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from codegenome.graph_api import Graph
from codegenome.intelligence import IntelligenceReport, report_to_dict
from codegenome.exporter.context import ExportContext
from codegenome.exporter.cypher_writer import CypherWriter
from codegenome.exporter.graphml_writer import GraphmlWriter
from codegenome.exporter.html_writer import HtmlWriter
from codegenome.exporter.json_writer import JsonWriter
from codegenome.exporter.markdown_writer import MarkdownWriter
from codegenome.exporter.obsidian_writer import ObsidianWriter
from codegenome.exporter.statistics import GraphStatistics, SUPPORTED_FORMATS

LOG = logging.getLogger(__name__)


@dataclass
class GraphExporter:
    """Serialize CodeGenome graphs and intelligence into multiple formats.

    Attributes:
        graph (Graph): The graph instance to be exported.
        report (IntelligenceReport | None): Optional intelligence report for augmented exports.
        workspace_name (str): The name of the workspace being exported.
    """

    graph: Graph
    report: IntelligenceReport | None = None
    workspace_name: str = "workspace"

    @property
    def context(self) -> ExportContext:
        """Build the shared export context from the current state."""
        return ExportContext(
            graph=self.graph,
            report=self.report,
            workspace_name=self.workspace_name,
        )

    def compute_statistics(self) -> GraphStatistics:
        """Compute aggregate graph statistics."""
        return self.context.compute_statistics()

    def export_json(self, output_path: Path) -> Path:
        """Export the graph as JSON."""
        return JsonWriter().write(self.context, output_path)

    def export_html(self, output_path: Path) -> Path:
        """Export the graph as an interactive HTML visualization."""
        return HtmlWriter().write(self.context, output_path)

    def export_graphml(self, output_path: Path) -> Path:
        """Export the graph to GraphML."""
        return GraphmlWriter().write(self.context, output_path)

    def export_cypher(self, output_path: Path) -> Path:
        """Export the graph as Cypher statements."""
        return CypherWriter().write(self.context, output_path)

    def export_markdown(self, output_path: Path) -> Path:
        """Export a Markdown report."""
        return MarkdownWriter().write(self.context, output_path)

    def export_obsidian(self, output_dir: Path) -> Path:
        """Export the graph as an Obsidian vault."""
        return ObsidianWriter().write(self.context, output_dir)

    def export_all(
        self,
        output_dir: Path,
        formats: Iterable[str] | None = None,
    ) -> dict[str, Path]:
        """Export the graph into multiple selected formats.

        Args:
            output_dir (Path): The destination directory for all export files.
            formats (Iterable[str] | None): Format strings to export. If None,
                all supported formats are exported.

        Returns:
            dict[str, Path]: Mapping of format name to generated path.

        Raises:
            ValueError: If an unsupported format is provided.
        """
        selected = {fmt.lower() for fmt in (formats or SUPPORTED_FORMATS)}
        unknown = selected - SUPPORTED_FORMATS
        if unknown:
            raise ValueError(f"Unsupported export formats: {', '.join(sorted(unknown))}")

        output_dir.mkdir(parents=True, exist_ok=True)
        ctx = self.context
        paths: dict[str, Path] = {}

        if "json" in selected:
            paths["json"] = JsonWriter().write(ctx, output_dir / "graph.json")
        if "html" in selected:
            paths["html"] = HtmlWriter().write(ctx, output_dir / "graph.html")
        if "graphml" in selected:
            paths["graphml"] = GraphmlWriter().write(ctx, output_dir / "graph.graphml")
        if "cypher" in selected:
            paths["cypher"] = CypherWriter().write(ctx, output_dir / "graph.cypher")
        if "markdown" in selected:
            paths["markdown"] = MarkdownWriter().write(ctx, output_dir / "report.md")
        if "obsidian" in selected:
            paths["obsidian"] = ObsidianWriter().write(
                ctx, output_dir / "obsidian-vault"
            )

        return paths

    @staticmethod
    def report_to_dict(report: IntelligenceReport | None) -> dict[str, Any] | None:
        """Serialize an intelligence report for JSON/HTML exports."""
        if report is None:
            return None
        return report_to_dict(report)
