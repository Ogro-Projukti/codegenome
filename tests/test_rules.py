"""Tests for non-destructive agent rule generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenome.rules import (
    MANAGED_SECTION_END,
    MANAGED_SECTION_START,
    RuleMergeError,
    backup_path_for,
    generate_rules,
    rule_targets,
)


def test_agents_rules_preserve_user_content_and_are_idempotent(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    user_content = "# Team instructions\n\nNever remove this guidance.\n"
    agents_path.write_text(user_content, encoding="utf-8")

    generate_rules(["agents"], workspace=tmp_path, port=7331)
    first_update = agents_path.read_text(encoding="utf-8")

    assert first_update.startswith(user_content.rstrip())
    assert first_update.count(MANAGED_SECTION_START) == 1
    assert first_update.count(MANAGED_SECTION_END) == 1
    assert backup_path_for(agents_path).read_text(encoding="utf-8") == user_content

    generate_rules(["agents"], workspace=tmp_path, port=7331)
    assert agents_path.read_text(encoding="utf-8") == first_update


def test_managed_rules_update_in_place_without_touching_user_content(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("Keep me.\n", encoding="utf-8")

    generate_rules(["agents"], workspace=tmp_path, port=7331)
    generate_rules(["agents"], workspace=tmp_path, port=9000)
    updated = agents_path.read_text(encoding="utf-8")

    assert updated.startswith("Keep me.\n")
    assert updated.count(MANAGED_SECTION_START) == 1
    assert updated.count(MANAGED_SECTION_END) == 1
    assert "127.0.0.1:9000" in updated
    assert "127.0.0.1:7331" not in updated


def test_malformed_managed_section_fails_without_mutating_file(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    malformed = f"User rules\n{MANAGED_SECTION_START}\nunfinished\n"
    agents_path.write_text(malformed, encoding="utf-8")

    with pytest.raises(RuleMergeError):
        generate_rules(["agents"], workspace=tmp_path)

    assert agents_path.read_text(encoding="utf-8") == malformed
    assert not backup_path_for(agents_path).exists()


def test_cursor_front_matter_remains_at_start_of_generated_file(tmp_path: Path) -> None:
    cursor_target = next(target for target in rule_targets(tmp_path) if target.key == "cursor")

    generate_rules(["cursor"], workspace=tmp_path)
    generated = cursor_target.output_path.read_text(encoding="utf-8")

    assert generated.startswith("---\n")
    assert generated.index(MANAGED_SECTION_START) > generated.index("\n---\n")


def test_rules_dry_run_does_not_create_files(tmp_path: Path) -> None:
    generate_rules(["all"], workspace=tmp_path, dry_run=True)

    assert all(not target.output_path.exists() for target in rule_targets(tmp_path))
