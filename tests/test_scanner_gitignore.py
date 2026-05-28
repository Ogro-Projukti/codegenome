
def test_ignore_matcher_for_workspace_loads_gitignore(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / ".genomeignore").write_text("local.txt\n", encoding="utf-8")

    from codegenome.scanner import IgnoreMatcher

    matcher = IgnoreMatcher.for_workspace(root)
    assert matcher.is_ignored("ignored.txt")
    assert matcher.is_ignored("local.txt")
    assert not matcher.is_ignored("main.py")
