"""Markdown report writer."""

from __future__ import annotations

from pathlib import Path

from codegenome.exporter.context import ExportContext
from codegenome.intelligence import IntelligenceReport
from codegenome.resources import render_template


class MarkdownWriter:
    """Render the statistics and intelligence summary as Markdown."""

    def write(self, ctx: ExportContext, output_path: Path) -> Path:
        stats = ctx.compute_statistics()
        report = ctx.report or IntelligenceReport()
        rendered = render_template(
            "report.md.j2",
            workspace_name=ctx.workspace_name,
            stats=stats,
            report=report,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        return output_path
