"""Tests for full gitignore semantics and nested ignore files."""

from __future__ import annotations

from pathlib import Path

from codegenome.gitignore import IgnoreMatcher
from codegenome.scanner import WorkspaceScanner


def test_nested_gitignore_in_subdirectory(tmp_path: Path) -> None:
    root = tmp_path / "project"
    pkg = root / "packages" / "app"
    pkg.mkdir(parents=True)
    (root / "main.py").write_text("x\n", encoding="utf-8")
    (pkg / "main.py").write_text("y\n", encoding="utf-8")
    (pkg / "dist.py").write_text("z\n", encoding="utf-8")
    (pkg / ".gitignore").write_text("dist.py\n", encoding="utf-8")

    matcher = IgnoreMatcher.for_workspace(root)
    assert not matcher.is_ignored("main.py")
    assert not matcher.is_ignored("packages/app/main.py")
    assert matcher.is_ignored("packages/app/dist.py")


def test_nested_gitignore_directory_pattern(tmp_path: Path) -> None:
    root = tmp_path / "project"
    lib = root / "packages" / "lib"
    dist = lib / "dist"
    dist.mkdir(parents=True)
    (dist / "bundle.js").write_text("js\n", encoding="utf-8")
    (lib / "index.js").write_text("js\n", encoding="utf-8")
    (lib / ".gitignore").write_text("dist/\n", encoding="utf-8")

    matcher = IgnoreMatcher.for_workspace(root)
    assert not matcher.is_ignored("packages/lib/index.js")
    assert matcher.is_ignored("packages/lib/dist/bundle.js")
    assert matcher.is_ignored("packages/lib/dist", is_dir=True)


def test_gitignore_negation(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".gitignore").write_text("*.log\n!important.log\n", encoding="utf-8")

    matcher = IgnoreMatcher.for_workspace(root)
    assert matcher.is_ignored("debug.log")
    assert not matcher.is_ignored("important.log")
    assert matcher.is_ignored("nested/debug.log")
    assert not matcher.is_ignored("nested/important.log")


def test_nested_gitignore_negation_overrides_parent(tmp_path: Path) -> None:
    root = tmp_path / "project"
    pkg = root / "packages" / "app"
    pkg.mkdir(parents=True)
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (pkg / ".gitignore").write_text("!keep.log\n", encoding="utf-8")

    matcher = IgnoreMatcher.for_workspace(root)
    assert matcher.is_ignored("other.log")
    assert matcher.is_ignored("packages/app/other.log")
    assert not matcher.is_ignored("packages/app/keep.log")


def test_anchored_pattern_only_matches_in_ignore_directory(tmp_path: Path) -> None:
    root = tmp_path / "project"
    pkg = root / "packages" / "app"
    nested = root / "packages" / "other"
    pkg.mkdir(parents=True)
    nested.mkdir()
    (pkg / "target").write_text("x\n", encoding="utf-8")
    (nested / "target").write_text("y\n", encoding="utf-8")
    (pkg / ".gitignore").write_text("/target\n", encoding="utf-8")

    matcher = IgnoreMatcher.for_workspace(root)
    assert matcher.is_ignored("packages/app/target")
    assert not matcher.is_ignored("packages/other/target")


def test_scanner_skips_nested_gitignored_files(tmp_path: Path) -> None:
    root = tmp_path / "project"
    pkg = root / "packages" / "app"
    pkg.mkdir(parents=True)
    (root / "main.py").write_text("x\n", encoding="utf-8")
    (pkg / "keep.py").write_text("y\n", encoding="utf-8")
    (pkg / "skip.py").write_text("z\n", encoding="utf-8")
    (pkg / ".gitignore").write_text("skip.py\n", encoding="utf-8")

    scanner = WorkspaceScanner(root, cache_db=root / ".genome" / "cache.db")
    result = scanner.scan(incremental=False)
    paths = {record.path for record in result.files}

    assert "main.py" in paths
    assert "packages/app/keep.py" in paths
    assert "packages/app/skip.py" not in paths
    scanner.cache.close()
