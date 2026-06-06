"""CodeGenome Textual TUI package.

Re-exports the public surface that previously lived in the single ``tui.py``
module so existing imports (``from codegenome.tui import CodeGenomeTUI`` etc.)
keep working after the decomposition into cohesive submodules.
"""

from __future__ import annotations

from codegenome.tui.constants import (
    LogChannel,
    PAGE_INFO,
    PAGE_MAIN,
    PAGE_MEMORY,
    PAGE_SET,
)
from codegenome.tui.memory import (
    MEMORY_PRESETS,
    MEMORY_SWITCH_LABELS,
    MemoryModeSettings,
    analyze_mode_cli_args,
    evolve_mode_cli_args,
    format_memory_mode_preview,
    mcp_mode_cli_args,
    parse_max_working_files,
    working_set_cli_args,
)
from codegenome.tui.process import ActiveProcess, SubprocessController
from codegenome.tui.widgets import ReadOnlyRichLog
from codegenome.tui.app import CodeGenomeTUI, main

__all__ = [
    "LogChannel",
    "PAGE_SET",
    "PAGE_INFO",
    "PAGE_MAIN",
    "PAGE_MEMORY",
    "MemoryModeSettings",
    "MEMORY_PRESETS",
    "MEMORY_SWITCH_LABELS",
    "working_set_cli_args",
    "analyze_mode_cli_args",
    "evolve_mode_cli_args",
    "mcp_mode_cli_args",
    "parse_max_working_files",
    "format_memory_mode_preview",
    "ActiveProcess",
    "SubprocessController",
    "ReadOnlyRichLog",
    "CodeGenomeTUI",
    "main",
]
