"""File-level graph projections derived from the symbol/import graph."""

from __future__ import annotations

import networkx as nx

from codegenome.builder import file_node_id
from codegenome.graph_api import Graph
from codegenome.registry import GlobalDependencyRegistry
from codegenome.intelligence.pathutil import PathLike


class FileGraphProjector:
    """Project the detailed graph into file-level import / dependency graphs."""

    def __init__(
        self,
        graph: Graph,
        registry: GlobalDependencyRegistry | None = None,
    ) -> None:
        self.graph = graph
        self.registry = registry

    def file_import_graph(self) -> nx.DiGraph:
        """Build a directed file→file graph of import relationships."""
        file_graph = nx.DiGraph()

        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") == "file":
                file_graph.add_node(node)

        if self.registry:
            for file_path, entry in self.registry.files.items():
                source_id = file_node_id(file_path)
                if source_id not in file_graph:
                    file_graph.add_node(source_id)
                for fqn in entry.consumes:
                    target_path = self.registry.get_provider(fqn)
                    if target_path and target_path != file_path:
                        target_id = file_node_id(target_path)
                        if target_id not in file_graph:
                            file_graph.add_node(target_id)
                        file_graph.add_edge(source_id, target_id)
            return file_graph

        module_index = self._module_to_file_index()
        for source, target, edge_attrs in self.graph.iter_edges():
            if edge_attrs.get("edge_type") != "imports":
                continue
            target_attrs = self.graph.get_node(target) if self.graph.has_node(target) else {}
            if target_attrs.get("node_type") != "import":
                continue
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            source_path = source_attrs.get("file_path")
            if not source_path:
                continue
            module = str(target_attrs.get("module", ""))
            target_file = self._resolve_module_to_file(module, source_path, module_index)
            if not target_file:
                continue
            target_id = file_node_id(target_file)
            if target_id in file_graph and source in file_graph:
                file_graph.add_edge(source, target_id)

        return file_graph

    def file_dependency_graph(self) -> nx.Graph:
        """Build an undirected file dependency graph (imports + cross-file calls)."""
        dependency = nx.Graph()

        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") == "file":
                dependency.add_node(node)

        if self.registry:
            for file_path, entry in self.registry.files.items():
                source_id = file_node_id(file_path)
                if source_id not in dependency:
                    dependency.add_node(source_id)
                for fqn in entry.consumes:
                    target_path = self.registry.get_provider(fqn)
                    if target_path and target_path != file_path:
                        target_id = file_node_id(target_path)
                        if target_id not in dependency:
                            dependency.add_node(target_id)
                        dependency.add_edge(source_id, target_id)
            return dependency

        module_index = self._module_to_file_index()
        for source, target, edge_attrs in self.graph.iter_edges():
            edge_type = edge_attrs.get("edge_type")
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            target_attrs = self.graph.get_node(target) if self.graph.has_node(target) else {}

            if edge_type == "imports" and target_attrs.get("node_type") == "import":
                source_path = source_attrs.get("file_path")
                module = str(target_attrs.get("module", ""))
                if not source_path:
                    continue
                target_file = self._resolve_module_to_file(module, source_path, module_index)
                if not target_file:
                    continue
                target_id = file_node_id(target_file)
                if source in dependency and target_id in dependency:
                    dependency.add_edge(source, target_id)
                continue

            if edge_type != "calls":
                continue
            source_file = source_attrs.get("file_path")
            target_file = target_attrs.get("file_path")
            if not source_file or not target_file or source_file == target_file:
                continue
            source_id = file_node_id(source_file)
            target_id = file_node_id(target_file)
            if source_id in dependency and target_id in dependency:
                dependency.add_edge(source_id, target_id)

        return dependency

    def _module_to_file_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "file":
                continue
            path = str(attrs.get("file_path", ""))
            if not path:
                continue
            stem = PathLike(path).stem
            index[stem] = path
            normalized = path.replace("\\", "/")
            without_ext = normalized.rsplit(".", 1)[0]
            index[without_ext] = path
            index[normalized] = path
            parts = without_ext.split("/")
            index[".".join(parts)] = path
            index[parts[-1]] = path
        return index

    def _resolve_module_to_file(
        self,
        module: str,
        source_path: str,
        module_index: dict[str, str],
    ) -> str | None:
        module = module.strip()
        if not module:
            return None

        normalized = module.replace("\\", "/")
        candidates = [
            normalized,
            normalized.replace(".", "/"),
            f"{normalized.replace('.', '/')}.py",
        ]
        if module.startswith("."):
            source_dir = PathLike(source_path).parent.as_posix()
            pieces = [part for part in module.split(".") if part]
            rel = source_dir
            for piece in pieces:
                if piece == "":
                    rel = str(PathLike(rel).parent) if rel and rel != "." else ""
                else:
                    rel = f"{rel}/{piece}".strip("/") if rel and rel != "." else piece
            candidates.extend([rel, f"{rel}.py"])

        for candidate in candidates:
            candidate = candidate.strip("/")
            if candidate in module_index:
                return module_index[candidate]
            if PathLike(candidate).stem in module_index:
                return module_index[PathLike(candidate).stem]
        return None
