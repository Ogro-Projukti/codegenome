"""Tests for timeline dump CLI flags."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from codegenome.graph_api import create_graph
import pytest

from codegenome.timeline import GraphTimeline


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    graph = create_graph("igraph")
    graph.add_node(
        "file:alpha.py",
        node_type="file",
        file_path="alpha.py",
        churn=2,
        complexity=1,
    )
    db_path = tmp_path / "test.db"
    timeline = GraphTimeline(db_path)
    timeline.record_snapshot(graph, label="baseline")
    timeline.close()
    return db_path


def test_dump_timeline_cli(sample_db: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codegenome",
            "--workspace",
            str(sample_db.parent),
            "--db-path",
            str(sample_db),
            "--dump-timeline",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["empty"] is False


def test_dump_changes_cli(sample_db: Path) -> None:
    graph = create_graph("igraph")
    graph.add_node(
        "file:beta.py",
        node_type="file",
        file_path="beta.py",
        churn=1,
        complexity=1,
    )
    timeline = GraphTimeline(sample_db)
    timeline.record_snapshot(graph, label="second")
    timeline.close()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codegenome",
            "--workspace",
            str(sample_db.parent),
            "--db-path",
            str(sample_db),
            "--dump-changes",
            "--snapshot-from",
            "1",
            "--snapshot-to",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["snapshot_from"] == 1
    assert payload["snapshot_to"] == 2
    assert "file:beta.py" in payload["added_nodes"]
