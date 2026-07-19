"""Read-only release-safety diagnostics for a CodeGenome workspace."""

from __future__ import annotations

import ipaddress
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from codegenome.graph_api import create_graph
from codegenome.live_server import LiveGraphServer
from codegenome.mcp_server import DEFAULT_HOST as MCP_DEFAULT_HOST
from codegenome.mcp_server import ENV_HOST as MCP_HOST_ENV
from codegenome.network_utils import resolve_bind_host
from codegenome.timeline import GraphTimeline


EXPECTED_EDGE_PRIMARY_KEY = ("snapshot_id", "source_id", "target_id", "edge_key")


@dataclass(frozen=True)
class DoctorCheck:
    """One independently actionable diagnostic result."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    """Complete doctor result for a workspace and database."""

    workspace: Path
    database: Path
    checks: tuple[DoctorCheck, ...]

    @property
    def passed(self) -> bool:
        """Return whether every diagnostic passed."""
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "status": "pass" if self.passed else "fail",
            "workspace": str(self.workspace),
            "database": str(self.database),
            "checks": [asdict(check) for check in self.checks],
        }


def run_doctor(workspace: Path, db_path: Path | None = None) -> DoctorReport:
    """Run network-boundary and persistence diagnostics without changing user data."""
    resolved_workspace = workspace.resolve()
    resolved_database = (db_path or resolved_workspace / ".genome" / "codegenome.db").resolve()
    checks = [*_network_checks(), *_database_checks(resolved_database)]
    checks.append(_multiedge_runtime_check())
    return DoctorReport(
        workspace=resolved_workspace,
        database=resolved_database,
        checks=tuple(checks),
    )


def _network_checks() -> list[DoctorCheck]:
    live_http_host = resolve_bind_host(allow_lan=False)
    live_websocket_host = LiveGraphServer().host
    default_hosts = {
        "live HTTP": live_http_host,
        "live WebSocket": live_websocket_host,
        "MCP HTTP": MCP_DEFAULT_HOST,
    }
    non_loopback = {
        name: host
        for name, host in default_hosts.items()
        if not _is_loopback(host)
    }
    default_check = DoctorCheck(
        name="network.loopback_defaults",
        passed=not non_loopback,
        detail=(
            ", ".join(f"{name}={host}" for name, host in default_hosts.items())
            if not non_loopback
            else "non-loopback defaults: "
            + ", ".join(f"{name}={host}" for name, host in non_loopback.items())
        ),
    )

    configured_host = os.getenv(MCP_HOST_ENV, MCP_DEFAULT_HOST)
    environment_check = DoctorCheck(
        name="network.environment",
        passed=_is_loopback(configured_host),
        detail=f"{MCP_HOST_ENV}={configured_host}",
    )
    return [default_check, environment_check]


def _database_checks(database: Path) -> list[DoctorCheck]:
    if not database.is_file():
        return [
            DoctorCheck(
                name="sqlite.database_present",
                passed=False,
                detail=f"database not found: {database}",
            )
        ]

    present = DoctorCheck(
        name="sqlite.database_present",
        passed=True,
        detail=str(database),
    )
    try:
        connection = _open_read_only(database)
    except sqlite3.Error as exc:
        return [
            present,
            DoctorCheck(
                name="sqlite.open_read_only",
                passed=False,
                detail=str(exc),
            ),
        ]

    try:
        quick_check_rows = connection.execute("PRAGMA quick_check").fetchall()
        quick_check_messages = [str(row[0]) for row in quick_check_rows]
        quick_check_ok = quick_check_messages == ["ok"]
        quick_check = DoctorCheck(
            name="sqlite.quick_check",
            passed=quick_check_ok,
            detail="; ".join(quick_check_messages),
        )

        columns = connection.execute("PRAGMA table_info(graph_edges)").fetchall()
        primary_key = tuple(
            row["name"]
            for row in sorted(
                (row for row in columns if row["pk"]),
                key=lambda row: row["pk"],
            )
        )
        schema_ok = primary_key == EXPECTED_EDGE_PRIMARY_KEY
        schema = DoctorCheck(
            name="sqlite.multiedge_schema",
            passed=schema_ok,
            detail=f"graph_edges primary key={primary_key!r}",
        )

        edge_count = _latest_edge_count_check(connection)
        return [present, quick_check, schema, edge_count]
    except sqlite3.Error as exc:
        return [
            present,
            DoctorCheck(
                name="sqlite.schema_query",
                passed=False,
                detail=str(exc),
            ),
        ]
    finally:
        connection.close()


def _latest_edge_count_check(connection: sqlite3.Connection) -> DoctorCheck:
    snapshot = connection.execute(
        """
        SELECT snapshot_id, edge_count
        FROM snapshots
        ORDER BY snapshot_id DESC
        LIMIT 1
        """
    ).fetchone()
    if snapshot is None:
        return DoctorCheck(
            name="sqlite.latest_edge_count",
            passed=True,
            detail="no snapshots recorded",
        )

    stored_rows = connection.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE snapshot_id = ?",
        (snapshot["snapshot_id"],),
    ).fetchone()[0]
    metadata_count = int(snapshot["edge_count"])
    return DoctorCheck(
        name="sqlite.latest_edge_count",
        passed=stored_rows == metadata_count,
        detail=(
            f"snapshot={snapshot['snapshot_id']}, metadata={metadata_count}, "
            f"rows={stored_rows}"
        ),
    )


def _multiedge_runtime_check() -> DoctorCheck:
    try:
        with tempfile.TemporaryDirectory(prefix="codegenome-doctor-") as temporary_root:
            graph = create_graph("igraph")
            graph.add_node("file:a.py", node_type="file", file_path="a.py")
            graph.add_node("file:b.py", node_type="file", file_path="b.py")
            edge_attrs = {"edge_type": "calls", "line": 42}
            graph.add_edge("file:a.py", "file:b.py", **edge_attrs)
            graph.add_edge("file:a.py", "file:b.py", **edge_attrs)

            timeline = GraphTimeline(Path(temporary_root) / "roundtrip.db")
            try:
                snapshot_id = timeline.record_snapshot(graph, label="doctor")
                stored_rows = timeline.connection.execute(
                    "SELECT COUNT(*) FROM graph_edges WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()[0]
                restored_edges = timeline.load_snapshot(snapshot_id).number_of_edges()
            finally:
                timeline.close()
    except Exception as exc:
        return DoctorCheck(
            name="sqlite.multiedge_roundtrip",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        )

    passed = stored_rows == restored_edges == 2
    return DoctorCheck(
        name="sqlite.multiedge_roundtrip",
        passed=passed,
        detail=f"input=2, rows={stored_rows}, reloaded={restored_edges}",
    )


def _open_read_only(database: Path) -> sqlite3.Connection:
    uri = f"{database.as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
