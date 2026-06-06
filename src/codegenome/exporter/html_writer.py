"""Interactive HTML visualization writer."""

from __future__ import annotations

import html
import json
from pathlib import Path

from codegenome.exporter.context import ExportContext
from codegenome.exporter.statistics import GraphStatistics
from codegenome.resources import copy_html_asset, render_template


class HtmlWriter:
    """Render the vis-network HTML viewer and copy its bundled assets."""

    def write(self, ctx: ExportContext, output_path: Path) -> Path:
        stats = ctx.compute_statistics()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        bundled_js = copy_html_asset(
            "vis-network.min.js",
            output_path.parent / "vis-network.min.js",
        )
        copy_html_asset("graph-viewer.css", output_path.parent / "graph-viewer.css")
        copy_html_asset("graph-viewer.js", output_path.parent / "graph-viewer.js")
        script_src = (
            "vis-network.min.js"
            if bundled_js is not None
            else "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"
        )
        output_path.write_text(
            self._render(ctx, stats, script_src=script_src),
            encoding="utf-8",
        )
        return output_path

    def _render(
        self,
        ctx: ExportContext,
        stats: GraphStatistics,
        *,
        script_src: str,
        live_json_url: str | None = None,
    ) -> str:
        config = {
            "workspaceName": ctx.workspace_name,
            "liveJsonUrl": live_json_url,
            "livePollMs": 1500,
            "maxFileNodes": 200,
        }
        return render_template(
            "graph.html.j2",
            workspace_name=html.escape(ctx.workspace_name),
            script_src=script_src,
            graph_json=json.dumps(ctx.json_payload()),
            stats=stats,
            config_json=json.dumps(config),
        )
