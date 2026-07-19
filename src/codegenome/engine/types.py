"""Shared dataclasses and type aliases for the engine service layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import networkx as nx

from codegenome.intelligence import IntelligenceReport

DEFAULT_EXPORT_FORMATS = ("json", "html", "markdown")

ProgressCallback = Callable[[str], None]
PARSE_PROGRESS_INTERVAL = 50


@dataclass
class CodeGenomeConfig:
    """Configuration for CodeGenomeEngine."""

    workspace: Path
    db_path: Path | None = None
    export_dir: Path | None = None
    graph_json_path: Path | None = None
    export_formats: tuple[str, ...] = DEFAULT_EXPORT_FORMATS
    start_mcp: bool = False
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 7331
    watch_debounce_seconds: float = 30.0
    live_graph: bool = False
    live_graph_poll_seconds: float = 30.0
    memory_bounded: bool = False
    max_working_files: int = 64
    snapshot_retention_count: int | None = 100
    snapshot_retention_days: float | None = None

    def __post_init__(self) -> None:
        if self.snapshot_retention_count is not None and self.snapshot_retention_count < 1:
            raise ValueError("snapshot_retention_count must be at least 1")
        if self.snapshot_retention_days is not None and self.snapshot_retention_days < 0:
            raise ValueError("snapshot_retention_days must be non-negative")


@dataclass
class BuildResult:
    """Container for the output of a CodeGenomeEngine build or update."""

    graph: nx.DiGraph
    report: IntelligenceReport
    snapshot_id: int | None
    export_paths: dict[str, Path] = field(default_factory=dict)


def make_emitter(on_progress: ProgressCallback | None) -> ProgressCallback:
    """Return a safe progress emitter that is a no-op when no callback is given."""

    def emit(message: str) -> None:
        if on_progress is not None:
            on_progress(message)

    return emit
