"""GraphML writer backed by networkx."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from codegenome.exporter.context import ExportContext


class GraphmlWriter:
    """Serialize the graph to GraphML with attribute sanitization."""

    def write(self, ctx: ExportContext, output_path: Path) -> Path:
        export_graph = nx.DiGraph()
        for node_id, attrs in ctx.graph.iter_nodes():
            export_graph.add_node(node_id, **self._attrs(attrs))
        for source, target, attrs in ctx.graph.iter_edges():
            export_graph.add_edge(source, target, **self._attrs(attrs))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(export_graph, output_path)
        return output_path

    def _attrs(self, attrs: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in attrs.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key] = value
            else:
                sanitized[key] = json.dumps(value, sort_keys=True)
        return sanitized
