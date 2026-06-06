"""NetworkX graph builder for CodeGenome scan and parse results."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from codegenome.graph_api import Graph, create_graph
from codegenome.parser import ParseResult, ParsedCall, ParsedImport, ParsedInheritance, ParsedSymbol
from codegenome.scanner import FileRecord, ScanResult


def file_node_id(path: str) -> str:
    """Generate a unique node ID for a file based on its path.

    Args:
        path (str): The file path.

    Returns:
        str: The generated node ID.
    """
    return f"file:{path}"


def symbol_node_id(path: str, qualified_name: str) -> str:
    """Generate a unique node ID for a symbol based on its path and qualified name.

    Args:
        path (str): The file path containing the symbol.
        qualified_name (str): The fully qualified name of the symbol.

    Returns:
        str: The generated node ID.
    """
    return f"symbol:{path}:{qualified_name}"


@dataclass
class GraphBuilder:
    """Build and incrementally update a codebase dependency graph.

    Attributes:
        graph (Graph): The underlying graph instance being built.
    """

    graph: Graph = field(default_factory=lambda: create_graph("igraph"))

    def build(
        self,
        scan: ScanResult,
        parses: dict[str, ParseResult],
    ) -> tuple[Graph, dict[str, set[str]], dict[str, set[str]]]:
        """Build a new graph from a fresh scan and parse results.

        Args:
            scan (ScanResult): The result of the workspace scan containing file records.
            parses (dict[str, ParseResult]): Dictionary mapping file paths to their parse results.

        Returns:
            tuple[Graph, dict[str, set[str]], dict[str, set[str]]]: A tuple containing the built graph,
                a dictionary of provided symbols per file, and a dictionary of consumed symbols per file.
        """
        self.graph.clear()
        now = time.time()
        provides: dict[str, set[str]] = {}
        consumes: dict[str, set[str]] = {}
        for record in scan.files:
            self._add_file_node(record, now)
        for path, parse_result in parses.items():
            provides[path] = set()
            consumes[path] = set()
            self._add_parse_result(path, parse_result, now, provides[path], consumes[path])
        return self.graph, provides, consumes

    def update(
        self,
        scan: ScanResult,
        parses: dict[str, ParseResult],
    ) -> tuple[Graph, dict[str, set[str]], dict[str, set[str]]]:
        """Update an existing graph incrementally based on new scan and parse results.

        Args:
            scan (ScanResult): The incremental scan result containing added, modified, and deleted files.
            parses (dict[str, ParseResult]): Dictionary mapping modified/added file paths to parse results.

        Returns:
            tuple[Graph, dict[str, set[str]], dict[str, set[str]]]: A tuple containing the updated graph,
                a dictionary of provided symbols for updated files, and a dictionary of consumed symbols.
        """
        now = time.time()

        provides: dict[str, set[str]] = {}
        consumes: dict[str, set[str]] = {}

        for deleted_path in scan.deleted:
            self._remove_file_subgraph(deleted_path)
            provides[deleted_path] = set()
            consumes[deleted_path] = set()

        for record in scan.files:
            rel_path = record.path
            if rel_path in scan.added:
                self._add_file_node(record, now)
                if rel_path in parses:
                    provides[rel_path] = set()
                    consumes[rel_path] = set()
                    self._add_parse_result(rel_path, parses[rel_path], now, provides[rel_path], consumes[rel_path])
            elif rel_path in scan.modified:
                self._remove_file_subgraph(rel_path)
                self._add_file_node(record, now, churn_delta=1)
                if rel_path in parses:
                    provides[rel_path] = set()
                    consumes[rel_path] = set()
                    self._add_parse_result(rel_path, parses[rel_path], now, provides[rel_path], consumes[rel_path])
            elif rel_path in scan.unchanged:
                file_id = file_node_id(rel_path)
                if self.graph.has_node(file_id):
                    self.graph.set_node_attr(file_id, "last_seen", now)
                elif rel_path in parses:
                    provides[rel_path] = set()
                    consumes[rel_path] = set()
                    self._add_file_node(record, now)
                    self._add_parse_result(rel_path, parses[rel_path], now, provides[rel_path], consumes[rel_path])

        return self.graph, provides, consumes

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

    def _add_parse_result(self, path: str, result: ParseResult, timestamp: float, provides: set[str], consumes: set[str]) -> None:
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
            self._add_symbol(path, file_id, symbol, timestamp, provides)
        for imp in result.imports:
            self._add_import(path, file_id, imp, timestamp, consumes)
        for inherit in result.inheritance:
            self._add_inheritance(path, inherit, timestamp, consumes)
        for call in result.calls:
            self._add_call(path, call, timestamp, consumes)

    def _add_symbol(
        self,
        path: str,
        file_id: str,
        symbol: ParsedSymbol,
        timestamp: float,
        provides: set[str]
    ) -> None:
        qname = symbol.qualified_name or symbol.name
        provides.add(qname)
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
            instance_attrs=sorted(symbol.instance_attrs),
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
        consumes: set[str]
    ) -> None:
        import_id = f"import:{path}:{imp.start_line}:{imp.module}"
        if imp.names:
            for name in imp.names:
                consumes.add(f"{imp.module}.{name}" if imp.module else name)
        elif imp.module:
            consumes.add(imp.module)
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
        consumes: set[str]
    ) -> None:
        consumes.add(inherit.base)
        child_candidates = [
            node
            for node, attrs in self.graph.iter_nodes()
            if attrs.get("file_path") == path
            and attrs.get("node_type") == "symbol"
            and attrs.get("name") == inherit.class_name
        ]
        base_id = f"proxy:{path}:{inherit.base}"
        if not self.graph.has_node(base_id):
            self.graph.add_node(
                base_id,
                node_type="proxy",
                name=inherit.base,
                file_path=path,
                first_seen=timestamp,
                last_seen=timestamp,
                churn=0,
                is_broken=False,
            )
        for child_id in child_candidates:
            self.graph.add_edge(child_id, base_id, edge_type="inherits", line=inherit.line)

    def _add_call(self, path: str, call: ParsedCall, timestamp: float, consumes: set[str]) -> None:
        caller_id = self._resolve_local_symbol_id(path, call.caller)
        consumes.add(call.callee)
        callee_id = self._resolve_local_symbol_id(path, call.callee) or f"proxy:{path}:{call.callee}"
        if not self.graph.has_node(callee_id):
            self.graph.add_node(
                callee_id,
                node_type="proxy",
                name=call.callee,
                file_path=path,
                first_seen=timestamp,
                last_seen=timestamp,
                churn=0,
                is_broken=False,
            )
        if caller_id and self.graph.has_node(caller_id):
            self.graph.add_edge(caller_id, callee_id, edge_type="calls", line=call.line)

    def _resolve_local_symbol_id(self, path: str, qualified_name: str) -> str | None:
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
        """Retrieve metadata attributes for a specific file node in the graph.

        Args:
            path (str): The file path to lookup.

        Returns:
            dict[str, Any] | None: The node attributes if found, otherwise None.
        """
        node_id = file_node_id(path)
        if not self.graph.has_node(node_id):
            return None
        return self.graph.get_node(node_id)

    def symbol_count(self, path: str | None = None) -> int:
        """Count the number of symbol nodes in the graph, optionally filtered by file path.

        Args:
            path (str | None, optional): The file path to filter by. Defaults to None.

        Returns:
            int: The total number of symbol nodes matching the criteria.
        """
        return sum(
            1
            for _, attrs in self.graph.iter_nodes()
            if attrs.get("node_type") == "symbol"
            and (path is None or attrs.get("file_path") == path)
        )
