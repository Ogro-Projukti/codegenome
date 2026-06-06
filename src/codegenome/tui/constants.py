"""Shared constants and type aliases for the TUI package."""

from __future__ import annotations

from typing import Literal

LogChannel = Literal["analyze", "mcp", "evolve", "general"]

PAGE_SET = "page-set-workspace"
PAGE_INFO = "page-workspace-info"
PAGE_MAIN = "page-main"
PAGE_MEMORY = "page-memory-setup"
