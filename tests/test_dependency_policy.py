"""Regression tests for the single-source dependency policy."""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_requirements_delegates_to_pyproject_under_constraints() -> None:
    active_lines = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert active_lines == ["-c constraints.txt", "-e .[dev]"]


def test_security_dependency_floors_and_pins_are_synchronized() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = set(project["dependencies"])
    dev = set(project["optional-dependencies"]["dev"])
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")

    assert "fastmcp>=3.2,<4" in declared
    assert "mcp>=1.28.1,<2" in declared
    assert "pytest>=9.0.3,<10" in dev
    assert "pytest-asyncio>=1.3,<2" in dev
    assert "fastmcp==3.4.4" in constraints
    assert "mcp==1.28.1" in constraints
    assert "pytest==9.0.3" in constraints
