"""Structural analyzers: dead code, cycles, entry points, orphan modules."""

from __future__ import annotations

import networkx as nx

from codegenome.builder import file_node_id
from codegenome.intelligence.context import AnalysisContext
from codegenome.intelligence.pathutil import PathLike


class DeadCodeAnalyzer:
    """Detect functions and methods that are never called."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def detect(
        self,
        *,
        include_generated: bool = False,
        include_public_api: bool = False,
    ) -> list[str]:
        """Return a sorted list of node IDs corresponding to dead code."""
        graph = self.ctx.graph
        classifier = self.ctx.classifier
        if graph.number_of_nodes() == 0:
            return []

        entry_symbols = set(classifier.entry_symbol_ids(graph))
        dead: list[str] = []
        for node, attrs in graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            if not include_generated and classifier.is_generated_or_vendor(attrs):
                continue
            if attrs.get("kind") not in {"function", "method"}:
                continue
            name = str(attrs.get("name", ""))
            if classifier.is_dunder_name(name):
                continue
            if not include_public_api and classifier.is_public_api_method(attrs):
                continue
            if node in entry_symbols:
                continue
            if any(
                edge_attrs.get("edge_type") == "calls"
                for _, _, edge_attrs in graph.out_edges(node)
            ):
                continue
            if any(
                pred_attrs.get("edge_type") == "calls"
                for _, _, pred_attrs in graph.in_edges(node)
            ):
                continue
            dead.append(node)
        return sorted(dead)


class CircularDependencyAnalyzer:
    """Identify circular import dependencies between files."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def detect(self) -> list[list[str]]:
        """Return a list of cycles, each a list of node IDs."""
        file_graph = self.ctx.projector.file_import_graph()
        if file_graph.number_of_nodes() == 0:
            return []

        cycles: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for component in nx.strongly_connected_components(file_graph):
            if len(component) < 2:
                continue
            subgraph = file_graph.subgraph(component)
            for cycle in nx.simple_cycles(subgraph):
                normalized = tuple(sorted(cycle))
                if normalized in seen:
                    continue
                seen.add(normalized)
                cycles.append(cycle)
        cycles.sort(key=lambda cycle: (len(cycle), cycle))
        return cycles


class EntryPointAnalyzer:
    """Detect file and symbol nodes that serve as application entry points."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def detect(self) -> list[str]:
        """Return a sorted list of node IDs representing entry points."""
        graph = self.ctx.graph
        if graph.number_of_nodes() == 0:
            return []

        file_graph = self.ctx.projector.file_import_graph()
        imported_files = {target for _, target in file_graph.edges()}
        all_files = {
            attrs["file_path"]
            for _, attrs in graph.iter_nodes()
            if attrs.get("node_type") == "file" and attrs.get("file_path")
        }
        entry_file_names = self.ctx.classifier.ENTRY_FILE_NAMES
        file_entries = sorted(
            file_node_id(path)
            for path in all_files
            if file_node_id(path) not in imported_files
            or PathLike(path).name in entry_file_names
        )

        symbol_entries = self.ctx.classifier.entry_symbol_ids(graph)
        return sorted(set(file_entries) | set(symbol_entries))


class OrphanModuleAnalyzer:
    """Identify files that have no incoming or outgoing dependencies."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def detect(self) -> list[str]:
        """Return a sorted list of orphan file paths."""
        graph = self.ctx.graph
        if graph.number_of_nodes() == 0:
            return []

        file_graph = self.ctx.projector.file_dependency_graph()
        orphans: list[str] = []
        for node, attrs in graph.iter_nodes():
            if attrs.get("node_type") != "file":
                continue
            path = attrs.get("file_path")
            if not path:
                continue
            if file_graph.number_of_nodes() <= 1:
                continue
            if file_graph.degree(node) == 0:
                orphans.append(path)
        return sorted(orphans)
