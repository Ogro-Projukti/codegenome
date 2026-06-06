"""Tests for filesystem watch handlers respecting ignore rules."""

from __future__ import annotations

from pathlib import Path

from codegenome.core import CodeGenomeConfig, CodeGenomeEngine
from codegenome.gitignore import IgnoreMatcher


def test_default_ignore_patterns_cover_virtualenvs() -> None:
    matcher = IgnoreMatcher()
    assert matcher.is_ignored("env/Lib/site-packages/pkg/module.py")
    assert matcher.is_ignored("venv/lib/python3.11/site-packages/pkg/module.py")


def test_engine_should_process_path_skips_env_and_genome(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("env/\n", encoding="utf-8")

    engine = CodeGenomeEngine(CodeGenomeConfig(workspace=root))
    try:
        assert not engine.should_process_path("env/Lib/site-packages/foo.py")
        assert not engine.should_process_path(".genome/graph.json")
        assert not engine.should_process_path(".genome/exports/graph.html")
        assert engine.should_process_path("src/main.py")
    finally:
        engine.close()
