"""Obsidian vault writer producing interlinked Markdown notes."""

from __future__ import annotations

import re
from pathlib import Path

from codegenome.exporter.context import ExportContext


def obsidian_name(value: str) -> str:
    """Sanitize a string into a safe Obsidian note filename."""
    cleaned = re.sub(r'[\\\\/:*?"<>|]', "-", value)
    cleaned = cleaned.replace(" ", "-")
    return cleaned[:120] or "note"


class ObsidianWriter:
    """Build an Obsidian vault with file, symbol, and index notes."""

    def write(self, ctx: ExportContext, output_path: Path) -> Path:
        vault_root = output_path
        files_dir = vault_root / "Files"
        symbols_dir = vault_root / "Symbols"
        files_dir.mkdir(parents=True, exist_ok=True)
        symbols_dir.mkdir(parents=True, exist_ok=True)

        file_links: list[str] = []
        for node_id, attrs in ctx.graph.iter_nodes():
            if attrs.get("node_type") != "file":
                continue
            path = str(attrs.get("file_path", node_id))
            note_name = obsidian_name(path)
            file_links.append(f"- [[Files/{note_name}|{path}]]")
            self._write_file_note(ctx, files_dir / f"{note_name}.md", path, node_id)

        for node_id, attrs in ctx.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            qname = str(attrs.get("qualified_name") or attrs.get("name") or node_id)
            note_name = obsidian_name(qname)
            file_path = str(attrs.get("file_path", ""))
            file_note = obsidian_name(file_path) if file_path else None
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
            "# CodeGenome Graph Vault",
            "",
            f"Workspace: `{ctx.workspace_name}`",
            "",
            "## Files",
            "",
            *sorted(file_links),
            "",
            "## Intelligence",
            "",
        ]
        if ctx.report:
            index_lines.extend(
                [
                    f"- Dead code nodes: {len(ctx.report.dead_code)}",
                    f"- God nodes: {len(ctx.report.god_nodes)}",
                    f"- Circular dependency groups: {len(ctx.report.circular_dependencies)}",
                ]
            )
        vault_root.joinpath("CodeGenome Index.md").write_text(
            "\n".join(index_lines) + "\n",
            encoding="utf-8",
        )
        return vault_root

    def _write_file_note(
        self,
        ctx: ExportContext,
        path: Path,
        file_path: str,
        node_id: str,
    ) -> None:
        graph = ctx.graph
        attrs = graph.get_node(node_id) if graph.has_node(node_id) else {}
        imports: list[str] = []
        calls: list[str] = []
        symbols: list[str] = []

        for _, target, edge_attrs in graph.out_edges(node_id):
            target_attrs = graph.get_node(target) if graph.has_node(target) else {}
            edge_type = edge_attrs.get("edge_type")
            if edge_type == "contains" and target_attrs.get("node_type") == "symbol":
                qname = target_attrs.get("qualified_name") or target_attrs.get("name")
                symbols.append(f"- [[Symbols/{obsidian_name(str(qname))}|{qname}]]")
            elif edge_type == "imports":
                module = target_attrs.get("module")
                if module:
                    imports.append(f"- `{module}`")

        for source, _, edge_attrs in graph.in_edges(node_id):
            if edge_attrs.get("edge_type") != "calls":
                continue
            source_attrs = graph.get_node(source) if graph.has_node(source) else {}
            if source_attrs.get("node_type") == "symbol":
                qname = source_attrs.get("qualified_name") or source_attrs.get("name")
                calls.append(f"- [[Symbols/{obsidian_name(str(qname))}|{qname}]]")

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
