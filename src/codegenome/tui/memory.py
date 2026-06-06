"""Per-service memory-mode settings, presets, and CLI-flag helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryModeSettings:
    """Per-service memory-bounded options for CLI commands."""

    mcp_memory_bounded: bool = False
    evolve_memory_bounded: bool = False
    analyze_memory_bounded: bool = False
    max_working_files: int = 64
    mcp_full_analysis_on_demand: bool = False


def working_set_cli_args(*, memory_bounded: bool, max_working_files: int) -> list[str]:
    """Return CLI flags for engine commands that use a file working set."""
    if not memory_bounded:
        return []
    return [
        "--memory-bounded",
        "--max-working-files",
        str(max(1, max_working_files)),
    ]


def analyze_mode_cli_args(settings: MemoryModeSettings) -> list[str]:
    """Return Analyze-specific memory-bounded CLI flags."""
    return working_set_cli_args(
        memory_bounded=settings.analyze_memory_bounded,
        max_working_files=settings.max_working_files,
    )


def evolve_mode_cli_args(settings: MemoryModeSettings) -> list[str]:
    """Return Live Evolve / graph memory-bounded CLI flags."""
    return working_set_cli_args(
        memory_bounded=settings.evolve_memory_bounded,
        max_working_files=settings.max_working_files,
    )


def mcp_mode_cli_args(settings: MemoryModeSettings) -> list[str]:
    """Return MCP-specific CLI flags including optional full-analysis on demand."""
    args: list[str] = []
    if settings.mcp_memory_bounded:
        args.append("--memory-bounded")
    if settings.mcp_memory_bounded and settings.mcp_full_analysis_on_demand:
        args.append("--full-analysis-on-demand")
    return args


def parse_max_working_files(value: str, *, default: int = 64) -> int:
    """Parse and clamp the max working files input."""
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    return max(1, parsed)


MEMORY_SWITCH_LABELS: dict[str, str] = {
    "switch-mcp-memory-bounded": "MCP memory-bounded",
    "switch-evolve-memory-bounded": "Live Evolve memory-bounded",
    "switch-analyze-memory-bounded": "Analyze memory-bounded",
    "switch-mcp-full-analysis": "MCP full-graph analysis on demand",
}

MEMORY_PRESETS: dict[str, MemoryModeSettings] = {
    "default": MemoryModeSettings(),
    "all_bounded": MemoryModeSettings(
        mcp_memory_bounded=True,
        evolve_memory_bounded=True,
        analyze_memory_bounded=True,
        max_working_files=64,
    ),
    "full_mcp_bounded_evolve": MemoryModeSettings(
        evolve_memory_bounded=True,
        max_working_files=64,
    ),
    "bounded_mcp_full_analysis": MemoryModeSettings(
        mcp_memory_bounded=True,
        mcp_full_analysis_on_demand=True,
        max_working_files=64,
    ),
}


def format_memory_mode_preview(settings: MemoryModeSettings) -> str:
    """Render a human-readable summary of the active memory settings."""
    analyze_flags = " ".join(analyze_mode_cli_args(settings)) or "(full graph)"
    evolve_flags = " ".join(evolve_mode_cli_args(settings)) or "(full graph)"
    mcp_flags = " ".join(mcp_mode_cli_args(settings)) or "(full graph)"

    lines = [
        f"[cyan]Analyze[/cyan]  →  {analyze_flags}",
        f"[cyan]MCP[/cyan]  →  {mcp_flags}",
        f"[cyan]Live Evolve[/cyan]  →  {evolve_flags}",
    ]
    if settings.analyze_memory_bounded or settings.evolve_memory_bounded:
        lines.append("")
        lines.append(
            f"[dim]Working set limit:[/dim] {settings.max_working_files} file(s) "
            "(Analyze / Evolve only)"
        )
    if settings.mcp_memory_bounded and settings.mcp_full_analysis_on_demand:
        lines.append("[dim]MCP can load the full graph temporarily for global tools.[/dim]")
    return "\n".join(lines)
