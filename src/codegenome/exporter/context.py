"""Shared export context used by all format writers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from codegenome.graph_api import Graph
from codegenome.intelligence import IntelligenceReport, report_to_dict
from codegenome.exporter.statistics import GraphStatistics


@dataclass
class ExportContext:
    """Carry the graph, report, and shared serialization helpers to writers."""

    graph: Graph
    report: IntelligenceReport | None = None
    workspace_name: str = "workspace"

    def compute_statistics(self) -> GraphStatistics:
        """Compute aggregate node-type counts and language distribution."""
        languages: dict[str, int] = {}
        file_count = symbol_count = import_count = external_count = 0
        communities: set[int] = set()
        bridge_count = 0

        for _, attrs in self.graph.iter_nodes():
            node_type = attrs.get("node_type")
            if node_type == "file":
                file_count += 1
                language = attrs.get("language")
                if language:
                    languages[str(language)] = languages.get(str(language), 0) + 1
            elif node_type == "symbol":
                symbol_count += 1
            elif node_type == "import":
                import_count += 1
            elif node_type == "external":
                external_count += 1

            community_id = attrs.get("community_id")
            if community_id is not None:
                communities.add(int(community_id))
            if attrs.get("is_bridge"):
                bridge_count += 1

        return GraphStatistics(
            node_count=self.graph.number_of_nodes(),
            edge_count=self.graph.number_of_edges(),
            file_count=file_count,
            symbol_count=symbol_count,
            import_count=import_count,
            external_count=external_count,
            community_count=len(communities),
            bridge_count=bridge_count,
            languages=dict(sorted(languages.items())),
        )

    def json_payload(self) -> dict[str, Any]:
        """Build the canonical JSON payload (nodes, edges, intelligence)."""
        stats = self.compute_statistics()
        return {
            "metadata": {
                "workspace": self.workspace_name,
                "statistics": stats.__dict__,
            },
            "nodes": [
                {"id": node_id, **self.json_safe(attrs)}
                for node_id, attrs in self.graph.iter_nodes()
            ],
            "edges": [
                {
                    "source": source,
                    "target": target,
                    **self.json_safe(edge_attrs),
                }
                for source, target, edge_attrs in self.graph.iter_edges()
            ],
            "intelligence": self.report_dict(),
        }

    def report_dict(self) -> dict[str, Any] | None:
        """Serialize the intelligence report, or None when absent."""
        if self.report is None:
            return None
        return report_to_dict(self.report)

    def json_safe(self, value: dict[str, Any]) -> dict[str, Any]:
        """Round-trip a mapping through JSON to drop non-serializable values."""
        return json.loads(json.dumps(value, default=str))

    def node_label(self, node_id: str, attrs: dict[str, Any]) -> str:
        """Return a human-friendly label for a node."""
        node_type = attrs.get("node_type")
        if node_type == "file":
            return str(attrs.get("file_path") or node_id)
        if node_type == "symbol":
            return str(attrs.get("qualified_name") or attrs.get("name") or node_id)
        if node_type == "import":
            return str(attrs.get("module") or node_id)
        return str(attrs.get("name") or node_id)
