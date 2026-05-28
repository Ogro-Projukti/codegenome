"""Tests for workspace metrics scanning."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.workspace_metrics import (
    WorkspaceMetrics,
    WorkspaceMetricsScanner,
    metrics_increased,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\nline2\n", encoding="utf-8")
    (root / "utils.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (root / "ignored.txt").write_text("skip me\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.txt\nbuild/\n", encoding="utf-8")
    build_dir = root / "build"
    build_dir.mkdir()
    (build_dir / "artifact.txt").write_text("ignored by gitignore\n", encoding="utf-8")
    return root


def test_workspace_metrics_respects_gitignore(workspace: Path) -> None:
    scanner = WorkspaceMetricsScanner(workspace)
    metrics = scanner.scan()

    assert metrics.file_count == 3
    assert metrics.line_count == 6


def test_workspace_metrics_detects_new_file(workspace: Path) -> None:
    scanner = WorkspaceMetricsScanner(workspace)
    previous = scanner.scan()
    (workspace / "new.py").write_text("x = 1\n", encoding="utf-8")
    current = scanner.scan()

    assert metrics_increased(previous, current)
    assert current.file_count == previous.file_count + 1
    assert current.line_count == previous.line_count + 1


def test_workspace_metrics_detects_line_increase(workspace: Path) -> None:
    scanner = WorkspaceMetricsScanner(workspace)
    previous = scanner.scan()
    (workspace / "main.py").write_text("print('hello')\nline2\nline3\n", encoding="utf-8")
    current = scanner.scan()

    assert metrics_increased(previous, current)
    assert current.file_count == previous.file_count
    assert current.line_count > previous.line_count


def test_workspace_metrics_no_increase_on_decrease(workspace: Path) -> None:
    scanner = WorkspaceMetricsScanner(workspace)
    previous = scanner.scan()
    (workspace / "main.py").write_text("x\n", encoding="utf-8")
    current = scanner.scan()

    assert not metrics_increased(previous, current)


def test_metrics_increased_requires_strict_growth() -> None:
    previous = WorkspaceMetrics(file_count=3, line_count=10)
    same = WorkspaceMetrics(file_count=3, line_count=10)
    smaller = WorkspaceMetrics(file_count=2, line_count=8)

    assert not metrics_increased(previous, same)
    assert not metrics_increased(previous, smaller)
