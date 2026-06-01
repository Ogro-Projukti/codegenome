from pathlib import Path

from codegenome.scanner import IgnoreMatcher, WorkspaceScanner


def test_ignore_matcher_for_workspace_loads_gitignore(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / ".genomeignore").write_text("local.txt\n", encoding="utf-8")

    matcher = IgnoreMatcher.for_workspace(root)
    assert matcher.is_ignored("ignored.txt")
    assert matcher.is_ignored("local.txt")
    assert not matcher.is_ignored("main.py")


def test_scanner_respects_gitignore(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "ignored.txt").write_text("skip me\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.txt\nbuild/\n", encoding="utf-8")
    build_dir = root / "build"
    build_dir.mkdir()
    (build_dir / "artifact.txt").write_text("ignored by gitignore\n", encoding="utf-8")

    scanner = WorkspaceScanner(root, cache_db=root / ".genome" / "cache.db")
    result = scanner.scan(incremental=False)

    paths = {record.path for record in result.files}
    assert "main.py" in paths
    assert "ignored.txt" not in paths
    assert "build/artifact.txt" not in paths
    scanner.cache.close()
