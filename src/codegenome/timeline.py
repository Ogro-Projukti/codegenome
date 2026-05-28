"""SQLite-backed graph snapshot and delta timeline for Watcher."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codegenome.builder import file_node_id
from codegenome.graph_api import Graph, create_graph


@dataclass(frozen=True)
class SnapshotInfo:
    """Metadata for a stored graph snapshot."""

    snapshot_id: int
    created_at: float
    label: str | None
    node_count: int
    edge_count: int


@dataclass
class GraphDelta:
    """Structural diff between two snapshots."""

    snapshot_from: int
    snapshot_to: int
    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    modified_nodes: list[str] = field(default_factory=list)
    added_edges: list[tuple[str, str]] = field(default_factory=list)
    removed_edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class NodeHistoryEntry:
    """Historical node state at a snapshot."""

    snapshot_id: int
    created_at: float
    attrs: dict[str, Any]


class GraphTimeline:
    """Persist graph snapshots, compute deltas, and answer historical queries."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # MCP tool handlers run on worker threads; allow cross-thread reads/writes.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def close(self) -> None:
        self._conn.close()

    def record_snapshot(
        self,
        graph: Graph,
        *,
        label: str | None = None,
        created_at: float | None = None,
    ) -> int:
        timestamp = created_at if created_at is not None else time.time()
        cursor = self._conn.execute(
            """
            INSERT INTO snapshots (created_at, label, node_count, edge_count)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, label, graph.number_of_nodes(), graph.number_of_edges()),
        )
        snapshot_id = int(cursor.lastrowid)

        node_rows = [
            (snapshot_id, node_id, json.dumps(attrs, sort_keys=True))
            for node_id, attrs in graph.iter_nodes()
        ]
        if node_rows:
            self._conn.executemany(
                "INSERT INTO graph_nodes (snapshot_id, node_id, attrs_json) VALUES (?, ?, ?)",
                node_rows,
            )

        edge_rows = [
            (
                snapshot_id,
                source,
                target,
                json.dumps(edge_attrs, sort_keys=True),
            )
            for source, target, edge_attrs in graph.iter_edges()
        ]
        if edge_rows:
            self._conn.executemany(
                """
                INSERT INTO graph_edges (snapshot_id, source_id, target_id, attrs_json)
                VALUES (?, ?, ?, ?)
                """,
                edge_rows,
            )

        self._conn.commit()
        return snapshot_id

    def load_snapshot(self, snapshot_id: int) -> Graph:
        graph = create_graph("igraph")
        rows = self._conn.execute(
            "SELECT node_id, attrs_json FROM graph_nodes WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        for row in rows:
            graph.add_node(row["node_id"], **json.loads(row["attrs_json"]))

        edge_rows = self._conn.execute(
            """
            SELECT source_id, target_id, attrs_json
            FROM graph_edges
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchall()
        for row in edge_rows:
            graph.add_edge(
                row["source_id"],
                row["target_id"],
                **json.loads(row["attrs_json"]),
            )
        return graph

    def list_snapshots(self) -> list[SnapshotInfo]:
        rows = self._conn.execute(
            """
            SELECT snapshot_id, created_at, label, node_count, edge_count
            FROM snapshots
            ORDER BY snapshot_id ASC
            """
        ).fetchall()
        return [
            SnapshotInfo(
                snapshot_id=row["snapshot_id"],
                created_at=row["created_at"],
                label=row["label"],
                node_count=row["node_count"],
                edge_count=row["edge_count"],
            )
            for row in rows
        ]

    def compute_delta(self, snapshot_from: int, snapshot_to: int) -> GraphDelta:
        from_nodes = self._node_map(snapshot_from)
        to_nodes = self._node_map(snapshot_to)
        from_edges = self._edge_set(snapshot_from)
        to_edges = self._edge_set(snapshot_to)

        added_nodes = sorted(set(to_nodes) - set(from_nodes))
        removed_nodes = sorted(set(from_nodes) - set(to_nodes))
        modified_nodes = sorted(
            node
            for node in set(from_nodes) & set(to_nodes)
            if from_nodes[node] != to_nodes[node]
        )

        added_edges = sorted(to_edges - from_edges)
        removed_edges = sorted(from_edges - to_edges)

        return GraphDelta(
            snapshot_from=snapshot_from,
            snapshot_to=snapshot_to,
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            modified_nodes=modified_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
        )

    def query_node_history(self, node_id: str) -> list[NodeHistoryEntry]:
        rows = self._conn.execute(
            """
            SELECT s.snapshot_id, s.created_at, n.attrs_json
            FROM graph_nodes n
            JOIN snapshots s ON s.snapshot_id = n.snapshot_id
            WHERE n.node_id = ?
            ORDER BY s.snapshot_id ASC
            """,
            (node_id,),
        ).fetchall()
        return [
            NodeHistoryEntry(
                snapshot_id=row["snapshot_id"],
                created_at=row["created_at"],
                attrs=json.loads(row["attrs_json"]),
            )
            for row in rows
        ]

    def churn_rate(
        self,
        file_path: str,
        *,
        snapshot_from: int | None = None,
        snapshot_to: int | None = None,
    ) -> float:
        snapshots = self.list_snapshots()
        if len(snapshots) < 2:
            return 0.0

        start_id = snapshot_from if snapshot_from is not None else snapshots[0].snapshot_id
        end_id = snapshot_to if snapshot_to is not None else snapshots[-1].snapshot_id
        if start_id > end_id:
            start_id, end_id = end_id, start_id

        selected = [
            snapshot
            for snapshot in snapshots
            if start_id <= snapshot.snapshot_id <= end_id
        ]
        if len(selected) < 2:
            return 0.0

        node_id = file_node_id(file_path)
        changes = 0
        previous_attrs: dict[str, Any] | None = None
        for snapshot in selected:
            rows = self._conn.execute(
                """
                SELECT attrs_json
                FROM graph_nodes
                WHERE snapshot_id = ? AND node_id = ?
                """,
                (snapshot.snapshot_id, node_id),
            ).fetchall()
            if not rows:
                if previous_attrs is not None:
                    changes += 1
                previous_attrs = None
                continue

            attrs = json.loads(rows[0]["attrs_json"])
            if previous_attrs is not None and attrs != previous_attrs:
                changes += 1
            previous_attrs = attrs

        intervals = len(selected) - 1
        return changes / intervals

    def _initialize_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                label TEXT,
                node_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS graph_nodes (
                snapshot_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                attrs_json TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, node_id),
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS graph_edges (
                snapshot_id INTEGER NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                attrs_json TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, source_id, target_id),
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
            );
            """
        )
        self._conn.commit()

    def _node_map(self, snapshot_id: int) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT node_id, attrs_json FROM graph_nodes WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        return {row["node_id"]: row["attrs_json"] for row in rows}

    def _edge_set(self, snapshot_id: int) -> set[tuple[str, str]]:
        rows = self._conn.execute(
            """
            SELECT source_id, target_id
            FROM graph_edges
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchall()
        return {(row["source_id"], row["target_id"]) for row in rows}
