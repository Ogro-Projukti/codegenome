"""CodeGenomeEngine coordinator wiring the engine service layer.

The heavy lifting now lives in :mod:`codegenome.engine`. ``CodeGenomeEngine``
is a thin facade that composes the focused services and preserves the original
public API (attributes and methods) for the CLI, TUI, watchers, and tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from codegenome.builder import GraphBuilder
from codegenome.clusterer import GraphClusterer
from codegenome.parser import SourceParser
from codegenome.registry import GlobalDependencyRegistry
from codegenome.scanner import WorkspaceScanner
from codegenome.timeline import GraphTimeline
from codegenome.working_set import WorkingSetGraph
from codegenome.intelligence import IntelligenceReport
from codegenome.live_graph_monitor import LiveGraphMonitor

from codegenome.engine import (
    BuildResult,
    BuildService,
    CodeGenomeConfig,
    DEFAULT_EXPORT_FORMATS,
    EngineContext,
    ExportService,
    McpProcessManager,
    PARSE_PROGRESS_INTERVAL,
    PersistenceService,
    ProgressCallback,
    ScanService,
    SurgicalUpdateHandler,
    WatchService,
)

__all__ = [
    "BuildResult",
    "CodeGenomeConfig",
    "CodeGenomeEngine",
    "SurgicalUpdateHandler",
    "DEFAULT_EXPORT_FORMATS",
    "PARSE_PROGRESS_INTERVAL",
    "ProgressCallback",
]


class CodeGenomeEngine:
    """Coordinate scanning, graph building, exports, watching, and MCP startup."""

    def __init__(self, config: CodeGenomeConfig) -> None:
        """Initialize the CodeGenomeEngine.

        Args:
            config (CodeGenomeConfig): The configuration defining paths and options.
        """
        self.ctx = EngineContext.create(config)
        self._scan_service = ScanService(self.ctx)
        self._persistence = PersistenceService(self.ctx)
        self._export_service = ExportService(self.ctx)
        self._build_service = BuildService(
            self.ctx,
            self._scan_service,
            self._persistence,
            self._export_service,
        )
        self._watch_service = WatchService(self)
        self._mcp_manager = McpProcessManager(self.ctx)
        self._live_graph_monitor: LiveGraphMonitor | None = None

        self.ctx.loaded_existing_graph = self._persistence.load_existing_graph()

    # -- Backward-compatible attribute access -----------------------------

    @property
    def config(self) -> CodeGenomeConfig:
        return self.ctx.config

    @property
    def workspace(self) -> Path:
        return self.ctx.workspace

    @property
    def genome_dir(self) -> Path:
        return self.ctx.genome_dir

    @property
    def db_path(self) -> Path:
        return self.ctx.db_path

    @property
    def export_dir(self) -> Path:
        return self.ctx.export_dir

    @property
    def graph_json_path(self) -> Path:
        return self.ctx.graph_json_path

    @property
    def scanner(self) -> WorkspaceScanner:
        return self.ctx.scanner

    @property
    def parser(self) -> SourceParser:
        return self.ctx.parser

    @property
    def builder(self) -> GraphBuilder:
        return self.ctx.builder

    @property
    def clusterer(self) -> GraphClusterer:
        return self.ctx.clusterer

    @property
    def timeline(self) -> GraphTimeline:
        return self.ctx.timeline

    @property
    def registry(self) -> GlobalDependencyRegistry:
        return self.ctx.registry

    @property
    def _working_set(self) -> WorkingSetGraph | None:
        return self.ctx.working_set

    @property
    def _active_snapshot_id(self) -> int | None:
        return self.ctx.active_snapshot_id

    @property
    def _loaded_existing_graph(self) -> bool:
        return self.ctx.loaded_existing_graph

    # -- Build / update ----------------------------------------------------

    def should_process_path(self, rel_path: str) -> bool:
        """Return False for runtime artifacts and gitignored paths."""
        return self.ctx.should_process_path(rel_path)

    def build(
        self,
        *,
        full: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> BuildResult:
        """Build or rebuild the graph from source files."""
        return self._build_service.build(full=full, on_progress=on_progress)

    def rebuild_incremental(self) -> BuildResult:
        """Perform an incremental rebuild of the graph."""
        return self._build_service.build(full=False)

    def surgical_update(
        self,
        abs_path: str,
        rel_path: str,
        event_type: str,
    ) -> BuildResult | None:
        """Perform a surgical update on the graph for a single file change."""
        return self._build_service.surgical_update(abs_path, rel_path, event_type)

    def export(
        self,
        formats: Iterable[str] | None = None,
        *,
        report: IntelligenceReport | None = None,
    ) -> dict[str, Path]:
        """Export the graph to various formats."""
        return self._export_service.export(formats, report=report)

    # -- Watching ----------------------------------------------------------

    def watch(self) -> None:
        """Start watching the workspace for file changes to trigger rebuilds."""
        self._watch_service.watch()

    def stop_watch(self) -> None:
        """Stop watching the workspace for file changes."""
        self._watch_service.stop()

    # -- Live graph monitor ------------------------------------------------

    def monitor_live_graph(self) -> None:
        """Start the live graph monitor in a background thread."""
        self._live_graph_monitor = LiveGraphMonitor(
            self,
            poll_interval_seconds=self.config.live_graph_poll_seconds,
        )
        self._live_graph_monitor.run_forever()

    def stop_live_graph_monitor(self) -> None:
        """Stop the live graph monitor if it is running."""
        if self._live_graph_monitor is not None:
            self._live_graph_monitor.stop()
            self._live_graph_monitor = None

    # -- MCP subprocess ----------------------------------------------------

    def start_mcp(self) -> subprocess.Popen[str]:
        """Start the MCP server as a subprocess."""
        return self._mcp_manager.start()

    def stop_mcp(self) -> None:
        """Stop the MCP server subprocess if it is running."""
        self._mcp_manager.stop()

    # -- Lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Stop all background tasks and close database connections."""
        self.stop_watch()
        self.stop_live_graph_monitor()
        self.stop_mcp()
        self.ctx.scanner.cache.close()
        self.ctx.timeline.close()
