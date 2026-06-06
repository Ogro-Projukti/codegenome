"""Workspace scan panel rendering helpers for the TUI."""

from __future__ import annotations

from typing import Any, Iterable

from codegenome.workspace_info import (
    WorkspaceInfo,
    format_gitignore_files_panel,
    format_tracked_extensions_panel,
    format_tracked_folders_panel,
)


def clear_workspace_scan_panels(panels: Iterable[Any], message: str = "") -> None:
    """Clear workspace scan panels and optionally write a placeholder."""
    for panel in panels:
        panel.clear()
        if message:
            panel.write(message)


def update_workspace_scan_panels(
    *,
    status_widget: Any,
    folders_log: Any,
    extensions_log: Any,
    gitignore_log: Any,
    info: WorkspaceInfo,
) -> None:
    """Populate workspace scan panels from workspace info."""
    status_widget.update(_workspace_scan_status(info))

    folders_log.clear()
    folders_log.write(format_tracked_folders_panel(info))

    extensions_log.clear()
    extensions_log.write(format_tracked_extensions_panel(info))

    gitignore_log.clear()
    gitignore_log.write(format_gitignore_files_panel(info))


def _workspace_scan_status(info: WorkspaceInfo) -> str:
    if info.error:
        return f"[bold]Root:[/bold] {info.root}  [bold red]Error:[/bold red] {info.error}"

    dir_count = len(info.tracked_directories)
    file_count = len(info.tracked_files)
    return (
        f"[bold]Root:[/bold] {info.root}  "
        f"[dim]|[/dim]  "
        f"{file_count} file{'s' if file_count != 1 else ''} in "
        f"{dir_count} director{'ies' if dir_count != 1 else 'y'}"
    )
