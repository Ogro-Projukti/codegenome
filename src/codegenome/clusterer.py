"""Leiden community detection and bridge-node analysis for CodeGenome graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import igraph as ig
import leidenalg
import networkx as nx

from codegenome.builder import file_node_id
from codegenome.graph_api import Graph, create_graph


@dataclass(frozen=True)
class ClusterResult:
    """Community detection output.

    Attributes:
        communities (dict[str, int]): Mapping of node IDs to community IDs.
        bridge_nodes (list[str]): List of node IDs identified as bridge nodes.
        betweenness_centrality (dict[str, float]): Normalized betweenness scores per file node.
    """

    communities: dict[str, int] = field(default_factory=dict)
    bridge_nodes: list[str] = field(default_factory=list)
    betweenness_centrality: dict[str, float] = field(default_factory=dict)


class GraphClusterer:
    """Detect architectural communities and bridge nodes.

    Attributes:
        resolution (float): The resolution parameter for the Leiden algorithm.
    """

    def __init__(self, *, resolution: float = 1.0) -> None:
        """Initialize the GraphClusterer.

        Args:
            resolution (float, optional): Resolution parameter for the Leiden algorithm. Defaults to 1.0.
        """
        self.resolution = resolution

    def cluster(self, graph: Graph) -> ClusterResult:
        """Perform community detection on the given graph.

        Args:
            graph (Graph): The graph to cluster.

        Returns:
            ClusterResult: The results of the community detection, including communities and bridge nodes.
        """
        clustering_graph = self._clustering_graph(graph)
        if clustering_graph.number_of_nodes() == 0:
            return ClusterResult()

        if clustering_graph.number_of_nodes() == 1:
            node = next(iter(node for node, _ in clustering_graph.iter_nodes()))
            return ClusterResult(
                communities={node: 0},
                bridge_nodes=[],
                betweenness_centrality={node: 0.0},
            )

        try:
            ig_graph = clustering_graph.to_igraph()
        except NotImplementedError:
            nx_graph = clustering_graph.to_networkx()
            ig_graph = self._networkx_to_igraph(nx_graph)

        if ig_graph.vcount() == 0:
            return ClusterResult()

        undirected = ig_graph.as_undirected()

        if undirected.ecount() == 0:
            communities = {v["name"]: idx for idx, v in enumerate(undirected.vs)}
            betweenness = {node_id: 0.0 for node_id in communities}
            return ClusterResult(
                communities=communities,
                bridge_nodes=[],
                betweenness_centrality=betweenness,
            )

        partition = leidenalg.find_partition(
            undirected,
            leidenalg.RBConfigurationVertexPartition,
            weights=None,
            resolution_parameter=self.resolution,
            seed=42,
        )
        
        node_names = undirected.vs["name"]
        communities = {
            node_names[index]: int(partition.membership[index])
            for index in range(len(node_names))
        }
        bridge_nodes = self.detect_bridge_nodes(clustering_graph, communities)
        betweenness = self.compute_betweenness_centrality(clustering_graph)
        return ClusterResult(
            communities=communities,
            bridge_nodes=bridge_nodes,
            betweenness_centrality=betweenness,
        )

    def annotate(self, graph: Graph) -> Graph:
        """Annotate the graph nodes with their community IDs and bridge status.

        Args:
            graph (Graph): The graph to annotate.

        Returns:
            Graph: The annotated graph.
        """
        result = self.cluster(graph)
        file_communities = dict(result.communities)
        bridge_set = set(result.bridge_nodes)
        betweenness = dict(result.betweenness_centrality)

        for node, attrs in graph.iter_nodes():
            community_id: int | None = None
            betweenness_score: float | None = None
            if node in file_communities:
                community_id = file_communities[node]
            else:
                file_path = attrs.get("file_path")
                if file_path:
                    file_id = file_node_id(str(file_path))
                    community_id = file_communities.get(file_id)

            if node in betweenness:
                betweenness_score = betweenness[node]
            else:
                file_path = attrs.get("file_path")
                if file_path:
                    betweenness_score = betweenness.get(file_node_id(str(file_path)))

            if community_id is not None:
                graph.set_node_attr(node, "community_id", community_id)
            graph.set_node_attr(node, "is_bridge", node in bridge_set)
            if betweenness_score is not None:
                graph.set_node_attr(node, "betweenness_centrality", betweenness_score)

        return graph

    def detect_bridge_nodes(
        self,
        graph: Graph,
        communities: dict[str, int],
    ) -> list[str]:
        """Identify bridge nodes that connect different communities.

        Args:
            graph (Graph): The underlying graph structure.
            communities (dict[str, int]): A mapping from node IDs to community IDs.

        Returns:
            list[str]: A sorted list of bridge node IDs.
        """
        if not communities:
            return []

        bridges: list[str] = []
        for node, _ in graph.iter_nodes():
            if node not in communities:
                continue
            own_community = communities[node]
            neighbor_communities = {
                communities[neighbor]
                for neighbor in graph.neighbors(node)
                if neighbor in communities and communities[neighbor] != own_community
            }
            if neighbor_communities:
                bridges.append(node)
        return sorted(bridges)

    def compute_betweenness_centrality(self, graph: Graph) -> dict[str, float]:
        """Compute normalized betweenness centrality on the file-level clustering graph.

        High scores highlight nodes that lie on many shortest paths between other
        files, complementing community-based bridge detection.

        Args:
            graph (Graph): The file-level graph used for community detection.

        Returns:
            dict[str, float]: Mapping of file node IDs to normalized betweenness scores.
        """
        if graph.number_of_nodes() == 0:
            return {}

        undirected = graph.to_networkx().to_undirected()
        if undirected.number_of_nodes() == 0:
            return {}

        if undirected.number_of_edges() == 0:
            return {str(node): 0.0 for node in undirected.nodes()}

        return {
            str(node): float(score)
            for node, score in nx.betweenness_centrality(undirected, normalized=True).items()
        }

    def betweenness_rankings(
        self,
        graph: Graph,
        *,
        include_generated: bool = False,
    ) -> list[tuple[str, float]]:
        """Rank file nodes by descending betweenness centrality."""
        clustering_graph = self._clustering_graph(graph)
        scores = self.compute_betweenness_centrality(clustering_graph)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if include_generated:
            return ranked

        filtered: list[tuple[str, float]] = []
        for node_id, score in ranked:
            attrs = graph.get_node(node_id) if graph.has_node(node_id) else {}
            if self._is_generated_or_vendor(attrs):
                continue
            filtered.append((node_id, score))
        return filtered

    @staticmethod
    def _is_generated_or_vendor(attrs: dict[str, object]) -> bool:
        path = str(attrs.get("file_path") or attrs.get("absolute_path") or "")
        if not path:
            return False

        normalized = path.replace("\\", "/").casefold()
        parts = {part for part in normalized.split("/") if part}
        generated_parts = {
            ".cache",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            "build",
            "coverage",
            "dist",
            "node_modules",
            "site-packages",
            "vendor",
            "vendors",
            "venv",
        }
        if parts & generated_parts:
            return True

        name = normalized.rsplit("/", 1)[-1]
        return name.endswith(
            (
                ".bundle.css",
                ".bundle.js",
                ".generated.css",
                ".generated.js",
                ".map",
                ".min.css",
                ".min.js",
            )
        )

    def _clustering_graph(self, graph: Graph) -> Graph:
        module_index = self._module_to_file_index(graph)
        file_graph = create_graph("igraph")

        for node, attrs in graph.iter_nodes():
            if attrs.get("node_type") == "file":
                file_graph.add_node(node)

        if file_graph.number_of_nodes() == 0:
            for node, attrs in graph.iter_nodes():
                if attrs.get("node_type") == "symbol":
                    file_graph.add_node(node)

        for source, target, edge_attrs in graph.iter_edges():
            edge_type = edge_attrs.get("edge_type")
            source_attrs = graph.get_node(source) if graph.has_node(source) else {}
            target_attrs = graph.get_node(target) if graph.has_node(target) else {}

            if edge_type == "imports" and target_attrs.get("node_type") == "import":
                source_path = source_attrs.get("file_path")
                module = str(target_attrs.get("module", ""))
                if not source_path:
                    continue
                target_file = self._resolve_module_to_file(module, source_path, module_index)
                if not target_file:
                    continue
                target_id = file_node_id(target_file)
                if file_graph.has_node(source) and file_graph.has_node(target_id) and source != target_id:
                    file_graph.add_edge(source, target_id)
                continue

            if edge_type != "calls":
                continue

            source_file = source_attrs.get("file_path")
            target_file = target_attrs.get("file_path")
            if not source_file or not target_file or source_file == target_file:
                continue
            source_id = file_node_id(source_file)
            target_id = file_node_id(target_file)
            if file_graph.has_node(source_id) and file_graph.has_node(target_id):
                file_graph.add_edge(source_id, target_id)

        return file_graph

    def _module_to_file_index(self, graph: Graph) -> dict[str, str]:
        index: dict[str, str] = {}
        for _, attrs in graph.iter_nodes():
            if attrs.get("node_type") != "file":
                continue
            path = str(attrs.get("file_path", ""))
            if not path:
                continue
            normalized = path.replace("\\", "/")
            stem = normalized.rsplit("/", 1)[-1]
            if "." in stem:
                stem = stem.rsplit(".", 1)[0]
            index[stem] = path
            without_ext = normalized.rsplit(".", 1)[0]
            index[without_ext] = path
            index[normalized] = path
            index[".".join(without_ext.split("/"))] = path
            index[without_ext.split("/")[-1]] = path
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
            source_dir = source_path.replace("\\", "/").rsplit("/", 1)[0]
            pieces = [part for part in module.split(".") if part]
            rel = source_dir
            for piece in pieces:
                if piece == "":
                    rel = rel.rsplit("/", 1)[0] if rel and rel != "." else ""
                else:
                    rel = f"{rel}/{piece}".strip("/") if rel and rel != "." else piece
            candidates.extend([rel, f"{rel}.py"])

        for candidate in candidates:
            candidate = candidate.strip("/")
            if candidate in module_index:
                return module_index[candidate]
            stem = candidate.rsplit("/", 1)[-1]
            if "." in stem:
                stem = stem.rsplit(".", 1)[0]
            if stem in module_index:
                return module_index[stem]
        return None

    def _networkx_to_igraph(self, graph: Any) -> ig.Graph:
        """Convert a NetworkX graph to igraph for compatibility."""
        node_ids = list(graph.nodes())
        if not node_ids:
            return ig.Graph(n=0, directed=graph.is_directed())

        index = {node_id: idx for idx, node_id in enumerate(node_ids)}
        edges: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for source, target in graph.edges():
            edge = (index[source], index[target])
            if edge in seen:
                continue
            seen.add(edge)
            edges.append(edge)

        ig_graph = ig.Graph(
            n=len(node_ids),
            edges=edges,
            directed=getattr(graph, "is_directed", lambda: True)(),
        )
        ig_graph.vs["name"] = node_ids
        return ig_graph
