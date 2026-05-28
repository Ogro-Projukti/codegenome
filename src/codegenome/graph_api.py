"""Graph API abstraction layer for CodeGenome."""

from __future__ import annotations

import json
from typing import Any, Iterable, Iterator, Tuple

import igraph as ig
import networkx as nx


class Graph:
    """Abstract interface for graph operations."""

    def clear(self) -> None:
        raise NotImplementedError

    def add_node(self, node_id: str, **attrs: Any) -> None:
        raise NotImplementedError

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        raise NotImplementedError

    def remove_nodes_from(self, nodes: Iterable[str]) -> None:
        raise NotImplementedError

    def number_of_nodes(self) -> int:
        raise NotImplementedError

    def number_of_edges(self) -> int:
        raise NotImplementedError

    def has_node(self, node_id: str) -> bool:
        raise NotImplementedError

    def copy(self) -> 'Graph':
        raise NotImplementedError

    def has_edge(self, source: str, target: str) -> bool:
        raise NotImplementedError

    def get_node(self, node_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def set_node_attr(self, node_id: str, key: str, value: Any) -> None:
        raise NotImplementedError

    def get_edge(self, source: str, target: str) -> dict[str, Any]:
        raise NotImplementedError

    def iter_nodes(self) -> Iterator[Tuple[str, dict[str, Any]]]:
        raise NotImplementedError

    def in_degree(self, node_id: str) -> int:
        raise NotImplementedError

    def out_degree(self, node_id: str) -> int:
        raise NotImplementedError

    def iter_edges(self) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        raise NotImplementedError

    def in_edges(self, node_id: str) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        raise NotImplementedError

    def out_edges(self, node_id: str) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        raise NotImplementedError

    def neighbors(self, node_id: str) -> Iterator[str]:
        raise NotImplementedError

    def strongly_connected_components(self) -> list[set[str]]:
        raise NotImplementedError

    def to_serializable(self) -> dict[str, Any]:
        raise NotImplementedError

    def to_networkx(self) -> nx.DiGraph:
        """Compatibility layer for incremental migration."""
        raise NotImplementedError

    def to_igraph(self) -> ig.Graph:
        """Compatibility layer for incremental migration."""
        raise NotImplementedError


class NetworkXGraph(Graph):
    """NetworkX implementation of the Graph API."""

    def __init__(self) -> None:
        self._graph = nx.DiGraph()

    def clear(self) -> None:
        self._graph.clear()

    def add_node(self, node_id: str, **attrs: Any) -> None:
        self._graph.add_node(node_id, **attrs)

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        self._graph.add_edge(source, target, **attrs)

    def remove_nodes_from(self, nodes: Iterable[str]) -> None:
        self._graph.remove_nodes_from(nodes)

    def number_of_nodes(self) -> int:
        return self._graph.number_of_nodes()

    def number_of_edges(self) -> int:
        return self._graph.number_of_edges()

    def has_node(self, node_id: str) -> bool:
        return self._graph.has_node(node_id)

    def copy(self) -> 'Graph':
        new_g = NetworkXGraph()
        new_g._graph = self._graph.copy()
        return new_g

    def has_edge(self, source: str, target: str) -> bool:
        return self._graph.has_edge(source, target)

    def get_node(self, node_id: str) -> dict[str, Any]:
        return dict(self._graph.nodes[node_id])

    def set_node_attr(self, node_id: str, key: str, value: Any) -> None:
        if self._graph.has_node(node_id):
            self._graph.nodes[node_id][key] = value

    def get_edge(self, source: str, target: str) -> dict[str, Any]:
        return dict(self._graph.edges[source, target])

    def iter_nodes(self) -> Iterator[Tuple[str, dict[str, Any]]]:
        for node_id, attrs in self._graph.nodes(data=True):
            yield node_id, dict(attrs)

    def in_degree(self, node_id: str) -> int:
        return self._graph.in_degree(node_id) if self._graph.has_node(node_id) else 0

    def out_degree(self, node_id: str) -> int:
        return self._graph.out_degree(node_id) if self._graph.has_node(node_id) else 0

    def iter_edges(self) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        for source, target, attrs in self._graph.edges(data=True):
            yield source, target, dict(attrs)

    def in_edges(self, node_id: str) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        if self._graph.has_node(node_id):
            for source, target, attrs in self._graph.in_edges(node_id, data=True):
                yield source, target, dict(attrs)

    def out_edges(self, node_id: str) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        if self._graph.has_node(node_id):
            for source, target, attrs in self._graph.out_edges(node_id, data=True):
                yield source, target, dict(attrs)

    def neighbors(self, node_id: str) -> Iterator[str]:
        if self._graph.has_node(node_id):
            yield from self._graph.neighbors(node_id)

    def strongly_connected_components(self) -> list[set[str]]:
        return [set(c) for c in nx.strongly_connected_components(self._graph)]

    def to_serializable(self) -> dict[str, Any]:
        return nx.node_link_data(self._graph)

    def to_networkx(self) -> nx.DiGraph:
        return self._graph

    def to_igraph(self) -> ig.Graph:
        raise NotImplementedError("Direct conversion to igraph not supported in NX adapter.")


class IGraphGraph(Graph):
    """igraph implementation of the Graph API."""

    def __init__(self) -> None:
        self._graph = ig.Graph(directed=True)
        self._name_index: dict[str, int] = {}
        self._node_attrs: dict[str, dict[str, Any]] = {}

    def clear(self) -> None:
        self._graph = ig.Graph(directed=True)
        self._name_index.clear()
        self._node_attrs.clear()

    def add_node(self, node_id: str, **attrs: Any) -> None:
        if node_id not in self._name_index:
            idx = self._graph.vcount()
            self._graph.add_vertices(1)
            self._name_index[node_id] = idx
            self._graph.vs[idx]["name"] = node_id
        self._node_attrs[node_id] = attrs

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        if source not in self._name_index:
            self.add_node(source)
        if target not in self._name_index:
            self.add_node(target)
            
        source_idx = self._name_index[source]
        target_idx = self._name_index[target]
        self._graph.add_edges([(source_idx, target_idx)])
        edge_idx = self._graph.ecount() - 1
        
        # Store attributes dynamically
        for key, value in attrs.items():
            if key not in self._graph.edge_attributes():
                self._graph.es[key] = None
            self._graph.es[edge_idx][key] = value

    def remove_nodes_from(self, nodes: Iterable[str]) -> None:
        indices_to_remove = []
        for node_id in nodes:
            if node_id in self._name_index:
                indices_to_remove.append(self._name_index[node_id])
                del self._name_index[node_id]
                self._node_attrs.pop(node_id, None)
                
        if indices_to_remove:
            self._graph.delete_vertices(indices_to_remove)
            # Rebuild index since deleting vertices shifts indices
            self._name_index = {
                v["name"]: v.index for v in self._graph.vs
            }

    def number_of_nodes(self) -> int:
        return self._graph.vcount()

    def number_of_edges(self) -> int:
        return self._graph.ecount()

    def has_node(self, node_id: str) -> bool:
        return node_id in self._name_index

    def copy(self) -> 'Graph':
        new_g = IGraphGraph()
        new_g._graph = self._graph.copy()
        new_g._name_index = dict(self._name_index)
        new_g._node_attrs = {k: dict(v) for k, v in self._node_attrs.items()}
        return new_g

    def has_edge(self, source: str, target: str) -> bool:
        if source not in self._name_index or target not in self._name_index:
            return False
        source_idx = self._name_index[source]
        target_idx = self._name_index[target]
        return bool(self._graph.es.select(_source=source_idx, _target=target_idx))

    def get_node(self, node_id: str) -> dict[str, Any]:
        if node_id not in self._name_index:
            raise KeyError(node_id)
        return self._node_attrs.get(node_id, {})

    def set_node_attr(self, node_id: str, key: str, value: Any) -> None:
        if node_id in self._name_index:
            if node_id not in self._node_attrs:
                self._node_attrs[node_id] = {}
            self._node_attrs[node_id][key] = value

    def get_edge(self, source: str, target: str) -> dict[str, Any]:
        if source not in self._name_index or target not in self._name_index:
            raise KeyError(f"Edge {source}->{target} not found")
        source_idx = self._name_index[source]
        target_idx = self._name_index[target]
        edges = self._graph.es.select(_source=source_idx, _target=target_idx)
        if not edges:
            raise KeyError(f"Edge {source}->{target} not found")
        return {k: v for k, v in edges[0].attributes().items() if v is not None}

    def iter_nodes(self) -> Iterator[Tuple[str, dict[str, Any]]]:
        for node_id, attrs in self._node_attrs.items():
            yield node_id, attrs

    def in_degree(self, node_id: str) -> int:
        if node_id not in self._name_index:
            return 0
        return self._graph.degree(self._name_index[node_id], mode="in")

    def out_degree(self, node_id: str) -> int:
        if node_id not in self._name_index:
            return 0
        return self._graph.degree(self._name_index[node_id], mode="out")

    def iter_edges(self) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        for e in self._graph.es:
            source_id = self._graph.vs[e.source]["name"]
            target_id = self._graph.vs[e.target]["name"]
            yield source_id, target_id, {k: v for k, v in e.attributes().items() if v is not None}

    def in_edges(self, node_id: str) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        if node_id in self._name_index:
            idx = self._name_index[node_id]
            for e in self._graph.es.select(_target=idx):
                source_id = self._graph.vs[e.source]["name"]
                yield source_id, node_id, {k: v for k, v in e.attributes().items() if v is not None}

    def out_edges(self, node_id: str) -> Iterator[Tuple[str, str, dict[str, Any]]]:
        if node_id in self._name_index:
            idx = self._name_index[node_id]
            for e in self._graph.es.select(_source=idx):
                target_id = self._graph.vs[e.target]["name"]
                yield node_id, target_id, {k: v for k, v in e.attributes().items() if v is not None}

    def neighbors(self, node_id: str) -> Iterator[str]:
        if node_id in self._name_index:
            idx = self._name_index[node_id]
            for neighbor_idx in self._graph.successors(idx):
                yield self._graph.vs[neighbor_idx]["name"]

    def strongly_connected_components(self) -> list[set[str]]:
        scc = self._graph.connected_components(mode="strong")
        return [{self._graph.vs[idx]["name"] for idx in comp} for comp in scc]

    def to_serializable(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": node_id, **attrs}
                for node_id, attrs in self.iter_nodes()
            ],
            "links": [
                {"source": s, "target": t, **attrs}
                for s, t, attrs in self.iter_edges()
            ]
        }

    def to_networkx(self) -> nx.DiGraph:
        nx_g = nx.DiGraph()
        for node_id, attrs in self.iter_nodes():
            nx_g.add_node(node_id, **attrs)
        for s, t, attrs in self.iter_edges():
            nx_g.add_edge(s, t, **attrs)
        return nx_g

    def to_igraph(self) -> ig.Graph:
        return self._graph

def create_graph(backend: str = "igraph") -> Graph:
    """Factory to create a graph instance."""
    if backend == "networkx":
        return NetworkXGraph()
    return IGraphGraph()
