"""Tests for the read-only release-safety doctor."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from codegenome.cli import cli
from codegenome.doctor import run_doctor
from codegenome.graph_api import create_graph
from codegenome.timeline import GraphTimeline


def _healthy_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    database = workspace / ".genome" / "codegenome.db"
    database.parent.mkdir(parents=True)
    graph = create_graph("igraph")
    graph.add_node("file:a.py", node_type="file", file_path="a.py")
    graph.add_node("file:b.py", node_type="file", file_path="b.py")
    graph.add_edge("file:a.py", "file:b.py", edge_type="calls", line=42)
    graph.add_edge("file:a.py", "file:b.py", edge_type="calls", line=42)
    timeline = GraphTimeline(database)
    try:
        timeline.record_snapshot(graph, label="test")
    finally:
        timeline.close()
    return workspace, database


def test_doctor_passes_loopback_and_multiedge_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace, _database = _healthy_workspace(tmp_path)
    monkeypatch.delenv("CODEGENOME_MCP_HOST", raising=False)

    report = run_doctor(workspace)
    checks = {check.name: check for check in report.checks}

    assert report.passed
    assert checks["network.loopback_defaults"].passed
    assert checks["network.environment"].passed
    assert checks["sqlite.quick_check"].detail == "ok"
    assert checks["sqlite.multiedge_schema"].passed
    assert "metadata=2, rows=2" in checks["sqlite.latest_edge_count"].detail
    assert checks["sqlite.multiedge_roundtrip"].detail == "input=2, rows=2, reloaded=2"


def test_doctor_rejects_wildcard_host_from_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace, _database = _healthy_workspace(tmp_path)
    monkeypatch.setenv("CODEGENOME_MCP_HOST", "0.0.0.0")

    report = run_doctor(workspace)
    environment_check = next(
        check for check in report.checks if check.name == "network.environment"
    )

    assert not report.passed
    assert not environment_check.passed
    assert environment_check.detail == "CODEGENOME_MCP_HOST=0.0.0.0"


def test_doctor_detects_endpoint_only_edge_schema(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    database = workspace / ".genome" / "codegenome.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE snapshots (
            snapshot_id INTEGER PRIMARY KEY,
            created_at REAL NOT NULL,
            label TEXT,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL
        );
        CREATE TABLE graph_edges (
            snapshot_id INTEGER NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            attrs_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, source_id, target_id)
        );
        """
    )
    connection.close()
    monkeypatch.delenv("CODEGENOME_MCP_HOST", raising=False)

    report = run_doctor(workspace)
    schema_check = next(
        check for check in report.checks if check.name == "sqlite.multiedge_schema"
    )

    assert not report.passed
    assert not schema_check.passed
    assert "('snapshot_id', 'source_id', 'target_id')" in schema_check.detail


def test_doctor_cli_emits_machine_readable_report(tmp_path: Path, monkeypatch) -> None:
    workspace, database = _healthy_workspace(tmp_path)
    monkeypatch.delenv("CODEGENOME_MCP_HOST", raising=False)

    result = CliRunner().invoke(
        cli,
        ["doctor", "--path", str(workspace), "--db-path", str(database), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "pass"
    assert payload["database"] == str(database.resolve())
