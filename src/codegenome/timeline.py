"""SQLite-backed graph snapshot and delta timeline for CodeGenome.

This module provides the GraphTimeline class, which records full dependency
graphs into a SQLite database, allowing for historical analysis and
structural diffing (deltas) between points in time.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codegenome.builder import file_node_id
from codegenome.gdr_store import GDRStore
from codegenome.graph_api import Graph, create_graph
from codegenome.graph_loader import node_file_path


@dataclass(frozen=True)
class SnapshotInfo:
    """Metadata for a stored graph snapshot.

    Attributes:
        snapshot_id (int): Unique identifier for the snapshot.
        created_at (float): Unix timestamp of snapshot creation.
        label (str | None): Optional descriptive label.
        node_count (int): Number of nodes in the graph at this snapshot.
        edge_count (int): Number of edges in the graph at this snapshot.
    """

    snapshot_id: int
    created_at: float
    label: str | None
    node_count: int
    edge_count: int


@dataclass
class GraphDelta:
    """Structural diff between two snapshots.

    Attributes:
        snapshot_from (int): ID of the base snapshot.
        snapshot_to (int): ID of the target snapshot.
        added_nodes (list[str]): Node IDs present in target but not base.
        removed_nodes (list[str]): Node IDs present in base but not target.
        modified_nodes (list[str]): Node IDs with changed attributes.
        added_edges (list[tuple[str, str]]): Edges present in target but not base.
        removed_edges (list[tuple[str, str]]): Edges present in base but not target.
    """

    snapshot_from: int
    snapshot_to: int
    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    modified_nodes: list[str] = field(default_factory=list)
    added_edges: list[tuple[str, str]] = field(default_factory=list)
    removed_edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class NodeHistoryEntry:
    """Historical node state at a snapshot.

    Attributes:
        snapshot_id (int): ID of the snapshot where the node was recorded.
        created_at (float): Timestamp of the snapshot.
        attrs (dict[str, Any]): Node attributes at that point in time.
    """

    snapshot_id: int
    created_at: float
    attrs: dict[str, Any]


class GraphTimeline:
    """Persist graph snapshots, compute deltas, and answer historical queries.

    This class uses a SQLite database to securely log states of the
    dependency graph and evaluate changes over time (churn rate, deltas).
    """

    def __init__(self, db_path: Path | str) -> None:
        """Initialize the GraphTimeline.

        Args:
            db_path (Path | str): Path to the SQLite timeline database.
        """
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # MCP tool handlers run on worker threads; allow cross-thread reads/writes.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()
        self._gdr_store = GDRStore(self._conn)
        self._gdr_store.initialize_schema()

    @property
    def gdr_store(self) -> GDRStore:
        """Snapshot-scoped Global Dependency Registry persistence."""
        return self._gdr_store

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def record_snapshot(
        self,
        graph: Graph,
        *,
        label: str | None = None,
        created_at: float | None = None,
    ) -> int:
        """Save a full copy of the current graph to the database.

        Args:
            graph (Graph): The current dependency graph.
            label (str | None): An optional string label for the snapshot.
            created_at (float | None): Explicit timestamp. Defaults to current time.

        Returns:
            int: The ID of the newly created snapshot.
        """
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

        edge_rows_dict = {}
        for source, target, edge_attrs in graph.iter_edges():
            edge_rows_dict[(source, target)] = (
                snapshot_id,
                source,
                target,
                json.dumps(edge_attrs, sort_keys=True),
            )
        edge_rows = list(edge_rows_dict.values())
        if edge_rows:
            self._conn.executemany(
                """
                INSERT INTO graph_edges (snapshot_id, source_id, target_id, attrs_json)
                VALUES (?, ?, ?, ?)
                """,
                edge_rows,
            )

        self._index_graph_node_files(snapshot_id, graph)
        self._conn.commit()
        return snapshot_id

    def load_snapshot(self, snapshot_id: int) -> Graph:
        """Reconstruct a dependency graph from a specific snapshot ID.

        Args:
            snapshot_id (int): The ID of the snapshot to load.

        Returns:
            Graph: The reconstructed graph instance.
        """
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

    def has_node_file_index(self, snapshot_id: int) -> bool:
        """Return True when graph_node_files rows exist for a snapshot."""
        row = self._conn.execute(
            "SELECT 1 FROM graph_node_files WHERE snapshot_id = ? LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        return row is not None

    def load_file_subgraph(
        self,
        snapshot_id: int,
        file_paths: set[str],
        *,
        include_cross_edges: bool = True,
    ) -> Graph:
        """Load nodes and edges for a set of file paths without loading the full snapshot."""
        if not file_paths:
            return create_graph("igraph")

        graph = create_graph("igraph")
        node_ids = self._node_ids_for_files(snapshot_id, file_paths)
        if not node_ids:
            return graph

        placeholders = ", ".join("?" for _ in node_ids)
        rows = self._conn.execute(
            f"""
            SELECT node_id, attrs_json
            FROM graph_nodes
            WHERE snapshot_id = ? AND node_id IN ({placeholders})
            """,
            (snapshot_id, *sorted(node_ids)),
        ).fetchall()
        for row in rows:
            graph.add_node(row["node_id"], **json.loads(row["attrs_json"]))

        edge_rows = self._conn.execute(
            f"""
            SELECT source_id, target_id, attrs_json
            FROM graph_edges
            WHERE snapshot_id = ?
              AND source_id IN ({placeholders})
              AND target_id IN ({placeholders})
            """,
            (snapshot_id, *sorted(node_ids), *sorted(node_ids)),
        ).fetchall()

        for row in edge_rows:
            graph.add_edge(
                row["source_id"],
                row["target_id"],
                **json.loads(row["attrs_json"]),
            )
        return graph

    def load_neighborhood(
        self,
        snapshot_id: int,
        seed_node_id: str,
        *,
        depth: int = 1,
        max_nodes: int = 500,
    ) -> Graph:
        """Load a bounded BFS neighborhood around a seed node."""
        if depth < 1 or max_nodes < 1:
            return create_graph("igraph")

        frontier = {seed_node_id}
        visited: set[str] = set()
        edges: list[tuple[str, str, str]] = []

        for _ in range(depth):
            if not frontier or len(visited) >= max_nodes:
                break
            batch = sorted(frontier - visited)
            if not batch:
                break
            remaining = max_nodes - len(visited)
            batch = batch[:remaining]
            placeholders = ", ".join("?" for _ in batch)
            rows = self._conn.execute(
                f"""
                SELECT source_id, target_id, attrs_json
                FROM graph_edges
                WHERE snapshot_id = ?
                  AND (source_id IN ({placeholders}) OR target_id IN ({placeholders}))
                """,
                (snapshot_id, *batch, *batch),
            ).fetchall()

            next_frontier: set[str] = set()
            for row in rows:
                source = row["source_id"]
                target = row["target_id"]
                edges.append((source, target, row["attrs_json"]))
                if source in batch:
                    next_frontier.add(target)
                if target in batch:
                    next_frontier.add(source)

            visited.update(batch)
            frontier = next_frontier

        graph = create_graph("igraph")
        if seed_node_id not in visited:
            visited.add(seed_node_id)

        placeholders = ", ".join("?" for _ in visited)
        node_rows = self._conn.execute(
            f"""
            SELECT node_id, attrs_json
            FROM graph_nodes
            WHERE snapshot_id = ? AND node_id IN ({placeholders})
            """,
            (snapshot_id, *sorted(visited)),
        ).fetchall()
        for row in node_rows:
            graph.add_node(row["node_id"], **json.loads(row["attrs_json"]))

        seen_edges: set[tuple[str, str]] = set()
        for source, target, attrs_json in edges:
            if source in visited and target in visited:
                key = (source, target)
                if key not in seen_edges:
                    graph.add_edge(source, target, **json.loads(attrs_json))
                    seen_edges.add(key)
        return graph

    def record_snapshot_patch(
        self,
        base_snapshot_id: int,
        changed_files: set[str],
        fragment: Graph,
        *,
        label: str | None = None,
        created_at: float | None = None,
    ) -> int:
        """Create a new snapshot by patching only the files that changed."""
        changed = {path for path in changed_files if path}
        timestamp = created_at if created_at is not None else time.time()

        kept_node_ids = self._node_ids_for_files(
            base_snapshot_id,
            self._all_indexed_files(base_snapshot_id) - changed,
        )
        changed_node_ids = {
            node_id
            for node_id, attrs in fragment.iter_nodes()
            if (node_file_path(node_id, attrs) or "") in changed
        }
        all_node_ids = kept_node_ids | changed_node_ids

        kept_edges = self._edges_for_node_ids(base_snapshot_id, kept_node_ids)
        fragment_edges = self._edges_for_node_ids_in_fragment(fragment, all_node_ids)
        all_edges = self._merge_edge_maps(kept_edges, fragment_edges)

        cursor = self._conn.execute(
            """
            INSERT INTO snapshots (created_at, label, node_count, edge_count)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, label, len(all_node_ids), len(all_edges)),
        )
        snapshot_id = int(cursor.lastrowid)
        edge_items = list(all_edges.items())

        node_rows: list[tuple[int, str, str]] = []
        if kept_node_ids:
            placeholders = ", ".join("?" for _ in kept_node_ids)
            rows = self._conn.execute(
                f"""
                SELECT node_id, attrs_json
                FROM graph_nodes
                WHERE snapshot_id = ? AND node_id IN ({placeholders})
                """,
                (base_snapshot_id, *sorted(kept_node_ids)),
            ).fetchall()
            node_rows.extend((snapshot_id, row["node_id"], row["attrs_json"]) for row in rows)

        for node_id in sorted(changed_node_ids):
            node_rows.append((snapshot_id, node_id, json.dumps(fragment.get_node(node_id), sort_keys=True)))

        if node_rows:
            self._conn.executemany(
                "INSERT INTO graph_nodes (snapshot_id, node_id, attrs_json) VALUES (?, ?, ?)",
                node_rows,
            )

        if edge_items:
            edge_rows = [
                (snapshot_id, source, target, json.dumps(attrs, sort_keys=True))
                for (source, target), attrs in sorted(edge_items)
            ]
            self._conn.executemany(
                """
                INSERT INTO graph_edges (snapshot_id, source_id, target_id, attrs_json)
                VALUES (?, ?, ?, ?)
                """,
                edge_rows,
            )

        self._copy_graph_node_file_index(
            snapshot_id,
            base_snapshot_id,
            kept_node_ids,
            changed_node_ids,
            fragment,
        )
        self._conn.commit()
        return snapshot_id

    def list_snapshots(self) -> list[SnapshotInfo]:
        """List all recorded snapshots in ascending order.

        Returns:
            list[SnapshotInfo]: A list of metadata objects for each snapshot.
        """
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
        """Compute the structural differences between two snapshots.

        Args:
            snapshot_from (int): The starting snapshot ID.
            snapshot_to (int): The ending snapshot ID.

        Returns:
            GraphDelta: An object detailing added, removed, and modified elements.
        """
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
        """Retrieve the historical states of a specific node across all snapshots.

        Args:
            node_id (str): The ID of the node to query.

        Returns:
            list[NodeHistoryEntry]: A chronological list of the node's state history.
        """
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
        """Calculate the churn rate for a specific file between snapshots.

        The churn rate is defined as the number of snapshots where the file's
        node attributes changed, divided by the total number of snapshot intervals.

        Args:
            file_path (str): The file path to calculate churn for.
            snapshot_from (int | None): Starting snapshot ID (inclusive).
            snapshot_to (int | None): Ending snapshot ID (inclusive).

        Returns:
            float: A value between 0.0 and 1.0 representing the churn rate.
        """
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

            CREATE TABLE IF NOT EXISTS graph_node_files (
                snapshot_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, node_id),
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_graph_node_files_path
                ON graph_node_files (snapshot_id, file_path);
            """
        )
        self._conn.commit()

    def _index_graph_node_files(self, snapshot_id: int, graph: Graph) -> None:
        rows: list[tuple[int, str, str]] = []
        for node_id, attrs in graph.iter_nodes():
            file_path = node_file_path(node_id, attrs)
            if file_path:
                rows.append((snapshot_id, node_id, file_path))
        self._conn.execute("DELETE FROM graph_node_files WHERE snapshot_id = ?", (snapshot_id,))
        if rows:
            self._conn.executemany(
                """
                INSERT INTO graph_node_files (snapshot_id, node_id, file_path)
                VALUES (?, ?, ?)
                """,
                rows,
            )

    def _copy_graph_node_file_index(
        self,
        snapshot_id: int,
        base_snapshot_id: int,
        kept_node_ids: set[str],
        changed_node_ids: set[str],
        fragment: Graph,
    ) -> None:
        self._conn.execute("DELETE FROM graph_node_files WHERE snapshot_id = ?", (snapshot_id,))
        if kept_node_ids and self.has_node_file_index(base_snapshot_id):
            placeholders = ", ".join("?" for _ in kept_node_ids)
            self._conn.execute(
                f"""
                INSERT INTO graph_node_files (snapshot_id, node_id, file_path)
                SELECT ?, node_id, file_path
                FROM graph_node_files
                WHERE snapshot_id = ? AND node_id IN ({placeholders})
                """,
                (snapshot_id, base_snapshot_id, *sorted(kept_node_ids)),
            )
        elif kept_node_ids:
            placeholders = ", ".join("?" for _ in kept_node_ids)
            rows = self._conn.execute(
                f"""
                SELECT node_id, attrs_json
                FROM graph_nodes
                WHERE snapshot_id = ? AND node_id IN ({placeholders})
                """,
                (base_snapshot_id, *sorted(kept_node_ids)),
            ).fetchall()
            index_rows = []
            for row in rows:
                file_path = node_file_path(row["node_id"], json.loads(row["attrs_json"]))
                if file_path:
                    index_rows.append((snapshot_id, row["node_id"], file_path))
            if index_rows:
                self._conn.executemany(
                    "INSERT INTO graph_node_files (snapshot_id, node_id, file_path) VALUES (?, ?, ?)",
                    index_rows,
                )

        changed_rows: list[tuple[int, str, str]] = []
        for node_id in sorted(changed_node_ids):
            file_path = node_file_path(node_id, fragment.get_node(node_id))
            if file_path:
                changed_rows.append((snapshot_id, node_id, file_path))
        if changed_rows:
            self._conn.executemany(
                "INSERT INTO graph_node_files (snapshot_id, node_id, file_path) VALUES (?, ?, ?)",
                changed_rows,
            )

    def _node_ids_for_files(self, snapshot_id: int, file_paths: set[str]) -> set[str]:
        if not file_paths:
            return set()
        if self.has_node_file_index(snapshot_id):
            placeholders = ", ".join("?" for _ in file_paths)
            rows = self._conn.execute(
                f"""
                SELECT node_id
                FROM graph_node_files
                WHERE snapshot_id = ? AND file_path IN ({placeholders})
                """,
                (snapshot_id, *sorted(file_paths)),
            ).fetchall()
            return {row["node_id"] for row in rows}

        result: set[str] = set()
        wanted = set(file_paths)
        rows = self._conn.execute(
            "SELECT node_id, attrs_json FROM graph_nodes WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        for row in rows:
            attrs = json.loads(row["attrs_json"])
            if node_file_path(row["node_id"], attrs) in wanted:
                result.add(row["node_id"])
        return result

    def _all_indexed_files(self, snapshot_id: int) -> set[str]:
        if self.has_node_file_index(snapshot_id):
            rows = self._conn.execute(
                "SELECT DISTINCT file_path FROM graph_node_files WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchall()
            return {row["file_path"] for row in rows}

        files: set[str] = set()
        rows = self._conn.execute(
            "SELECT node_id, attrs_json FROM graph_nodes WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        for row in rows:
            file_path = node_file_path(row["node_id"], json.loads(row["attrs_json"]))
            if file_path:
                files.add(file_path)
        return files

    def _edges_for_node_ids(
        self,
        snapshot_id: int,
        node_ids: set[str],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not node_ids:
            return {}
        placeholders = ", ".join("?" for _ in node_ids)
        rows = self._conn.execute(
            f"""
            SELECT source_id, target_id, attrs_json
            FROM graph_edges
            WHERE snapshot_id = ?
              AND source_id IN ({placeholders})
              AND target_id IN ({placeholders})
            """,
            (snapshot_id, *sorted(node_ids), *sorted(node_ids)),
        ).fetchall()
        return {
            (row["source_id"], row["target_id"]): json.loads(row["attrs_json"])
            for row in rows
        }

    @staticmethod
    def _edges_for_node_ids_in_fragment(
        fragment: Graph,
        node_ids: set[str],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        allowed = set(node_ids)
        return {
            (source, target): dict(attrs)
            for source, target, attrs in fragment.iter_edges()
            if source in allowed and target in allowed
        }

    @staticmethod
    def _merge_edge_maps(
        *edge_maps: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for edge_map in edge_maps:
            merged.update(edge_map)
        return merged

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
