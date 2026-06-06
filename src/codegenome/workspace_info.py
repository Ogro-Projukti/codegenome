"""Collect workspace ignore rules and tracked paths for UI display."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from codegenome.gitignore import DEFAULT_IGNORE_PATTERNS, IGNORE_FILENAMES, IgnoreMatcher


@dataclass(frozen=True)
class IgnoreFileInfo:
    """An ignore file discovered under the workspace root."""

    relative_path: str
    filename: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceInfo:
    """Snapshot of ignore configuration and tracked paths for one workspace."""

    root: str
    exists: bool
    is_directory: bool
    error: str | None = None
    default_patterns: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_IGNORE_PATTERNS))
    ignore_files: tuple[IgnoreFileInfo, ...] = ()
    tracked_directories: tuple[str, ...] = ()
    tracked_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphLiveSummary:
    """Latest graph snapshot metadata for dashboard display."""

    available: bool
    snapshot_id: int | None = None
    label: str | None = None
    node_count: int = 0
    edge_count: int = 0
    updated_at: float | None = None


def collect_workspace_info(root: Path | str) -> WorkspaceInfo:
    """Walk a workspace and collect ignore files plus tracked paths."""
    resolved = Path(root).expanduser()
    try:
        resolved = resolved.resolve()
    except OSError as exc:
        return WorkspaceInfo(
            root=str(root),
            exists=False,
            is_directory=False,
            error=str(exc),
        )

    if not resolved.exists():
        return WorkspaceInfo(
            root=str(resolved),
            exists=False,
            is_directory=False,
            error="Path does not exist",
        )

    if not resolved.is_dir():
        return WorkspaceInfo(
            root=str(resolved),
            exists=True,
            is_directory=False,
            error="Path is not a directory",
        )

    ignore = IgnoreMatcher.for_workspace(resolved)
    ignore_files = _discover_ignore_files(resolved, ignore)
    tracked_directories, tracked_files = _collect_tracked_paths(resolved, ignore)

    return WorkspaceInfo(
        root=str(resolved),
        exists=True,
        is_directory=True,
        ignore_files=tuple(ignore_files),
        tracked_directories=tuple(tracked_directories),
        tracked_files=tuple(tracked_files),
    )


def _discover_ignore_files(root: Path, ignore: IgnoreMatcher) -> list[IgnoreFileInfo]:
    """Collect ignore files from directories visited by the same walk as scanning."""
    found: list[IgnoreFileInfo] = []

    for dirpath, dirnames, _ in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""

        dirnames[:] = [
            name
            for name in dirnames
            if not ignore.is_ignored(f"{rel_dir}/{name}".strip("/"), is_dir=True)
        ]

        for filename in IGNORE_FILENAMES:
            ignore_path = current / filename
            if not ignore_path.is_file():
                continue
            patterns = _read_ignore_patterns(ignore_path)
            found.append(
                IgnoreFileInfo(
                    relative_path=ignore_path.relative_to(root).as_posix(),
                    filename=filename,
                    patterns=tuple(patterns),
                )
            )

    return sorted(found, key=lambda item: item.relative_path)


def _collect_tracked_paths(
    root: Path,
    ignore: IgnoreMatcher,
) -> tuple[list[str], list[str]]:
    """Return tracked directory and file paths relative to the workspace root."""
    tracked_directories: list[str] = []
    tracked_files: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""

        dirnames[:] = [
            name
            for name in dirnames
            if not ignore.is_ignored(f"{rel_dir}/{name}".strip("/"), is_dir=True)
        ]

        if rel_dir not in tracked_directories:
            tracked_directories.append(rel_dir)

        for filename in sorted(filenames):
            rel_path = f"{rel_dir}/{filename}".strip("/") if rel_dir else filename
            if ignore.is_ignored(rel_path):
                continue
            tracked_files.append(rel_path)

    return tracked_directories, tracked_files


def _read_ignore_patterns(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return patterns


def format_workspace_info(info: WorkspaceInfo) -> str:
    """Render workspace info as Rich markup for the TUI."""
    lines: list[str] = []

    lines.append(f"[bold]Resolved root:[/bold] {info.root}")

    if info.error:
        lines.append(f"[bold red]Status:[/bold red] {info.error}")
        return "\n".join(lines)

    dir_count = len(info.tracked_directories)
    file_count = len(info.tracked_files)
    lines.append(
        f"[bold green]Status:[/bold green] tracking "
        f"{file_count} file{'s' if file_count != 1 else ''} in "
        f"{dir_count} director{'ies' if dir_count != 1 else 'y'}"
    )

    lines.append("")
    lines.append("[bold cyan]Built-in ignore patterns[/bold cyan]")
    for pattern in info.default_patterns:
        lines.append(f"  [dim]•[/dim] {pattern}")

    lines.append("")
    lines.append("[bold cyan]Ignore files in use[/bold cyan]")
    if not info.ignore_files:
        lines.append("  [dim](none — only built-in patterns apply)[/dim]")
    else:
        for ignore_file in info.ignore_files:
            pattern_count = len(ignore_file.patterns)
            lines.append(
                f"  [bold]{ignore_file.relative_path}[/bold] "
                f"[dim]({ignore_file.filename}, {pattern_count} pattern"
                f"{'s' if pattern_count != 1 else ''})[/dim]"
            )
            for pattern in ignore_file.patterns:
                lines.append(f"    [dim]•[/dim] {pattern}")

    lines.append("")
    lines.append("[bold cyan]Tracked directories[/bold cyan]")
    if not info.tracked_directories:
        lines.append("  [dim](none)[/dim]")
    else:
        for directory in info.tracked_directories:
            label = "." if directory == "" else directory
            lines.append(f"  [dim]•[/dim] {label}/")

    lines.append("")
    lines.append("[bold cyan]Tracked files[/bold cyan]")
    if not info.tracked_files:
        lines.append("  [dim](none)[/dim]")
    else:
        for rel_path in info.tracked_files:
            lines.append(f"  [dim]•[/dim] {rel_path}")

    return "\n".join(lines)


def load_graph_live_summary(root: Path | str) -> GraphLiveSummary:
    """Read the latest graph snapshot stats from `.genome/codegenome.db`."""
    workspace = Path(root).expanduser()
    db_path = workspace / ".genome" / "codegenome.db"
    if not db_path.is_file():
        return GraphLiveSummary(available=False)

    try:
        from codegenome.timeline import GraphTimeline

        timeline = GraphTimeline(db_path)
        try:
            snapshots = timeline.list_snapshots()
        finally:
            timeline.close()
    except OSError:
        return GraphLiveSummary(available=False)

    if not snapshots:
        return GraphLiveSummary(available=False)

    latest = snapshots[-1]
    return GraphLiveSummary(
        available=True,
        snapshot_id=latest.snapshot_id,
        label=latest.label,
        node_count=latest.node_count,
        edge_count=latest.edge_count,
        updated_at=latest.created_at,
    )


def format_graph_live_summary(summary: GraphLiveSummary) -> str:
    """Render live graph snapshot status for the dashboard header."""
    if not summary.available:
        return "[bold magenta]Graph:[/bold magenta] [dim]not analyzed yet[/dim]"

    label = f" · {summary.label}" if summary.label else ""
    updated = ""
    if summary.updated_at is not None:
        updated = f" · updated {datetime.fromtimestamp(summary.updated_at).strftime('%H:%M:%S')}"
    return (
        f"[bold magenta]Graph:[/bold magenta] "
        f"[cyan]{summary.node_count:,}[/cyan] nodes · "
        f"[cyan]{summary.edge_count:,}[/cyan] edges · "
        f"snapshot #{summary.snapshot_id}{label}{updated}"
    )


def format_workspace_summary(info: WorkspaceInfo) -> str:
    """Render a compact one-line workspace summary for the main dashboard."""
    if info.error:
        return f"[bold red]{info.root}[/bold red] — {info.error}"

    dir_count = len(info.tracked_directories)
    file_count = len(info.tracked_files)
    return (
        f"[bold]Workspace:[/bold] {info.root}  "
        f"[dim]|[/dim]  "
        f"[bold cyan]Tracking:[/bold cyan] {file_count} file{'s' if file_count != 1 else ''} in "
        f"{dir_count} director{'ies' if dir_count != 1 else 'y'}"
    )


def format_dashboard_summary(
    info: WorkspaceInfo,
    graph: GraphLiveSummary | None = None,
) -> str:
    """Render workspace tracking plus live graph snapshot status."""
    workspace_line = format_workspace_summary(info)
    if info.error:
        return workspace_line
    graph_line = format_graph_live_summary(graph or GraphLiveSummary(available=False))
    return f"{workspace_line}  [dim]|[/dim]  {graph_line}"


def _folder_label(directory: str) -> str:
    return "(root)" if directory == "" else directory


def _tracked_extension_counts(info: WorkspaceInfo) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for rel_path in info.tracked_files:
        suffix = Path(rel_path).suffix.lower()
        label = suffix if suffix else "(no extension)"
        counts[label] = counts.get(label, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def format_tracked_folders_panel(info: WorkspaceInfo) -> str:
    """Render tracked folder names for the scan results panel."""
    if info.error:
        return f"[bold red]{info.error}[/bold red]"

    if not info.tracked_directories:
        return "[dim](none)[/dim]"

    lines: list[str] = []
    for directory in info.tracked_directories:
        label = _folder_label(directory)
        lines.append(f"[dim]•[/dim] {label}/")
    return "\n".join(lines)


def format_tracked_extensions_panel(info: WorkspaceInfo) -> str:
    """Render tracked file extensions for the scan results panel."""
    if info.error:
        return "[dim]—[/dim]"

    extensions = _tracked_extension_counts(info)
    if not extensions:
        return "[dim](none)[/dim]"

    lines: list[str] = []
    for extension, count in extensions:
        lines.append(
            f"[dim]•[/dim] {extension}  "
            f"[dim]({count} file{'s' if count != 1 else ''})[/dim]"
        )
    return "\n".join(lines)


def format_gitignore_files_panel(info: WorkspaceInfo) -> str:
    """Render discovered .gitignore files for the scan results panel."""
    if info.error:
        return "[dim]—[/dim]"

    gitignore_files = tuple(
        ignore_file for ignore_file in info.ignore_files if ignore_file.filename == ".gitignore"
    )
    if not gitignore_files:
        return "[dim](none found)[/dim]"

    lines: list[str] = []
    for ignore_file in gitignore_files:
        pattern_count = len(ignore_file.patterns)
        lines.append(f"[bold]{ignore_file.relative_path}[/bold]")
        lines.append(
            f"  [dim]{pattern_count} pattern{'s' if pattern_count != 1 else ''}[/dim]"
        )
        for pattern in ignore_file.patterns:
            lines.append(f"    [dim]•[/dim] {pattern}")
        lines.append("")
    return "\n".join(lines).rstrip()
