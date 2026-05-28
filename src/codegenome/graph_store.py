"""Graph query layer for the Watcher MCP server."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from codegenome.graph_api import Graph, create_graph
from codegenome.intelligence import GraphIntelligence
from codegenome.timeline import GraphTimeline, NodeHistoryEntry, SnapshotInfo


class GraphStoreError(Exception):
    """Raised when graph store operations fail."""


@dataclass(frozen=True)
class GraphSummary:
    snapshot_id: int | None
    node_count: int
    edge_count: int
    label: str | None
    empty: bool


class GraphStore:
    """Load and query a Watcher timeline database."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).resolve()
        self._timeline: GraphTimeline | None = None
        self._graph: Graph = create_graph("igraph")
        self._snapshot_id: int | None = None
        self._snapshot_label: str | None = None
        self._intelligence: GraphIntelligence | None = None

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def snapshot_id(self) -> int | None:
        return self._snapshot_id

    @property
    def is_empty(self) -> bool:
        return self._graph.number_of_nodes() == 0

    def open(self) -> None:
        """Open the timeline database and load the latest snapshot."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._timeline = GraphTimeline(self.db_path)
        except sqlite3.Error as exc:
            raise GraphStoreError(f"Failed to open database at {self.db_path}: {exc}") from exc

        snapshots = self._timeline.list_snapshots()
        if not snapshots:
            self._graph = create_graph("igraph")
            self._snapshot_id = None
            self._snapshot_label = None
            self._intelligence = GraphIntelligence(self._graph)
            return

        latest = snapshots[-1]
        try:
            self._graph = self._timeline.load_snapshot(latest.snapshot_id)
        except sqlite3.Error as exc:
            raise GraphStoreError(
                f"Failed to load snapshot {latest.snapshot_id}: {exc}"
            ) from exc

        self._snapshot_id = latest.snapshot_id
        self._snapshot_label = latest.label
        self._intelligence = GraphIntelligence(self._graph)

    def close(self) -> None:
        if self._timeline is not None:
            self._timeline.close()
            self._timeline = None

    def summary(self) -> GraphSummary:
        return GraphSummary(
            snapshot_id=self._snapshot_id,
            node_count=self._graph.number_of_nodes(),
            edge_count=self._graph.number_of_edges(),
            label=self._snapshot_label,
            empty=self.is_empty,
        )

    def get_graph(
        self,
        *,
        include_nodes: bool = False,
        include_edges: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        summary = self.summary()
        payload: dict[str, Any] = {
            "snapshot_id": summary.snapshot_id,
            "label": summary.label,
            "node_count": summary.node_count,
            "edge_count": summary.edge_count,
            "empty": summary.empty,
        }
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
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

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
        }

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if not node_id:
            raise ValueError("node_id is required")
        if not self._graph.has_node(node_id):
            return None
        return {"node_id": node_id, **self._graph.get_node(node_id)}

    def get_neighbors(
        self,
        node_id: str,
        *,
        direction: Literal["in", "out", "both"] = "both",
    ) -> dict[str, Any]:
        if not node_id:
            raise ValueError("node_id is required")
        if not self._graph.has_node(node_id):
            raise GraphStoreError(f"Node not found: {node_id}")

        incoming: list[dict[str, Any]] = []
        outgoing: list[dict[str, Any]] = []

        if direction in {"in", "both"}:
            for source, _, attrs in self._graph.in_edges(node_id):
                incoming.append(
                    {
                        "node_id": source,
                        "edge": attrs,
                        "node": self._graph.get_node(source),
                    }
                )

        if direction in {"out", "both"}:
            for _, target, attrs in self._graph.out_edges(node_id):
                outgoing.append(
                    {
                        "node_id": target,
                        "edge": attrs,
                        "node": self._graph.get_node(target),
                    }
                )

        return {
            "node_id": node_id,
            "direction": direction,
            "incoming": incoming,
            "outgoing": outgoing,
        }

    def get_changes(
        self,
        snapshot_from: int,
        snapshot_to: int,
    ) -> dict[str, Any]:
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

    def get_dead_code(self) -> list[str]:
        return self._require_intelligence().detect_dead_code()

    def get_entry_points(self) -> list[str]:
        return self._require_intelligence().detect_entry_points()

    def get_god_nodes(self) -> list[dict[str, Any]]:
        return [
            {"node_id": node_id, "score": score}
            for node_id, score in self._require_intelligence().detect_god_nodes()
        ]

    def get_circular_deps(self) -> list[list[str]]:
        return self._require_intelligence().detect_circular_dependencies()

    def get_complexity(self, *, limit: int = 25) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        rankings = self._require_intelligence().complexity_rankings()[:limit]
        return [{"node_id": node_id, "complexity": score} for node_id, score in rankings]

    def get_churn(
        self,
        *,
        file_path: str | None = None,
        snapshot_from: int | None = None,
        snapshot_to: int | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
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

        rankings = self._require_intelligence().churn_rankings()[:limit]
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
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

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

    def _require_intelligence(self) -> GraphIntelligence:
        if self._intelligence is None:
            raise GraphStoreError("Intelligence engine is not initialized")
        return self._intelligence

    def _serialize_nodes(self, *, limit: int) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for node_id, attrs in self._graph.iter_nodes():
            nodes.append({"node_id": node_id, **attrs})
            if len(nodes) >= limit:
                break
        return nodes

    def _serialize_edges(self, *, limit: int) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for source, target, attrs in self._graph.iter_edges():
            edges.append({"source": source, "target": target, **attrs})
            if len(edges) >= limit:
                break
        return edges

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
