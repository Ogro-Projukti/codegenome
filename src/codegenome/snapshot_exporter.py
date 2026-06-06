"""Export snapshots straight from the persistence layer to JSON/HTML.

This keeps export/presentation concerns out of :class:`GraphTimeline` (the
persistence layer). The exporter reads snapshot rows via the timeline's
connection and renders artifacts using the HTML asset/template helpers.
"""

from __future__ import annotations

import html as html_module
import json
from pathlib import Path
from typing import TYPE_CHECKING

from codegenome.exporter import GraphExporter
from codegenome.intelligence import IntelligenceReport
from codegenome.resources import copy_html_asset, render_template

if TYPE_CHECKING:
    from codegenome.timeline import GraphTimeline


class SnapshotExporter:
    """Render stored snapshots to ``graph.json`` and ``graph.html``."""

    def __init__(self, timeline: "GraphTimeline") -> None:
        self._timeline = timeline
        self._conn = timeline.connection

    def export_json(self, snapshot_id: int, output_path: Path) -> Path:
        """Write graph.json for a snapshot by reading SQLite rows directly."""
        node_rows = self._conn.execute(
            "SELECT node_id, attrs_json FROM graph_nodes WHERE snapshot_id = ? ORDER BY node_id",
            (snapshot_id,),
        ).fetchall()
        edge_rows = self._conn.execute(
            """
            SELECT source_id, target_id, attrs_json
            FROM graph_edges
            WHERE snapshot_id = ?
            ORDER BY source_id, target_id
            """,
            (snapshot_id,),
        ).fetchall()

        nodes = [
            {"id": row["node_id"], **json.loads(row["attrs_json"])}
            for row in node_rows
        ]
        edges = [
            {
                "source": row["source_id"],
                "target": row["target_id"],
                **json.loads(row["attrs_json"]),
            }
            for row in edge_rows
        ]
        info = self._conn.execute(
            """
            SELECT snapshot_id, created_at, label, node_count, edge_count
            FROM snapshots
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        stats = self._timeline.compute_snapshot_statistics(snapshot_id)
        payload = {
            "snapshot_id": snapshot_id,
            "label": info["label"] if info else None,
            "node_count": info["node_count"] if info else len(nodes),
            "edge_count": info["edge_count"] if info else len(edges),
            "metadata": {
                "statistics": stats.__dict__,
            },
            "nodes": nodes,
            "edges": edges,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return output_path

    def export_html(
        self,
        snapshot_id: int,
        output_path: Path,
        *,
        workspace_name: str,
        report: IntelligenceReport | None = None,
        graph_json_relative: str = "graph.json",
    ) -> Path:
        """Write graph.html that loads node data from a sidecar JSON file."""
        stats = self._timeline.compute_snapshot_statistics(snapshot_id)
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
        graph_payload = {
            "metadata": {
                "workspace": workspace_name,
                "statistics": stats.__dict__,
            },
            "nodes": [],
            "edges": [],
            "intelligence": GraphExporter.report_to_dict(report),
        }
        config = {
            "workspaceName": workspace_name,
            "liveJsonUrl": graph_json_relative,
            "livePollMs": 1500,
            "maxFileNodes": 200,
        }
        output_path.write_text(
            render_template(
                "graph.html.j2",
                workspace_name=html_module.escape(workspace_name),
                script_src=script_src,
                graph_json=json.dumps(graph_payload),
                stats=stats,
                config_json=json.dumps(config),
            ),
            encoding="utf-8",
        )
        return output_path
