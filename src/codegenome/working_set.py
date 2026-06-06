"""Bounded in-memory graph working set backed by timeline snapshots."""

from __future__ import annotations

from collections import OrderedDict

from codegenome.graph_api import Graph, create_graph
from codegenome.graph_loader import node_file_path
from codegenome.timeline import GraphTimeline


class WorkingSetGraph:
    """Keep only a bounded set of file subgraphs resident in memory."""

    def __init__(
        self,
        timeline: GraphTimeline,
        snapshot_id: int,
        *,
        max_files: int = 64,
    ) -> None:
        self._timeline = timeline
        self._snapshot_id = snapshot_id
        self._max_files = max(1, max_files)
        self._loaded_files: OrderedDict[str, None] = OrderedDict()
        self._graph = create_graph("igraph")

    @property
    def snapshot_id(self) -> int:
        return self._snapshot_id

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def loaded_files(self) -> set[str]:
        return set(self._loaded_files)

    def set_snapshot_id(self, snapshot_id: int) -> None:
        self._snapshot_id = snapshot_id

    def ensure_files(self, file_paths: set[str]) -> None:
        """Load file subgraphs from disk and evict cold files when over capacity."""
        for file_path in sorted(file_paths):
            if not file_path:
                continue
            if file_path not in self._loaded_files:
                subgraph = self._timeline.load_file_subgraph(self._snapshot_id, {file_path})
                self._merge_subgraph(subgraph)
                self._loaded_files[file_path] = None
            self._loaded_files.move_to_end(file_path)

        while len(self._loaded_files) > self._max_files:
            evicted, _ = self._loaded_files.popitem(last=False)
            self._remove_file(evicted)

    def evict_all(self) -> None:
        """Drop all resident subgraphs."""
        self._loaded_files.clear()
        self._graph = create_graph("igraph")

    def _merge_subgraph(self, subgraph: Graph) -> None:
        for node_id, attrs in subgraph.iter_nodes():
            if self._graph.has_node(node_id):
                for key, value in attrs.items():
                    self._graph.set_node_attr(node_id, key, value)
            else:
                self._graph.add_node(node_id, **attrs)

        for source, target, attrs in subgraph.iter_edges():
            if not self._graph.has_edge(source, target):
                self._graph.add_edge(source, target, **attrs)

    def _remove_file(self, file_path: str) -> None:
        to_remove = [
            node_id
            for node_id, attrs in self._graph.iter_nodes()
            if node_file_path(node_id, attrs) == file_path
        ]
        if to_remove:
            self._graph.remove_nodes_from(to_remove)
