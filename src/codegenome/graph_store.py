"""Graph query layer for the CodeGenome MCP server."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from codegenome.graph_api import Graph, create_graph
from codegenome.clusterer import GraphClusterer
from codegenome.intelligence import GraphIntelligence
from codegenome.mcp_analysis import McpAnalysisProvider
from codegenome.snapshot_metrics import SnapshotMetrics
from codegenome.timeline import GraphTimeline, NodeHistoryEntry, SnapshotInfo


class GraphStoreError(Exception):
    """Raised when graph store operations fail."""


@dataclass(frozen=True)
class GraphSummary:
    """A summary of a graph snapshot's state and metrics.

    Attributes:
        snapshot_id (int | None): The unique identifier of the snapshot, if any.
        node_count (int): Total number of nodes in the snapshot.
        edge_count (int): Total number of edges in the snapshot.
        label (str | None): An optional descriptive label for the snapshot.
        empty (bool): Indicates whether the snapshot contains any nodes.
    """
    snapshot_id: int | None
    latest_snapshot_id: int | None
    node_count: int
    edge_count: int
    label: str | None
    empty: bool
    current: bool


class GraphStore:
    """Load and query a CodeGenome timeline database.

    Provides a high-level API to interact with versioned graph snapshots,
    perform queries, and extract code intelligence metrics.
    """

    def __init__(
        self,
        db_path: Path | str,
        *,
        memory_bounded: bool = False,
        max_query_nodes: int = 500,
        neighborhood_depth: int = 1,
        full_analysis_on_demand: bool = False,
    ) -> None:
        """Initializes a new GraphStore instance.

        Args:
            db_path (Path | str): The path to the SQLite timeline database.
            memory_bounded (bool): Load query subgraphs on demand instead of the full graph.
            max_query_nodes (int): Maximum nodes for neighborhood loads in bounded mode.
            neighborhood_depth (int): BFS depth for bounded neighbor queries.
            full_analysis_on_demand (bool): Allow global analysis tools to load the full graph temporarily.
        """
        self.db_path = Path(db_path).resolve()
        self._memory_bounded = memory_bounded
        self._max_query_nodes = max(1, max_query_nodes)
        self._neighborhood_depth = max(0, neighborhood_depth)
        self._full_analysis_on_demand = full_analysis_on_demand
        self._timeline: GraphTimeline | None = None
        self._graph: Graph = create_graph("igraph")
        self._snapshot_id: int | None = None
        self._snapshot_label: str | None = None
        self._snapshot_node_count = 0
        self._snapshot_edge_count = 0
        self._intelligence: GraphIntelligence | None = None
        self._analysis = McpAnalysisProvider(self)

    @property
    def graph(self) -> Graph:
        """The currently loaded graph instance."""
        return self._graph

    @property
    def snapshot_id(self) -> int | None:
        """The ID of the currently loaded snapshot, or None if empty."""
        return self._snapshot_id

    @property
    def is_empty(self) -> bool:
        """True if the currently loaded graph has no nodes."""
        return self._graph.number_of_nodes() == 0

    def open(self) -> None:
        """Opens the timeline database and loads the latest snapshot into memory.

        Raises:
            GraphStoreError: If the database cannot be opened or the snapshot fails to load.
        """
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._timeline = GraphTimeline(self.db_path)
        except sqlite3.Error as exc:
            raise GraphStoreError(f"Failed to open database at {self.db_path}: {exc}") from exc

        snapshots = self._timeline.list_snapshots()
        if not snapshots:
            self._bind_snapshot_metadata(None)
            return

        latest = snapshots[-1]
        if self._memory_bounded:
            self._bind_snapshot_metadata(latest)
            return

        try:
            self._graph = self._timeline.load_snapshot(latest.snapshot_id)
        except sqlite3.Error as exc:
            raise GraphStoreError(
                f"Failed to load snapshot {latest.snapshot_id}: {exc}"
            ) from exc

        self._bind_snapshot_metadata(latest, graph=self._graph)

    def refresh_latest(self) -> bool:
        """Load the newest timeline snapshot if it changed after startup.

        Returns:
            bool: True when a newer snapshot was loaded.
        """
        if self._timeline is None:
            raise GraphStoreError("Timeline database is not open")

        snapshots = self._timeline.list_snapshots()
        if not snapshots:
            changed = self._snapshot_id is not None or not self.is_empty
            self._bind_snapshot_metadata(None)
            return changed

        latest = snapshots[-1]
        if latest.snapshot_id == self._snapshot_id:
            return False

        if self._memory_bounded:
            self._bind_snapshot_metadata(latest)
            return True

        try:
            self._graph = self._timeline.load_snapshot(latest.snapshot_id)
        except sqlite3.Error as exc:
            raise GraphStoreError(
                f"Failed to load snapshot {latest.snapshot_id}: {exc}"
            ) from exc

        self._bind_snapshot_metadata(latest, graph=self._graph)
        return True

    def close(self) -> None:
        """Closes the connection to the timeline database."""
        if self._timeline is not None:
            self._timeline.close()
            self._timeline = None

    def summary(self) -> GraphSummary:
        """Generates a summary of the currently loaded graph.

        Returns:
            GraphSummary: High-level metrics for the current graph state.
        """
        latest_snapshot_id = self._latest_snapshot_id()
        if self._memory_bounded:
            node_count = self._snapshot_node_count
            edge_count = self._snapshot_edge_count
            empty = node_count == 0
        else:
            node_count = self._graph.number_of_nodes()
            edge_count = self._graph.number_of_edges()
            empty = self.is_empty
        return GraphSummary(
            snapshot_id=self._snapshot_id,
            latest_snapshot_id=latest_snapshot_id,
            node_count=node_count,
            edge_count=edge_count,
            label=self._snapshot_label,
            empty=empty,
            current=self._snapshot_id == latest_snapshot_id,
        )

    def get_graph(
        self,
        *,
        include_nodes: bool = False,
        include_edges: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Retrieves a serialized representation of the graph.

        Args:
            include_nodes (bool): Whether to include node details. Defaults to False.
            include_edges (bool): Whether to include edge details. Defaults to False.
            limit (int): Maximum number of nodes and edges to return. Defaults to 100.

        Returns:
            dict[str, Any]: A payload containing graph summary and optional details.
        """
        summary = self.summary()
        payload: dict[str, Any] = {
            "snapshot_id": summary.snapshot_id,
            "latest_snapshot_id": summary.latest_snapshot_id,
            "current": summary.current,
            "label": summary.label,
            "node_count": summary.node_count,
            "edge_count": summary.edge_count,
            "empty": summary.empty,
        }
        payload["memory_bounded"] = self._memory_bounded
        if include_nodes:
            payload["nodes"] = self._serialize_nodes(limit=limit)
        if include_edges:
            payload["edges"] = self._serialize_edges(limit=limit)
        return payload

    def query_graph(
        self,
        *,
        node_type: str | None = None,
        file_path: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Queries the graph for nodes matching specific criteria.

        Args:
            node_type (str | None): Filter by node type (e.g., 'file', 'symbol').
            file_path (str | None): Filter by a file path prefix.
            kind (str | None): Filter by symbol kind (e.g., 'function', 'class').
            limit (int): Maximum number of results to return. Defaults to 50.

        Returns:
            dict[str, Any]: A payload containing the search results and metadata.

        Raises:
            ValueError: If `limit` is not a positive integer.
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        if self._memory_bounded:
            return self._query_graph_bounded(
                node_type=node_type,
                file_path=file_path,
                kind=kind,
                limit=limit,
            )

        matches: list[dict[str, Any]] = []
        for node_id, attrs in self._graph.iter_nodes():
            if node_type and attrs.get("node_type") != node_type:
                continue
            if file_path and not str(attrs.get("file_path", "")).startswith(file_path):
                continue
            if kind and attrs.get("kind") != kind:
                continue
            matches.append({"node_id": node_id, **attrs})
            if len(matches) >= limit:
                break

        return {
            "count": len(matches),
            "limit": limit,
            "nodes": matches,
            "empty": self.is_empty,
            "memory_bounded": False,
        }

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Retrieves attributes for a specific node by its ID.

        Args:
            node_id (str): The unique identifier of the node.

        Returns:
            dict[str, Any] | None: The node's attributes, or None if it doesn't exist.

        Raises:
            ValueError: If `node_id` is empty.
        """
        if not node_id:
            raise ValueError("node_id is required")
        if self._memory_bounded:
            attrs = self._require_timeline().get_node_attrs(self._snapshot_id, node_id)
            if attrs is None:
                return None
            return {"node_id": node_id, **attrs}

        if not self._graph.has_node(node_id):
            return None
        return {"node_id": node_id, **self._graph.get_node(node_id)}

    def get_neighbors(
        self,
        node_id: str,
        *,
        direction: Literal["in", "out", "both"] = "both",
    ) -> dict[str, Any]:
        """Retrieves neighboring nodes for a specific node.

        Args:
            node_id (str): The unique identifier of the central node.
            direction (Literal["in", "out", "both"]): Which direction of edges to follow.
                Defaults to "both".

        Returns:
            dict[str, Any]: A payload describing the incoming and/or outgoing neighbors.

        Raises:
            ValueError: If `node_id` is empty.
            GraphStoreError: If the node does not exist in the graph.
        """
        if not node_id:
            raise ValueError("node_id is required")
        graph = self._graph
        if self._memory_bounded:
            graph = self._load_query_graph(
                seed_node_id=node_id,
                depth=self._neighborhood_depth,
            )
        if not graph.has_node(node_id):
            raise GraphStoreError(f"Node not found: {node_id}")

        incoming: list[dict[str, Any]] = []
        outgoing: list[dict[str, Any]] = []

        if direction in {"in", "both"}:
            for source, _, attrs in graph.in_edges(node_id):
                incoming.append(
                    {
                        "node_id": source,
                        "edge": attrs,
                        "node": graph.get_node(source),
                    }
                )

        if direction in {"out", "both"}:
            for _, target, attrs in graph.out_edges(node_id):
                outgoing.append(
                    {
                        "node_id": target,
                        "edge": attrs,
                        "node": graph.get_node(target),
                    }
                )

        return {
            "node_id": node_id,
            "direction": direction,
            "incoming": incoming,
            "outgoing": outgoing,
            "memory_bounded": self._memory_bounded,
        }

    def get_changes(
        self,
        snapshot_from: int,
        snapshot_to: int,
    ) -> dict[str, Any]:
        """Computes the differences between two graph snapshots.

        Args:
            snapshot_from (int): The ID of the older snapshot.
            snapshot_to (int): The ID of the newer snapshot.

        Returns:
            dict[str, Any]: A dictionary detailing added, modified, and removed nodes and edges.

        Raises:
            GraphStoreError: If the timeline database is not open.
            ValueError: If snapshot IDs are not positive integers.
        """
        if self._timeline is None:
            raise GraphStoreError("Timeline database is not open")
        if snapshot_from <= 0 or snapshot_to <= 0:
            raise ValueError("snapshot ids must be positive integers")

        delta = self._timeline.compute_delta(snapshot_from, snapshot_to)
        return asdict(delta)

    def get_timeline(
        self,
        *,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        """Retrieves the history of snapshots or a specific node.

        Args:
            node_id (str | None): If provided, returns the version history for this specific node.

        Returns:
            dict[str, Any]: A payload listing available snapshots and optionally node history.

        Raises:
            GraphStoreError: If the timeline database is not open.
        """
        if self._timeline is None:
            raise GraphStoreError("Timeline database is not open")

        snapshots = self._timeline.list_snapshots()
        payload: dict[str, Any] = {
            "snapshots": [self._snapshot_info_dict(item) for item in snapshots],
            "count": len(snapshots),
            "empty": len(snapshots) == 0,
        }
        if node_id:
            history = self._timeline.query_node_history(node_id)
            payload["node_id"] = node_id
            payload["node_history"] = [
                self._history_entry_dict(entry) for entry in history
            ]
        return payload

    def get_dead_code(
        self,
        *,
        include_generated: bool = False,
        include_public_api: bool = False,
    ) -> list[str]:
        """Detects likely dead code by finding unreferenced symbols.

        Returns:
            list[str]: A list of node IDs corresponding to unreferenced symbols.
        """
        if self._analysis.use_stored_metrics:
            return list(self._analysis.stored_report().dead_code)
        return self._analysis.require_intelligence().detect_dead_code(
            include_generated=include_generated,
            include_public_api=include_public_api,
        )

    def get_entry_points(self) -> list[str]:
        """Detects entry points to the application (e.g., main scripts, public API).

        Returns:
            list[str]: A list of node IDs that act as entry points.
        """
        if self._analysis.use_stored_metrics:
            return list(self._analysis.stored_report().entry_points)
        return self._analysis.require_intelligence().detect_entry_points()

    def get_god_nodes(self, *, include_generated: bool = False) -> list[dict[str, Any]]:
        """Identifies highly connected or overly complex nodes (God Nodes).

        Returns:
            list[dict[str, Any]]: A list of dictionaries containing 'node_id' and a severity 'score'.
        """
        if self._analysis.use_stored_metrics:
            return [
                {"node_id": node_id, "score": score}
                for node_id, score in self._analysis.stored_report().god_nodes
            ]
        return [
            {"node_id": node_id, "score": score}
            for node_id, score in self._analysis.require_intelligence().detect_god_nodes(
                include_generated=include_generated
            )
        ]

    def get_circular_deps(self) -> list[list[str]]:
        """Detects cycles in the import or dependency graph.

        Returns:
            list[list[str]]: A list of cycles, where each cycle is a list of node IDs.
        """
        if self._analysis.use_stored_metrics:
            return [
                list(cycle)
                for cycle in self._analysis.stored_report().circular_dependencies
            ]
        return self._analysis.require_intelligence().detect_circular_dependencies()

    def get_coupling_metrics(
        self,
        *,
        limit: int = 25,
        include_generated: bool = False,
        min_cbo: int | None = None,
    ) -> dict[str, Any]:
        """Return Chidamber--Kemerer CBO and LCOM metrics for class symbols.

        Args:
            limit (int): Maximum number of classes to return per ranking. Defaults to 25.
            include_generated (bool): Include vendor/generated paths when True.
            min_cbo (int | None): When set, filter tightly coupled classes to this minimum CBO.

        Returns:
            dict[str, Any]: Class coupling metrics and ranked CBO/LCOM lists.
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        if self._analysis.use_stored_metrics:
            stored = self._analysis.stored_report()
            cbo_rankings = stored.cbo_rankings[:limit]
            lcom_rankings = stored.lcom_rankings[:limit]
            lcom_by_node = dict(stored.lcom_rankings)
            threshold = min_cbo or 5
            tightly_coupled = [
                item for item in stored.tightly_coupled_classes if item[1] >= threshold
            ][:limit]
            return {
                "classes": [
                    {
                        "node_id": node_id,
                        "cbo": cbo,
                        "lcom": lcom_by_node.get(node_id, 0),
                    }
                    for node_id, cbo in cbo_rankings
                ],
                "cbo_rankings": [
                    {"node_id": node_id, "cbo": score} for node_id, score in cbo_rankings
                ],
                "lcom_rankings": [
                    {"node_id": node_id, "lcom": score} for node_id, score in lcom_rankings
                ],
                "tightly_coupled_classes": [
                    {"node_id": node_id, "cbo": score} for node_id, score in tightly_coupled
                ],
                "limit": limit,
            }

        intelligence = self._analysis.require_intelligence()
        metrics = intelligence.coupling_metrics(include_generated=include_generated)
        cbo_rankings = intelligence.cbo_rankings(include_generated=include_generated)[:limit]
        lcom_rankings = intelligence.lcom_rankings(include_generated=include_generated)[:limit]
        tightly_coupled = intelligence.tightly_coupled_classes(
            include_generated=include_generated,
            min_cbo=min_cbo or 5,
        )[:limit]

        return {
            "classes": metrics[:limit],
            "cbo_rankings": [
                {"node_id": node_id, "cbo": score} for node_id, score in cbo_rankings
            ],
            "lcom_rankings": [
                {"node_id": node_id, "lcom": score} for node_id, score in lcom_rankings
            ],
            "tightly_coupled_classes": [
                {"node_id": node_id, "cbo": score} for node_id, score in tightly_coupled
            ],
            "limit": limit,
        }

    def get_betweenness_centrality(
        self,
        *,
        limit: int = 25,
        include_generated: bool = False,
    ) -> dict[str, Any]:
        """Return file nodes ranked by betweenness centrality.

        Args:
            limit (int): Maximum number of nodes to return. Defaults to 25.
            include_generated (bool): Include vendor/generated paths when True.

        Returns:
            dict[str, Any]: Ranked betweenness scores for architectural choke points.
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        if self._analysis.use_stored_metrics:
            rankings = self._analysis.require_bounded_metrics().betweenness_rankings[:limit]
            return {
                "rankings": [
                    {"node_id": node_id, "betweenness_centrality": score}
                    for node_id, score in rankings
                ],
                "limit": limit,
            }
        graph = self._analysis.betweenness_graph()

        rankings = GraphClusterer().betweenness_rankings(
            graph,
            include_generated=include_generated,
        )[:limit]
        return {
            "rankings": [
                {"node_id": node_id, "betweenness_centrality": score}
                for node_id, score in rankings
            ],
            "limit": limit,
        }

    def get_complexity(
        self,
        *,
        limit: int = 25,
        include_generated: bool = False,
    ) -> list[dict[str, Any]]:
        """Ranks nodes by their computed complexity score.

        Args:
            limit (int): Maximum number of nodes to return. Defaults to 25.

        Returns:
            list[dict[str, Any]]: A list of dictionaries containing 'node_id' and 'complexity'.

        Raises:
            ValueError: If `limit` is not a positive integer.
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        if self._analysis.use_stored_metrics:
            rankings = self._analysis.stored_report().complexity_rankings[:limit]
        else:
            rankings = self._analysis.require_intelligence().complexity_rankings(
                include_generated=include_generated
            )[:limit]
        return [{"node_id": node_id, "complexity": score} for node_id, score in rankings]

    def get_churn(
        self,
        *,
        file_path: str | None = None,
        snapshot_from: int | None = None,
        snapshot_to: int | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Analyzes how frequently nodes or a specific file have changed over time.

        Args:
            file_path (str | None): Analyze churn for a specific file path.
            snapshot_from (int | None): Limit analysis starting from this snapshot ID.
            snapshot_to (int | None): Limit analysis ending at this snapshot ID.
            limit (int): Maximum number of nodes to return for overall rankings. Defaults to 25.

        Returns:
            dict[str, Any]: Churn rankings or the churn rate for the specific file.

        Raises:
            ValueError: If `limit` is not a positive integer.
            GraphStoreError: If a specific file is queried and the database is not open.
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        if file_path:
            if self._timeline is None:
                raise GraphStoreError("Timeline database is not open")
            rate = self._timeline.churn_rate(
                file_path,
                snapshot_from=snapshot_from,
                snapshot_to=snapshot_to,
            )
            return {"file_path": file_path, "churn_rate": rate}

        if self._analysis.use_stored_metrics:
            rankings = self._analysis.stored_report().churn_rankings[:limit]
        else:
            rankings = self._analysis.require_intelligence().churn_rankings()[:limit]
        return {
            "rankings": [{"node_id": node_id, "churn": score} for node_id, score in rankings],
            "limit": limit,
        }

    def search_nodes(
        self,
        query: str,
        *,
        node_type: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Performs a case-insensitive text search across node names and paths.

        Args:
            query (str): The text to search for.
            node_type (str | None): Optionally filter by a specific node type.
            limit (int): Maximum number of results to return. Defaults to 25.

        Returns:
            list[dict[str, Any]]: A list of matching nodes with their attributes.

        Raises:
            ValueError: If the query is empty or limit is not a positive integer.
        """
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        if self._memory_bounded:
            return self._search_nodes_bounded(query, node_type=node_type, limit=limit)

        needle = query.casefold()
        results: list[dict[str, Any]] = []
        for node_id, attrs in self._graph.iter_nodes():
            if node_type and attrs.get("node_type") != node_type:
                continue
            haystacks = [
                node_id,
                str(attrs.get("name", "")),
                str(attrs.get("qualified_name", "")),
                str(attrs.get("file_path", "")),
            ]
            if not any(needle in value.casefold() for value in haystacks if value):
                continue
            results.append({"node_id": node_id, **attrs})
            if len(results) >= limit:
                break
        return results

    def _load_stored_metrics(self) -> SnapshotMetrics | None:
        if self._timeline is None or self._snapshot_id is None:
            return None
        return self._timeline.metrics_store.load_snapshot(self._snapshot_id)

    def _bind_snapshot_metadata(
        self,
        info: SnapshotInfo | None,
        *,
        graph: Graph | None = None,
    ) -> None:
        if info is None:
            self._graph = create_graph("igraph")
            self._snapshot_id = None
            self._snapshot_label = None
            self._snapshot_node_count = 0
            self._snapshot_edge_count = 0
            self._intelligence = GraphIntelligence(self._graph)
            return

        if graph is not None:
            self._graph = graph
        elif self._memory_bounded:
            self._graph = create_graph("igraph")
        self._snapshot_id = info.snapshot_id
        self._snapshot_label = info.label
        self._snapshot_node_count = info.node_count
        self._snapshot_edge_count = info.edge_count
        self._intelligence = (
            None if self._memory_bounded else GraphIntelligence(self._graph)
        )

    def _require_timeline(self) -> GraphTimeline:
        if self._timeline is None:
            raise GraphStoreError("Timeline database is not open")
        if self._snapshot_id is None:
            raise GraphStoreError("No snapshot is loaded")
        return self._timeline

    def graph_for_genome(self) -> Graph:
        """Return the resident graph for legacy genome consumers.

        Memory-bounded callers must use the SQL-projected ``get_genome_*``
        methods; loading a complete snapshot here would violate that contract.
        """
        if self._memory_bounded:
            raise GraphStoreError(
                "Full genome graph is unavailable in memory-bounded mode; "
                "use get_genome_summary/get_genome_graph/get_genome_structure"
            )
        return self._graph

    def get_genome_summary(self) -> Any:
        """Build the genome overview without a full load in bounded mode."""
        return self._genome_provider().build_summary(snapshot_id=self._snapshot_id)

    def get_genome_graph(self, module_id: str) -> Any:
        """Build a module helix without loading unrelated modules."""
        return self._genome_provider().build_helix_graph(module_id)

    def get_genome_structure(self, module_id: str) -> Any:
        """Build a module structure tree without loading unrelated modules."""
        return self._genome_provider().build_structure_tree(module_id)

    def _genome_provider(self) -> Any:
        if self._memory_bounded and self._snapshot_id is not None:
            from codegenome.serializers.genome_sql_provider import SqlGenomeProvider

            return SqlGenomeProvider(self._require_timeline(), self._snapshot_id)

        from codegenome.serializers.genome_provider import GenomeProvider

        return GenomeProvider(self._graph)

    def _load_full_graph(self) -> Graph:
        timeline = self._require_timeline()
        return timeline.load_snapshot(self._snapshot_id)

    def _load_query_graph(
        self,
        *,
        seed_node_id: str | None = None,
        file_paths: set[str] | None = None,
        depth: int | None = None,
    ) -> Graph:
        timeline = self._require_timeline()
        if file_paths:
            return timeline.load_file_subgraph(self._snapshot_id, file_paths)
        if seed_node_id:
            return timeline.load_neighborhood(
                self._snapshot_id,
                seed_node_id,
                depth=self._neighborhood_depth if depth is None else depth,
                max_nodes=self._max_query_nodes,
            )
        return self._graph

    def _query_graph_bounded(
        self,
        *,
        node_type: str | None,
        file_path: str | None,
        kind: str | None,
        limit: int,
    ) -> dict[str, Any]:
        timeline = self._require_timeline()
        if file_path:
            file_paths = timeline.file_paths_with_prefix(
                self._snapshot_id,
                file_path,
                limit=self._max_query_nodes,
            )
            graph = timeline.load_file_subgraph(self._snapshot_id, file_paths)
        else:
            graph = self._graph

        matches: list[dict[str, Any]] = []
        for node_id, attrs in graph.iter_nodes():
            if node_type and attrs.get("node_type") != node_type:
                continue
            if file_path and not str(attrs.get("file_path", "")).startswith(file_path):
                continue
            if kind and attrs.get("kind") != kind:
                continue
            matches.append({"node_id": node_id, **attrs})
            if len(matches) >= limit:
                break

        return {
            "count": len(matches),
            "limit": limit,
            "nodes": matches,
            "empty": self._snapshot_node_count == 0,
            "memory_bounded": True,
        }

    def _search_nodes_bounded(
        self,
        query: str,
        *,
        node_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        timeline = self._require_timeline()
        return timeline.search_nodes(
            self._snapshot_id,
            query,
            node_type=node_type,
            limit=limit,
        )

    def _serialize_nodes(self, *, limit: int) -> list[dict[str, Any]]:
        if self._memory_bounded:
            return self._bounded_limited_nodes(limit)

        nodes: list[dict[str, Any]] = []
        for node_id, attrs in self._graph.iter_nodes():
            nodes.append({"node_id": node_id, **attrs})
            if len(nodes) >= limit:
                break
        return nodes

    def _bounded_limited_nodes(self, limit: int) -> list[dict[str, Any]]:
        return self._require_timeline().list_snapshot_nodes(
            self._snapshot_id,
            limit=limit,
        )

    def _serialize_edges(self, *, limit: int) -> list[dict[str, Any]]:
        if self._memory_bounded:
            return self._require_timeline().list_snapshot_edges(
                self._snapshot_id,
                limit=limit,
            )

        edges: list[dict[str, Any]] = []
        for source, target, attrs in self._graph.iter_edges():
            edges.append({"source": source, "target": target, **attrs})
            if len(edges) >= limit:
                break
        return edges

    def _latest_snapshot_id(self) -> int | None:
        if self._timeline is None:
            return self._snapshot_id
        snapshots = self._timeline.list_snapshots()
        return snapshots[-1].snapshot_id if snapshots else None

    @staticmethod
    def _snapshot_info_dict(info: SnapshotInfo) -> dict[str, Any]:
        return {
            "snapshot_id": info.snapshot_id,
            "created_at": info.created_at,
            "label": info.label,
            "node_count": info.node_count,
            "edge_count": info.edge_count,
        }

    @staticmethod
    def _history_entry_dict(entry: NodeHistoryEntry) -> dict[str, Any]:
        return {
            "snapshot_id": entry.snapshot_id,
            "created_at": entry.created_at,
            "attrs": entry.attrs,
        }
