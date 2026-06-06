"""In-process service facade over :class:`CodeGenomeEngine`.

This module provides :class:`CodeGenomeService`, a thin library API that the CLI
and TUI call directly instead of shelling out to ``codegenome ...`` subprocesses
for in-process-safe operations (analyze, export, rules). Long-lived servers
(the MCP server and the live-evolve server) intentionally remain separate
processes; everything else now flows through this single, testable surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from codegenome.core import BuildResult, CodeGenomeConfig, CodeGenomeEngine, ProgressCallback


class CodeGenomeServiceError(RuntimeError):
    """Raised for expected, user-facing service failures."""


class CodeGenomeService:
    """Facade exposing engine operations as a clean, reusable library API."""

    def analyze(
        self,
        workspace: str | Path,
        *,
        memory_bounded: bool = False,
        max_working_files: int = 64,
        full: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> BuildResult:
        """Scan, build, and persist the graph for ``workspace``."""
        config = CodeGenomeConfig(
            workspace=Path(workspace).resolve(),
            export_formats=("json",),
            memory_bounded=memory_bounded,
            max_working_files=max(1, max_working_files),
        )
        engine = CodeGenomeEngine(config)
        try:
            return engine.build(full=full, on_progress=on_progress)
        finally:
            engine.close()

    def export(
        self,
        workspace: str | Path,
        formats: Iterable[str],
        *,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Path]:
        """Export the previously built graph for ``workspace``.

        Raises:
            CodeGenomeServiceError: If no graph has been analyzed yet.
        """
        selected = [fmt.lower() for fmt in formats]
        config = CodeGenomeConfig(workspace=Path(workspace).resolve())
        engine = CodeGenomeEngine(config)
        try:
            if engine.builder.graph.number_of_nodes() == 0:
                raise CodeGenomeServiceError(
                    "No graph found. Run 'analyze' first before exporting."
                )
            if on_progress is not None:
                on_progress(f"Exporting to {', '.join(selected)}...")
            return engine.export(formats=selected)
        finally:
            engine.close()

    def generate_rules(
        self,
        workspace: str | Path,
        *,
        clients: Sequence[str] | None = None,
        port: int = 7331,
        dry_run: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> list[tuple[str, Path]]:
        """Generate agent rule files pointing at the MCP server."""
        from codegenome.rules import generate_rules

        resolved = Path(workspace).resolve()
        selected = list(clients) if clients else ["all"]
        if on_progress is not None:
            on_progress(f"Generating rules (MCP port: {port})...")
        return generate_rules(
            selected_clients=selected,
            port=port,
            workspace=resolved,
            dry_run=dry_run,
        )
