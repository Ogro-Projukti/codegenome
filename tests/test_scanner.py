"""Tests for workspace scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.scanner import IgnoreMatcher, ScanCache, WorkspaceScanner, sha256_file


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "utils.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (root / "ignored.txt").write_text("skip me", encoding="utf-8")
    (root / ".genomeignore").write_text("ignored.txt\n*.log\n", encoding="utf-8")
    return root


def test_scanner_finds_files_and_respects_watcherignore(workspace: Path) -> None:
    scanner = WorkspaceScanner(workspace, cache_db=workspace / ".genome" / "cache.db")
    result = scanner.scan(incremental=False)

    paths = {record.path for record in result.files}
    assert "main.py" in paths
    assert "utils.py" in paths
    assert "ignored.txt" not in paths
    assert len(result.added) == len(result.files)
    scanner.cache.close()


def test_scanner_sha256_and_cache(workspace: Path) -> None:
    main_path = workspace / "main.py"
    expected = sha256_file(main_path)

    scanner = WorkspaceScanner(workspace, cache_db=workspace / ".genome" / "cache.db")
    first = scanner.scan(incremental=False)
    main_record = next(record for record in first.files if record.path == "main.py")
    assert main_record.sha256 == expected

    second = scanner.scan(incremental=True)
    assert set(second.unchanged) == {"main.py", "utils.py"}
    assert second.added == []
    assert second.modified == []
    scanner.cache.close()


def test_scanner_incremental_detects_changes(workspace: Path) -> None:
    cache_db = workspace / ".genome" / "cache.db"
    scanner = WorkspaceScanner(workspace, cache_db=cache_db)
    scanner.scan(incremental=False)

    (workspace / "main.py").write_text("print('changed')\n", encoding="utf-8")
    (workspace / "new.py").write_text("x = 1\n", encoding="utf-8")

    result = scanner.scan(incremental=True)
    assert "main.py" in result.modified
    assert "new.py" in result.added
    scanner.cache.close()


def test_scanner_empty_repository_does_not_crash(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    scanner = WorkspaceScanner(empty, cache_db=empty / "cache.db")
    result = scanner.scan()
    assert result.files == []
    assert result.added == []
    scanner.cache.close()


def test_ignore_matcher_default_patterns() -> None:
    matcher = IgnoreMatcher()
    assert matcher.is_ignored("node_modules/pkg/index.js")
    assert matcher.is_ignored(".git/config")
    assert matcher.is_ignored("env/Lib/site-packages/pkg/module.py")
    assert matcher.is_ignored("venv/lib/python3.11/site-packages/pkg/module.py")
    assert not matcher.is_ignored("src/main.py")


def test_scan_cache_roundtrip(tmp_path: Path) -> None:
    from codegenome.scanner import FileRecord

    cache = ScanCache(tmp_path / "cache.db")
    record = FileRecord(
        path="a.py",
        absolute_path=str(tmp_path / "a.py"),
        sha256="abc",
        size=3,
        mtime=1.0,
    )
    cache.upsert(record)
    cache.commit()
    loaded = cache.load_all()
    assert loaded["a.py"].sha256 == "abc"
    cache.close()
