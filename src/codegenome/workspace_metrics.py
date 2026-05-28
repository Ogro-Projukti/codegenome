"""Workspace file and line counters respecting ignore rules."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from codegenome.scanner import IgnoreMatcher


@dataclass(frozen=True)
class WorkspaceMetrics:
    """Aggregate workspace size used to detect growth."""

    file_count: int
    line_count: int


class WorkspaceMetricsScanner:
    """Count tracked files and total lines under a workspace root."""

    def __init__(self, root: Path | str) -> None:
        """Initialize the scanner with a workspace root.

        Args:
            root (Path | str): The root directory of the workspace.
        """
        self.root = Path(root).resolve()
        self.ignore = IgnoreMatcher.for_workspace(self.root)

    def scan(self) -> WorkspaceMetrics:
        """Scan the workspace to compute current metrics.

        Returns:
            WorkspaceMetrics: The computed metrics containing file and line counts.
        """
        if not self.root.is_dir():
            return WorkspaceMetrics(file_count=0, line_count=0)

        file_count = 0
        line_count = 0

        for dirpath, dirnames, filenames in os.walk(self.root):
            current = Path(dirpath)
            rel_dir = current.relative_to(self.root).as_posix()
            if rel_dir == ".":
                rel_dir = ""

            dirnames[:] = [
                name
                for name in dirnames
                if not self.ignore.is_ignored(
                    f"{rel_dir}/{name}".strip("/"),
                    is_dir=True,
                )
            ]

            for filename in filenames:
                rel_path = f"{rel_dir}/{filename}".strip("/") if rel_dir else filename
                if self.ignore.is_ignored(rel_path):
                    continue

                abs_path = current / filename
                try:
                    line_count += _count_lines(abs_path)
                except OSError:
                    continue

                file_count += 1

        return WorkspaceMetrics(file_count=file_count, line_count=line_count)


def metrics_increased(previous: WorkspaceMetrics, current: WorkspaceMetrics) -> bool:
    """Return True when the workspace grew since the previous sample.

    Args:
        previous (WorkspaceMetrics): The previous metrics sample.
        current (WorkspaceMetrics): The current metrics sample.

    Returns:
        bool: True if either file count or line count increased, False otherwise.
    """
    return (
        current.file_count > previous.file_count
        or current.line_count > previous.line_count
    )


def _count_lines(path: Path) -> int:
    """Count the total number of lines in a given file.

    Args:
        path (Path): The path to the file to count lines for.

    Returns:
        int: The number of lines in the file.
    """
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)
