"""Export Watcher graphs to JSON, HTML, GraphML, Cypher, Markdown, and Obsidian."""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

from codegenome.graph_api import Graph
from codegenome.intelligence import IntelligenceReport
from codegenome.resources import copy_html_asset, render_template

LOG = logging.getLogger(__name__)

COMMUNITY_PALETTE = [
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
    "#9c755f",
    "#bab0ac",
]

SUPPORTED_FORMATS = frozenset(
    {"json", "html", "graphml", "cypher", "markdown", "obsidian"}
)


@dataclass(frozen=True)
class GraphStatistics:
    """High-level graph metrics for reports and exports."""

    node_count: int
    edge_count: int
    file_count: int
    symbol_count: int
    import_count: int
    external_count: int
    community_count: int
    bridge_count: int
    languages: dict[str, int] = field(default_factory=dict)


@dataclass
class GraphExporter:
    """Serialize Watcher graphs and intelligence into multiple formats."""

    graph: Graph
    report: IntelligenceReport | None = None
    workspace_name: str = "workspace"

    def compute_statistics(self) -> GraphStatistics:
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

    def export_json(self, output_path: Path) -> Path:
        payload = self._json_payload()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(output_path)
        return output_path

    def export_html(self, output_path: Path) -> Path:
        stats = self.compute_statistics()
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
            self._render_html(stats, script_src=script_src),
            encoding="utf-8",
        )
        return output_path

    def export_graphml(self, output_path: Path) -> Path:
        export_graph = self._graphml_graph()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(export_graph, output_path)
        return output_path

    def export_cypher(self, output_path: Path) -> Path:
        lines = [
            "// Watcher graph export for Neo4j",
            f"// workspace: {self.workspace_name}",
            "",
        ]
        for node_id, attrs in self.graph.iter_nodes():
            props = self._cypher_properties({"id": node_id, **attrs})
            label = str(attrs.get("node_type", "Node")).title().replace("_", "")
            lines.append(f"CREATE (:{label} {props});")

        for source, target, attrs in self.graph.iter_edges():
            edge_type = str(attrs.get("edge_type", "RELATED")).upper()
            props = self._cypher_properties(attrs)
            lines.append(
                "MATCH (a {id: "
                f"{self._cypher_literal(source)}"
                "}), (b {id: "
                f"{self._cypher_literal(target)}"
                f"}}) CREATE (a)-[:{edge_type} {props}]->(b);"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output_path

    def export_markdown(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self._render_markdown(), encoding="utf-8")
        return output_path

    def export_obsidian(self, output_dir: Path) -> Path:
        vault_root = output_dir
        files_dir = vault_root / "Files"
        symbols_dir = vault_root / "Symbols"
        files_dir.mkdir(parents=True, exist_ok=True)
        symbols_dir.mkdir(parents=True, exist_ok=True)

        file_links: list[str] = []
        for node_id, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "file":
                continue
            path = str(attrs.get("file_path", node_id))
            note_name = self._obsidian_name(path)
            file_links.append(f"- [[Files/{note_name}|{path}]]")
            self._write_obsidian_file_note(files_dir / f"{note_name}.md", path, node_id)

        for node_id, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            qname = str(attrs.get("qualified_name") or attrs.get("name") or node_id)
            note_name = self._obsidian_name(qname)
            file_path = str(attrs.get("file_path", ""))
            file_note = self._obsidian_name(file_path) if file_path else None
            body = [
                f"# {qname}",
                "",
                f"- kind: `{attrs.get('kind', 'unknown')}`",
                f"- file: [[Files/{file_note}|{file_path}]]" if file_note else "",
                f"- complexity: {attrs.get('complexity', 'n/a')}",
                f"- churn: {attrs.get('churn', 0)}",
            ]
            symbols_dir.joinpath(f"{note_name}.md").write_text(
                "\n".join(line for line in body if line) + "\n",
                encoding="utf-8",
            )

        index_lines = [
            "# Watcher Graph Vault",
            "",
            f"Workspace: `{self.workspace_name}`",
            "",
            "## Files",
            "",
            *sorted(file_links),
            "",
            "## Intelligence",
            "",
        ]
        if self.report:
            index_lines.extend(
                [
                    f"- Dead code nodes: {len(self.report.dead_code)}",
                    f"- God nodes: {len(self.report.god_nodes)}",
                    f"- Circular dependency groups: {len(self.report.circular_dependencies)}",
                ]
            )
        vault_root.joinpath("Watcher Index.md").write_text(
            "\n".join(index_lines) + "\n",
            encoding="utf-8",
        )
        return vault_root

    def export_all(
        self,
        output_dir: Path,
        formats: Iterable[str] | None = None,
    ) -> dict[str, Path]:
        selected = {fmt.lower() for fmt in (formats or SUPPORTED_FORMATS)}
        unknown = selected - SUPPORTED_FORMATS
        if unknown:
            raise ValueError(f"Unsupported export formats: {', '.join(sorted(unknown))}")

        output_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}

        if "json" in selected:
            paths["json"] = self.export_json(output_dir / "graph.json")
        if "html" in selected:
            paths["html"] = self.export_html(output_dir / "graph.html")
        if "graphml" in selected:
            paths["graphml"] = self.export_graphml(output_dir / "graph.graphml")
        if "cypher" in selected:
            paths["cypher"] = self.export_cypher(output_dir / "graph.cypher")
        if "markdown" in selected:
            paths["markdown"] = self.export_markdown(output_dir / "report.md")
        if "obsidian" in selected:
            paths["obsidian"] = self.export_obsidian(output_dir / "obsidian-vault")

        return paths

    def _json_payload(self) -> dict[str, Any]:
        stats = self.compute_statistics()
        return {
            "metadata": {
                "workspace": self.workspace_name,
                "statistics": stats.__dict__,
            },
            "nodes": [
                {"id": node_id, **self._json_safe(attrs)}
                for node_id, attrs in self.graph.iter_nodes()
            ],
            "edges": [
                {
                    "source": source,
                    "target": target,
                    **self._json_safe(edge_attrs),
                }
                for source, target, edge_attrs in self.graph.iter_edges()
            ],
            "intelligence": self._report_dict(),
        }

    def _report_dict(self) -> dict[str, Any] | None:
        if self.report is None:
            return None
        return {
            "dead_code": self.report.dead_code,
            "circular_dependencies": self.report.circular_dependencies,
            "god_nodes": [
                {"node": node, "score": score}
                for node, score in self.report.god_nodes
            ],
            "entry_points": self.report.entry_points,
            "orphan_modules": self.report.orphan_modules,
            "complexity_rankings": [
                {"node": node, "complexity": value}
                for node, value in self.report.complexity_rankings[:25]
            ],
            "churn_rankings": [
                {"node": node, "churn": value}
                for node, value in self.report.churn_rankings[:25]
            ],
        }

    def _render_markdown(self) -> str:
        stats = self.compute_statistics()
        report = self.report or IntelligenceReport()
        return render_template(
            "report.md.j2",
            workspace_name=self.workspace_name,
            stats=stats,
            report=report,
        )

    def _render_html(
        self,
        stats: GraphStatistics,
        *,
        script_src: str,
        live_json_url: str | None = None,
    ) -> str:
        config = {
            "workspaceName": self.workspace_name,
            "liveJsonUrl": live_json_url,
            "livePollMs": 1500,
            "maxFileNodes": 200,
        }
        return render_template(
            "graph.html.j2",
            workspace_name=html.escape(self.workspace_name),
            script_src=script_src,
            graph_json=json.dumps(self._json_payload()),
            stats=stats,
            config_json=json.dumps(config),
        )

    def _vis_payload(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        vis_nodes: list[dict[str, Any]] = []
        for node_id, attrs in self.graph.iter_nodes():
            community_id = attrs.get("community_id")
            color = COMMUNITY_PALETTE[int(community_id) % len(COMMUNITY_PALETTE)] if community_id is not None else "#888888"
            label = self._node_label(node_id, attrs)
            vis_nodes.append(
                {
                    "id": node_id,
                    "label": label,
                    "title": node_id,
                    "color": color,
                    "raw": self._json_safe(attrs),
                }
            )

        vis_edges = [
            {
                "from": source,
                "to": target,
                "label": str(edge_attrs.get("edge_type", "")),
                "arrows": "to",
            }
            for source, target, edge_attrs in self.graph.iter_edges()
        ]
        return vis_nodes, vis_edges

    def _graphml_graph(self) -> nx.DiGraph:
        export_graph = nx.DiGraph()
        for node_id, attrs in self.graph.iter_nodes():
            export_graph.add_node(node_id, **self._graphml_attrs(attrs))
        for source, target, attrs in self.graph.iter_edges():
            export_graph.add_edge(source, target, **self._graphml_attrs(attrs))
        return export_graph

    def _graphml_attrs(self, attrs: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in attrs.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key] = value
            else:
                sanitized[key] = json.dumps(value, sort_keys=True)
        return sanitized

    def _write_obsidian_file_note(self, path: Path, file_path: str, node_id: str) -> None:
        attrs = self.graph.get_node(node_id) if self.graph.has_node(node_id) else {}
        imports: list[str] = []
        calls: list[str] = []
        symbols: list[str] = []

        for _, target, edge_attrs in self.graph.out_edges(node_id):
            target_attrs = self.graph.get_node(target) if self.graph.has_node(target) else {}
            edge_type = edge_attrs.get("edge_type")
            if edge_type == "contains" and target_attrs.get("node_type") == "symbol":
                qname = target_attrs.get("qualified_name") or target_attrs.get("name")
                symbols.append(f"- [[Symbols/{self._obsidian_name(str(qname))}|{qname}]]")
            elif edge_type == "imports":
                module = target_attrs.get("module")
                if module:
                    imports.append(f"- `{module}`")

        for source, _, edge_attrs in self.graph.in_edges(node_id):
            if edge_attrs.get("edge_type") != "calls":
                continue
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            if source_attrs.get("node_type") == "symbol":
                qname = source_attrs.get("qualified_name") or source_attrs.get("name")
                calls.append(f"- [[Symbols/{self._obsidian_name(str(qname))}|{qname}]]")

        body = [
            f"# {file_path}",
            "",
            f"- language: `{attrs.get('language', 'unknown')}`",
            f"- churn: {attrs.get('churn', 0)}",
            "",
            "## Symbols",
            "",
            *(symbols or ["_No symbols parsed._"]),
            "",
            "## Imports",
            "",
            *(imports or ["_No imports detected._"]),
            "",
            "## Incoming calls",
            "",
            *(calls or ["_No cross-file callers detected._"]),
            "",
        ]
        path.write_text("\n".join(body), encoding="utf-8")

    def _node_label(self, node_id: str, attrs: dict[str, Any]) -> str:
        node_type = attrs.get("node_type")
        if node_type == "file":
            return str(attrs.get("file_path") or node_id)
        if node_type == "symbol":
            return str(attrs.get("qualified_name") or attrs.get("name") or node_id)
        if node_type == "import":
            return str(attrs.get("module") or node_id)
        return str(attrs.get("name") or node_id)

    def _obsidian_name(self, value: str) -> str:
        cleaned = re.sub(r'[\\\\/:*?"<>|]', "-", value)
        cleaned = cleaned.replace(" ", "-")
        return cleaned[:120] or "note"

    def _json_safe(self, value: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(value, default=str))

    def _cypher_properties(self, attrs: dict[str, Any]) -> str:
        pairs = []
        for key, value in sorted(attrs.items()):
            if value is None:
                continue
            pairs.append(f"{key}: {self._cypher_literal(value)}")
        return "{" + ", ".join(pairs) + "}"

    def _cypher_literal(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
