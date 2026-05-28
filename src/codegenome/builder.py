"""NetworkX graph builder for Watcher scan and parse results."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from codegenome.graph_api import Graph, create_graph
from codegenome.parser import ParseResult, ParsedCall, ParsedImport, ParsedInheritance, ParsedSymbol
from codegenome.scanner import FileRecord, ScanResult


def file_node_id(path: str) -> str:
    return f"file:{path}"


def symbol_node_id(path: str, qualified_name: str) -> str:
    return f"symbol:{path}:{qualified_name}"


@dataclass
class GraphBuilder:
    """Build and incrementally update a codebase dependency graph."""

    graph: Graph = field(default_factory=lambda: create_graph("igraph"))

    def build(
        self,
        scan: ScanResult,
        parses: dict[str, ParseResult],
    ) -> Graph:
        self.graph.clear()
        now = time.time()
        for record in scan.files:
            self._add_file_node(record, now)
        for path, parse_result in parses.items():
            self._add_parse_result(path, parse_result, now)
        return self.graph

    def update(
        self,
        scan: ScanResult,
        parses: dict[str, ParseResult],
    ) -> Graph:
        now = time.time()

        for deleted_path in scan.deleted:
            self._remove_file_subgraph(deleted_path)

        for record in scan.files:
            rel_path = record.path
            if rel_path in scan.added:
                self._add_file_node(record, now)
                if rel_path in parses:
                    self._add_parse_result(rel_path, parses[rel_path], now)
            elif rel_path in scan.modified:
                self._remove_file_subgraph(rel_path)
                self._add_file_node(record, now, churn_delta=1)
                if rel_path in parses:
                    self._add_parse_result(rel_path, parses[rel_path], now)
            elif rel_path in scan.unchanged:
                file_id = file_node_id(rel_path)
                if self.graph.has_node(file_id):
                    self.graph.set_node_attr(file_id, "last_seen", now)
                elif rel_path in parses:
                    self._add_file_node(record, now)
                    self._add_parse_result(rel_path, parses[rel_path], now)

        return self.graph

    def _remove_file_subgraph(self, path: str) -> None:
        file_id = file_node_id(path)
        to_remove = [
            node
            for node, attrs in self.graph.iter_nodes()
            if attrs.get("file_path") == path or node == file_id
        ]
        self.graph.remove_nodes_from(to_remove)

    def _add_file_node(self, record: FileRecord, timestamp: float, churn_delta: int = 0) -> None:
        node_id = file_node_id(record.path)
        existing = self.graph.get_node(node_id) if self.graph.has_node(node_id) else {}
        churn = int(existing.get("churn", 0)) + churn_delta
        self.graph.add_node(
            node_id,
            node_type="file",
            file_path=record.path,
            absolute_path=record.absolute_path,
            sha256=record.sha256,
            size=record.size,
            mtime=record.mtime,
            first_seen=existing.get("first_seen", timestamp),
            last_seen=timestamp,
            churn=churn,
        )

    def _add_parse_result(self, path: str, result: ParseResult, timestamp: float) -> None:
        file_id = file_node_id(path)
        if not self.graph.has_node(file_id):
            self.graph.add_node(
                file_id,
                node_type="file",
                file_path=path,
                first_seen=timestamp,
                last_seen=timestamp,
                churn=0,
            )

        self.graph.set_node_attr(file_id, "language", result.language)
        if result.errors:
            self.graph.set_node_attr(file_id, "parse_errors", list(result.errors))

        for symbol in result.symbols:
            self._add_symbol(path, file_id, symbol, timestamp)
        for imp in result.imports:
            self._add_import(path, file_id, imp, timestamp)
        for inherit in result.inheritance:
            self._add_inheritance(path, inherit, timestamp)
        for call in result.calls:
            self._add_call(path, call, timestamp)

    def _add_symbol(
        self,
        path: str,
        file_id: str,
        symbol: ParsedSymbol,
        timestamp: float,
    ) -> None:
        qname = symbol.qualified_name or symbol.name
        node_id = symbol_node_id(path, qname)
        self.graph.add_node(
            node_id,
            node_type="symbol",
            file_path=path,
            name=symbol.name,
            qualified_name=qname,
            kind=symbol.kind,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            docstring=symbol.docstring,
            complexity=symbol.complexity,
            first_seen=timestamp,
            last_seen=timestamp,
            churn=0,
        )
        self.graph.add_edge(file_id, node_id, edge_type="contains")

    def _add_import(
        self,
        path: str,
        file_id: str,
        imp: ParsedImport,
        timestamp: float,
    ) -> None:
        import_id = f"import:{path}:{imp.start_line}:{imp.module}"
        self.graph.add_node(
            import_id,
            node_type="import",
            file_path=path,
            module=imp.module,
            names=imp.names,
            is_relative=imp.is_relative,
            start_line=imp.start_line,
            first_seen=timestamp,
            last_seen=timestamp,
            churn=0,
        )
        self.graph.add_edge(file_id, import_id, edge_type="imports")

    def _add_inheritance(
        self,
        path: str,
        inherit: ParsedInheritance,
        timestamp: float,
    ) -> None:
        child_candidates = [
            node
            for node, attrs in self.graph.iter_nodes()
            if attrs.get("file_path") == path
            and attrs.get("node_type") == "symbol"
            and attrs.get("name") == inherit.class_name
        ]
        base_id = f"external:{inherit.base}"
        if not self.graph.has_node(base_id):
            self.graph.add_node(
                base_id,
                node_type="external",
                name=inherit.base,
                first_seen=timestamp,
                last_seen=timestamp,
                churn=0,
            )
        for child_id in child_candidates:
            self.graph.add_edge(child_id, base_id, edge_type="inherits", line=inherit.line)

    def _add_call(self, path: str, call: ParsedCall, timestamp: float) -> None:
        caller_id = self._resolve_symbol_id(path, call.caller)
        callee_id = self._resolve_symbol_id(path, call.callee) or f"external:{call.callee}"
        if not self.graph.has_node(callee_id):
            self.graph.add_node(
                callee_id,
                node_type="external",
                name=call.callee,
                first_seen=timestamp,
                last_seen=timestamp,
                churn=0,
            )
        if caller_id and self.graph.has_node(caller_id):
            self.graph.add_edge(caller_id, callee_id, edge_type="calls", line=call.line)

    def _resolve_symbol_id(self, path: str, qualified_name: str) -> str | None:
        exact = symbol_node_id(path, qualified_name)
        if self.graph.has_node(exact):
            return exact

        suffix_matches = [
            node
            for node, attrs in self.graph.iter_nodes()
            if attrs.get("file_path") == path
            and attrs.get("node_type") == "symbol"
            and (
                attrs.get("qualified_name") == qualified_name
                or attrs.get("name") == qualified_name
                or str(attrs.get("qualified_name", "")).endswith(f".{qualified_name}")
            )
        ]
        return suffix_matches[0] if suffix_matches else None

    def file_metadata(self, path: str) -> dict[str, Any] | None:
        node_id = file_node_id(path)
        if not self.graph.has_node(node_id):
            return None
        return self.graph.get_node(node_id)

    def symbol_count(self, path: str | None = None) -> int:
        return sum(
            1
            for _, attrs in self.graph.iter_nodes()
            if attrs.get("node_type") == "symbol"
            and (path is None or attrs.get("file_path") == path)
        )
