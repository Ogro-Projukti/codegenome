"""WatcherEngine orchestration for builds, watching, MCP, and exports."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import networkx as nx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from codegenome.builder import GraphBuilder
from codegenome.clusterer import GraphClusterer
from codegenome.exporter import GraphExporter
from codegenome.intelligence import GraphIntelligence, IntelligenceReport
from codegenome.parser import SourceParser
from codegenome.scanner import ScanResult, WorkspaceScanner
from codegenome.live_graph_monitor import LiveGraphMonitor
from codegenome.timeline import GraphTimeline

LOG = logging.getLogger(__name__)

DEFAULT_EXPORT_FORMATS = ("json", "html", "markdown")


@dataclass
class WatcherConfig:
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


@dataclass
class BuildResult:
    graph: nx.DiGraph
    report: IntelligenceReport
    snapshot_id: int | None
    export_paths: dict[str, Path] = field(default_factory=dict)


class _RebuildHandler(FileSystemEventHandler):
    def __init__(self, engine: WatcherEngine, debounce_seconds: float) -> None:
        self._engine = engine
        self._debounce_seconds = debounce_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        rel_path = self._relative_path(event.src_path)
        if rel_path is None:
            return
        if rel_path.startswith(".watcher"):
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self._debounce_seconds,
                self._trigger_rebuild,
            )
            self._timer.daemon = True
            self._timer.start()

    def _relative_path(self, src_path: str) -> str | None:
        try:
            return Path(src_path).resolve().relative_to(self._engine.workspace).as_posix()
        except ValueError:
            return None

    def _trigger_rebuild(self) -> None:
        LOG.info(
            "Workspace changes settled; rebuilding graph (debounce=%ss)",
            self._debounce_seconds,
        )
        try:
            self._engine.rebuild_incremental()
        except Exception:  # noqa: BLE001 - keep watcher alive
            LOG.exception("Incremental rebuild failed")


class WatcherEngine:
    """Coordinate scanning, graph building, exports, watching, and MCP startup."""

    def __init__(self, config: WatcherConfig) -> None:
        self.config = config
        self.workspace = config.workspace.resolve()
        self.watcher_dir = self.workspace / ".watcher"
        self.db_path = (config.db_path or self.watcher_dir / "watcher.db").resolve()
        self.export_dir = (config.export_dir or self.watcher_dir / "exports").resolve()
        self.graph_json_path = (
            config.graph_json_path or self.watcher_dir / "graph.json"
        ).resolve()

        self.watcher_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        self.scanner = WorkspaceScanner(
            self.workspace,
            cache_db=self.watcher_dir / "scan_cache.db",
        )
        self.parser = SourceParser()
        self.builder = GraphBuilder()
        self.clusterer = GraphClusterer()
        self.timeline = GraphTimeline(self.db_path)

        self._observer: Observer | None = None
        self._live_graph_monitor: LiveGraphMonitor | None = None
        self._mcp_process: subprocess.Popen[str] | None = None
        self._loaded_existing_graph = self._load_existing_graph()

    def build(self, *, full: bool = False) -> BuildResult:
        incremental = not full and self._loaded_existing_graph
        scan = self.scanner.scan(incremental=incremental)
        parses = self._parse_scan(scan)

        if incremental and self.builder.graph.number_of_nodes() > 0:
            graph = self.builder.update(scan, parses)
            label = "incremental"
        else:
            graph = self.builder.build(scan, parses)
            label = "full"

        self.clusterer.annotate(graph)
        intelligence = GraphIntelligence(graph)
        report = intelligence.analyze()

        exporter = GraphExporter(
            graph,
            report=report,
            workspace_name=self.workspace.name,
        )

        snapshot_id = self.timeline.record_snapshot(graph, label=label)
        export_paths = self._run_exports(exporter)
        self._loaded_existing_graph = True

        return BuildResult(
            graph=graph,
            report=report,
            snapshot_id=snapshot_id,
            export_paths=export_paths,
        )

    def rebuild_incremental(self) -> BuildResult:
        return self.build(full=False)

    def watch(self) -> None:
        handler = _RebuildHandler(self, self.config.watch_debounce_seconds)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.workspace), recursive=True)
        self._observer.start()
        LOG.info("Watching workspace: %s", self.workspace)
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            LOG.info("Stopping filesystem watch")
        finally:
            self.stop_watch()

    def stop_watch(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

    def monitor_live_graph(self) -> None:
        self._live_graph_monitor = LiveGraphMonitor(
            self,
            poll_interval_seconds=self.config.live_graph_poll_seconds,
        )
        self._live_graph_monitor.run_forever()

    def stop_live_graph_monitor(self) -> None:
        if self._live_graph_monitor is not None:
            self._live_graph_monitor.stop()
            self._live_graph_monitor = None

    def start_mcp(self) -> subprocess.Popen[str]:
        if self._mcp_process and self._mcp_process.poll() is None:
            return self._mcp_process

        if getattr(sys, "frozen", False):
            command = [
                sys.executable,
                "--run-mcp-server",
                "--db-path",
                str(self.db_path),
                "--host",
                self.config.mcp_host,
                "--port",
                str(self.config.mcp_port),
                "--transport",
                "http",
            ]
        else:
            command = [
                sys.executable,
                "-m",
                "codegenome.mcp_server",
                "--db-path",
                str(self.db_path),
                "--host",
                self.config.mcp_host,
                "--port",
                str(self.config.mcp_port),
                "--transport",
                "http",
            ]
        LOG.info("Starting MCP server: %s", " ".join(command))
        self._mcp_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._start_mcp_stderr_forwarder(self._mcp_process)
        return self._mcp_process

    def _start_mcp_stderr_forwarder(self, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return

        def forward() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                sys.stderr.write(line)
                sys.stderr.flush()

        thread = threading.Thread(target=forward, name="watcher-mcp-stderr", daemon=True)
        thread.start()

    def stop_mcp(self) -> None:
        if self._mcp_process is None:
            return
        if self._mcp_process.poll() is None:
            self._mcp_process.terminate()
            try:
                self._mcp_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._mcp_process.kill()
        self._mcp_process = None

    def export(
        self,
        formats: Iterable[str] | None = None,
        *,
        report: IntelligenceReport | None = None,
    ) -> dict[str, Path]:
        graph = self.builder.graph
        if graph.number_of_nodes() == 0:
            raise RuntimeError("Cannot export before building a graph")

        if report is None:
            report = GraphIntelligence(graph).analyze()

        exporter = GraphExporter(
            graph,
            report=report,
            workspace_name=self.workspace.name,
        )
        return self._run_exports(exporter, formats=formats)

    def close(self) -> None:
        self.stop_watch()
        self.stop_live_graph_monitor()
        self.stop_mcp()
        self.scanner.cache.close()
        self.timeline.close()

    def _load_existing_graph(self) -> bool:
        snapshots = self.timeline.list_snapshots()
        if not snapshots:
            return False
        latest = snapshots[-1]
        self.builder.graph = self.timeline.load_snapshot(latest.snapshot_id)
        return self.builder.graph.number_of_nodes() > 0

    def _parse_scan(self, scan: ScanResult) -> dict:
        parses = {}
        for record in scan.files:
            rel_path = record.path
            if scan.deleted and rel_path in scan.deleted:
                continue
            parsed = self.parser.parse_file(record.absolute_path)
            if parsed is not None:
                parses[rel_path] = parsed
        return parses

    def _run_exports(
        self,
        exporter: GraphExporter,
        formats: Iterable[str] | None = None,
    ) -> dict[str, Path]:
        selected = tuple(formats) if formats is not None else self.config.export_formats
        paths = exporter.export_all(self.export_dir, selected)
        json_path = exporter.export_json(self.graph_json_path)
        paths["graph_json"] = json_path
        return paths
