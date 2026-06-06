"""Cypher writer for Neo4j import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codegenome.exporter.context import ExportContext


class CypherWriter:
    """Emit CREATE/MATCH statements for nodes and edges."""

    def write(self, ctx: ExportContext, output_path: Path) -> Path:
        lines = [
            "// CodeGenome graph export for Neo4j",
            f"// workspace: {ctx.workspace_name}",
            "",
        ]
        for node_id, attrs in ctx.graph.iter_nodes():
            props = self._properties({"id": node_id, **attrs})
            label = str(attrs.get("node_type", "Node")).title().replace("_", "")
            lines.append(f"CREATE (:{label} {props});")

        for source, target, attrs in ctx.graph.iter_edges():
            edge_type = str(attrs.get("edge_type", "RELATED")).upper()
            props = self._properties(attrs)
            lines.append(
                "MATCH (a {id: "
                f"{self._literal(source)}"
                "}), (b {id: "
                f"{self._literal(target)}"
                f"}}) CREATE (a)-[:{edge_type} {props}]->(b);"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output_path

    def _properties(self, attrs: dict[str, Any]) -> str:
        pairs = []
        for key, value in sorted(attrs.items()):
            if value is None:
                continue
            pairs.append(f"{key}: {self._literal(value)}")
        return "{" + ", ".join(pairs) + "}"

    def _literal(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
