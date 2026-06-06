"""Tests for workspace info collection and formatting."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.builder import GraphBuilder
from codegenome.parser import SourceParser
from codegenome.scanner import WorkspaceScanner
from codegenome.timeline import GraphTimeline
from codegenome.workspace_info import (
    collect_workspace_info,
    format_dashboard_summary,
    format_gitignore_files_panel,
    format_graph_live_summary,
    format_tracked_extensions_panel,
    format_tracked_folders_panel,
    format_workspace_info,
    load_graph_live_summary,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "ignored.txt").write_text("skip me\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.txt\nbuild/\n", encoding="utf-8")
    build_dir = root / "build"
    build_dir.mkdir()
    (build_dir / "artifact.txt").write_text("ignored\n", encoding="utf-8")
    pkg_dir = root / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "module.py").write_text("x = 1\n", encoding="utf-8")
    (pkg_dir / ".genomeignore").write_text("module.py\n", encoding="utf-8")
    return root


def test_collect_workspace_info_lists_ignore_files_and_tracked_paths(workspace: Path) -> None:
    info = collect_workspace_info(workspace)

    assert info.exists
    assert info.is_directory
    assert info.error is None
    assert len(info.ignore_files) == 2
    assert info.ignore_files[0].relative_path == ".gitignore"
    assert info.ignore_files[0].patterns == ("ignored.txt", "build/")
    assert any(item.relative_path == "pkg/.genomeignore" for item in info.ignore_files)
    assert "main.py" in info.tracked_files
    assert "pkg/module.py" not in info.tracked_files
    assert "ignored.txt" not in info.tracked_files
    assert "" in info.tracked_directories
    assert "pkg" in info.tracked_directories
    assert "build" not in info.tracked_directories


def test_collect_workspace_info_invalid_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    info = collect_workspace_info(missing)

    assert not info.exists
    assert info.error == "Path does not exist"


def test_format_workspace_info_includes_sections(workspace: Path) -> None:
    info = collect_workspace_info(workspace)
    rendered = format_workspace_info(info)

    assert "Built-in ignore patterns" in rendered
    assert "Ignore files in use" in rendered
    assert ".gitignore" in rendered
    assert "Tracked directories" in rendered
    assert "Tracked files" in rendered
    assert "main.py" in rendered


def test_scan_result_panels_show_folders_extensions_and_gitignore(workspace: Path) -> None:
    info = collect_workspace_info(workspace)

    folders = format_tracked_folders_panel(info)
    extensions = format_tracked_extensions_panel(info)
    gitignore = format_gitignore_files_panel(info)

    assert "(root)/" in folders
    assert "pkg/" in folders
    assert "build/" not in folders
    assert ".py" in extensions
    assert "main.py" not in extensions
    assert ".gitignore" in gitignore
    assert "ignored.txt" in gitignore
    assert ".genomeignore" not in gitignore


def test_load_graph_live_summary_without_database(workspace: Path) -> None:
    summary = load_graph_live_summary(workspace)
    assert summary.available is False
    assert "not analyzed" in format_graph_live_summary(summary)


def test_format_dashboard_summary_includes_graph_stats(workspace: Path) -> None:
    scanner = WorkspaceScanner(workspace, cache_db=workspace / ".genome" / "cache.db")
    scan = scanner.scan(incremental=False)
    scanner.cache.close()

    parser = SourceParser()
    parses = {}
    for record in scan.files:
        parsed = parser.parse_file(record.absolute_path)
        if parsed:
            parses[record.path] = parsed

    graph, _, _ = GraphBuilder().build(scan, parses)
    timeline = GraphTimeline(workspace / ".genome" / "codegenome.db")
    timeline.record_snapshot(graph, label="baseline")
    timeline.close()

    info = collect_workspace_info(workspace)
    summary = load_graph_live_summary(workspace)
    rendered = format_dashboard_summary(info, summary)

    assert "Tracking:" in rendered
    assert "Graph:" in rendered
    assert f"{graph.number_of_nodes():,}" in rendered or str(graph.number_of_nodes()) in rendered
    assert summary.available is True
