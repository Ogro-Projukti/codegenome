"""Tests for live graph monitor polling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegenome.live_graph_monitor import LiveGraphMonitor
from codegenome.workspace_metrics import WorkspaceMetrics


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    return root


def test_live_graph_monitor_rebuilds_when_metrics_increase(workspace: Path) -> None:
    engine = MagicMock()
    engine.workspace = workspace
    monitor = LiveGraphMonitor(engine, poll_interval_seconds=60.0)

    monitor._poll_once()
    assert engine.rebuild_incremental.call_count == 0

    (workspace / "new.py").write_text("x = 1\n", encoding="utf-8")
    monitor._poll_once()
    engine.rebuild_incremental.assert_called_once()
    assert monitor._previous == WorkspaceMetrics(file_count=2, line_count=2)


def test_live_graph_monitor_skips_rebuild_when_unchanged(workspace: Path) -> None:
    engine = MagicMock()
    engine.workspace = workspace
    monitor = LiveGraphMonitor(engine, poll_interval_seconds=60.0)

    monitor._poll_once()
    monitor._poll_once()

    engine.rebuild_incremental.assert_not_called()
