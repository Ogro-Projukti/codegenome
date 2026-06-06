"""Persist and load precomputed global intelligence metrics per snapshot."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass

from codegenome.intelligence import IntelligenceReport, report_from_dict, report_to_dict


SCHEMA_VERSION = "1"
METRICS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshot_metrics (
    snapshot_id INTEGER PRIMARY KEY,
    metrics_json TEXT NOT NULL,
    computed_at REAL NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);
"""


@dataclass(frozen=True)
class SnapshotMetrics:
    """Global metrics computed from a full-graph analysis."""

    report: IntelligenceReport
    betweenness_rankings: tuple[tuple[str, float], ...] = ()


class SnapshotMetricsStore:
    """Read and write precomputed metrics for graph snapshots."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def initialize_schema(self) -> None:
        """Create metrics tables if missing."""
        self._conn.executescript(METRICS_SCHEMA_SQL)
        self._conn.execute(
            """
            INSERT INTO schema_meta (key, value)
            VALUES ('snapshot_metrics_schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SCHEMA_VERSION,),
        )
        self._conn.commit()

    def has_snapshot(self, snapshot_id: int) -> bool:
        """Return True when metrics exist for a snapshot."""
        row = self._conn.execute(
            "SELECT 1 FROM snapshot_metrics WHERE snapshot_id = ? LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        return row is not None

    def persist_snapshot(
        self,
        snapshot_id: int,
        metrics: SnapshotMetrics,
        *,
        computed_at: float | None = None,
    ) -> None:
        """Write global metrics for a snapshot."""
        timestamp = computed_at if computed_at is not None else time.time()
        payload = _metrics_to_dict(metrics)
        self._conn.execute(
            """
            INSERT INTO snapshot_metrics (snapshot_id, metrics_json, computed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                metrics_json = excluded.metrics_json,
                computed_at = excluded.computed_at
            """,
            (snapshot_id, json.dumps(payload, sort_keys=True), timestamp),
        )
        self._conn.commit()

    def load_snapshot(self, snapshot_id: int) -> SnapshotMetrics | None:
        """Load stored metrics for a snapshot."""
        row = self._conn.execute(
            "SELECT metrics_json FROM snapshot_metrics WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        return _metrics_from_dict(json.loads(row["metrics_json"]))

    def copy_snapshot(self, base_snapshot_id: int, snapshot_id: int) -> bool:
        """Copy metrics from a base snapshot to a patched snapshot."""
        row = self._conn.execute(
            """
            SELECT metrics_json, computed_at
            FROM snapshot_metrics
            WHERE snapshot_id = ?
            """,
            (base_snapshot_id,),
        ).fetchone()
        if row is None:
            return False
        self._conn.execute(
            """
            INSERT INTO snapshot_metrics (snapshot_id, metrics_json, computed_at)
            VALUES (?, ?, ?)
            """,
            (snapshot_id, row["metrics_json"], row["computed_at"]),
        )
        self._conn.commit()
        return True


def _metrics_to_dict(metrics: SnapshotMetrics) -> dict:
    return {
        "report": report_to_dict(metrics.report),
        "betweenness_rankings": [
            {"node": node, "score": score}
            for node, score in metrics.betweenness_rankings
        ],
    }


def _metrics_from_dict(payload: dict) -> SnapshotMetrics:
    report_data = payload.get("report")
    report = report_from_dict(report_data) if report_data else IntelligenceReport()
    betweenness = tuple(
        (str(item["node"]), float(item["score"]))
        for item in payload.get("betweenness_rankings", [])
    )
    return SnapshotMetrics(report=report, betweenness_rankings=betweenness)
