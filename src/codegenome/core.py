"""CodeGenomeEngine orchestration for builds, watching, MCP, and exports."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import networkx as nx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from codegenome.builder import GraphBuilder
from codegenome.clusterer import GraphClusterer
from codegenome.exporter import GraphExporter
from codegenome.intelligence import GraphIntelligence, IntelligenceReport
from codegenome.parser import SourceParser
from codegenome.scanner import ScanResult, WorkspaceScanner, FileRecord
from codegenome.live_graph_monitor import LiveGraphMonitor
from codegenome.timeline import GraphTimeline
from codegenome.registry import GlobalDependencyRegistry

LOG = logging.getLogger(__name__)

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


@dataclass
class BuildResult:
    """Container for the output of a CodeGenomeEngine build or update."""

    graph: nx.DiGraph
    report: IntelligenceReport
    snapshot_id: int | None
    export_paths: dict[str, Path] = field(default_factory=dict)


class _RebuildHandler(FileSystemEventHandler):
    """File system event handler to trigger incremental rebuilds with debouncing."""

    def __init__(self, engine: CodeGenomeEngine, debounce_seconds: float) -> None:
        """Initialize the _RebuildHandler.

        Args:
            engine (CodeGenomeEngine): The engine to invoke rebuilds on.
            debounce_seconds (float): Delay in seconds before triggering a rebuild.
        """
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
        if rel_path.startswith(".genome"):
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
        except Exception:  # noqa: BLE001 - keep codegenome alive
            LOG.exception("Incremental rebuild failed")


class SurgicalUpdateHandler(FileSystemEventHandler):
    """Surgically update the graph on individual file changes."""
    def __init__(self, engine: CodeGenomeEngine, live_server=None) -> None:
        """Initialize the SurgicalUpdateHandler.

        Args:
            engine (CodeGenomeEngine): The engine performing graph updates.
            live_server (LiveGraphServer | None, optional): Server for real-time broadcasts. Defaults to None.
        """
        self._engine = engine
        self._live_server = live_server
        self._lock = threading.Lock()

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "modified")

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "created")

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "deleted")

    def _handle_event(self, event: FileSystemEvent, event_type: str) -> None:
        if event.is_directory or not event.src_path.endswith(".py"):
            return

        with self._lock:
            try:
                rel_path = Path(event.src_path).resolve().relative_to(self._engine.workspace).as_posix()
                LOG.info(f"Surgical update triggered by {event_type} on {rel_path}")
                build_result = self._engine.surgical_update(event.src_path, rel_path, event_type)
                
                if self._live_server and build_result and build_result.snapshot_id:
                    snapshots = self._engine.timeline.list_snapshots()
                    if len(snapshots) >= 2:
                        prev_id = snapshots[-2].snapshot_id
                        curr_id = snapshots[-1].snapshot_id
                        delta = self._engine.timeline.compute_delta(prev_id, curr_id)
                        
                        delta_payload = {
                            "type": "graph_delta",
                            "snapshot_id": curr_id,
                            "added_nodes": delta.added_nodes,
                            "removed_nodes": delta.removed_nodes,
                            "modified_nodes": delta.modified_nodes,
                            "added_edges": delta.added_edges,
                            "removed_edges": delta.removed_edges,
                        }
                        self._live_server.sync_broadcast_graph_delta(delta_payload)
                        LOG.info("Broadcasted surgical AST delta to WebSocket clients.")
            except ValueError:
                pass
            except Exception:  # noqa: BLE001
                LOG.exception(f"Surgical update failed for {event.src_path}")


class CodeGenomeEngine:
    """Coordinate scanning, graph building, exports, watching, and MCP startup."""

    def __init__(self, config: CodeGenomeConfig) -> None:
        """Initialize the CodeGenomeEngine.

        Args:
            config (CodeGenomeConfig): The configuration defining paths and options.
        """
        self.config = config
        self.workspace = config.workspace.resolve()
        self.genome_dir = self.workspace / ".genome"
        self.db_path = (config.db_path or self.genome_dir / "codegenome.db").resolve()
        self.export_dir = (config.export_dir or self.genome_dir / "exports").resolve()
        self.graph_json_path = (
            config.graph_json_path or self.genome_dir / "graph.json"
        ).resolve()

        self.genome_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        self.scanner = WorkspaceScanner(
            self.workspace,
            cache_db=self.genome_dir / "scan_cache.db",
        )
        self.parser = SourceParser()
        self.builder = GraphBuilder()
        self.clusterer = GraphClusterer()
        self.timeline = GraphTimeline(self.db_path)
        self.registry = GlobalDependencyRegistry()

        self._observer: Observer | None = None
        self._live_graph_monitor: LiveGraphMonitor | None = None
        self._mcp_process: subprocess.Popen[str] | None = None
        self._loaded_existing_graph = self._load_existing_graph()

    def build(
        self,
        *,
        full: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> BuildResult:
        """Build or rebuild the graph from source files.

        Args:
            full (bool, optional): Force a full rebuild instead of incremental. Defaults to False.
            on_progress (ProgressCallback | None, optional): Optional callback for
                human-readable progress messages during long-running phases.

        Returns:
            BuildResult: The result of the build process.
        """
        def emit(message: str) -> None:
            if on_progress is not None:
                on_progress(message)

        incremental = not full and self._loaded_existing_graph
        emit("Scanning workspace...")
        scan = self.scanner.scan(
            incremental=incremental,
            on_progress=lambda count: emit(f"Scanning... {count:,} files"),
        )
        file_count = len(scan.files)
        change_parts: list[str] = []
        if scan.added:
            change_parts.append(f"{len(scan.added):,} added")
        if scan.modified:
            change_parts.append(f"{len(scan.modified):,} modified")
        if scan.deleted:
            change_parts.append(f"{len(scan.deleted):,} deleted")
        change_summary = f" ({', '.join(change_parts)})" if change_parts else ""
        emit(f"Scan complete: {file_count:,} files{change_summary}")

        parses = self._parse_scan(scan, on_progress=on_progress)

        if incremental and self.builder.graph.number_of_nodes() > 0:
            emit("Updating graph...")
            graph, provides, consumes = self.builder.update(scan, parses)
            label = "incremental"
        else:
            emit("Building graph...")
            graph, provides, consumes = self.builder.build(scan, parses)
            label = "full"

        deleted_fqns = set()
        for deleted_path in scan.deleted:
            deleted_fqns.update(self.registry.remove_file(deleted_path))
            
        for path, p_set in provides.items():
            deleted_fqns.update(self.registry.update_file(path, p_set, consumes.get(path, set())))
            
        for fqn in deleted_fqns:
            for dep_path in self.registry.get_dependents(fqn):
                self._flag_broken_proxy(graph, dep_path, fqn)

        self.clusterer.annotate(graph)
        emit("Analyzing dependencies...")
        intelligence = GraphIntelligence(graph, registry=self.registry)
        intelligence.annotate_coupling_metrics()
        intel_report = intelligence.analyze()

        emit("Exporting graph...")
        exporter = GraphExporter(
            graph,
            report=intel_report,
            workspace_name=self.workspace.name,
        )

        snapshot_id = self.timeline.record_snapshot(graph, label=label)
        export_paths = self._run_exports(exporter)
        self._loaded_existing_graph = True

        return BuildResult(
            graph=graph,
            report=intel_report,
            snapshot_id=snapshot_id,
            export_paths=export_paths,
        )

    def rebuild_incremental(self) -> BuildResult:
        """Perform an incremental rebuild of the graph.

        Returns:
            BuildResult: The result of the incremental rebuild.
        """
        return self.build(full=False)

    def surgical_update(self, abs_path: str, rel_path: str, event_type: str) -> BuildResult | None:
        """Perform a surgical update on the graph for a single file change.

        Args:
            abs_path (str): The absolute path of the changed file.
            rel_path (str): The relative path of the changed file from the workspace.
            event_type (str): The type of file event (e.g., 'created', 'modified', 'deleted').

        Returns:
            BuildResult | None: The result of the update, or None if skipped.
        """
        if not self._loaded_existing_graph:
            LOG.warning("Cannot surgical update without existing graph. Rebuilding incremental...")
            return self.rebuild_incremental()

        files: list[FileRecord] = []
        added = set()
        modified = set()
        deleted = set()
        parses = {}

        if event_type == "deleted" or not os.path.exists(abs_path):
            deleted.add(rel_path)
        else:
            try:
                stat = os.stat(abs_path)
                record = FileRecord(
                    path=rel_path,
                    absolute_path=abs_path,
                    sha256="",
                    size=stat.st_size,
                    mtime=stat.st_mtime
                )
                files.append(record)
                if event_type == "created":
                    added.add(rel_path)
                else:
                    modified.add(rel_path)
                    
                parsed = self.parser.parse_file(abs_path)
                if parsed is not None:
                    parses[rel_path] = parsed
            except OSError:
                deleted.add(rel_path)

        scan = ScanResult(
            root=str(self.workspace),
            files=files,
            added=added,
            modified=modified,
            deleted=deleted,
            unchanged=set()
        )
        
        graph, provides, consumes = self.builder.update(scan, parses)
        
        deleted_fqns = set()
        for deleted_path in deleted:
            deleted_fqns.update(self.registry.remove_file(deleted_path))
            
        for path, p_set in provides.items():
            deleted_fqns.update(self.registry.update_file(path, p_set, consumes.get(path, set())))
            
        for fqn in deleted_fqns:
            for dep_path in self.registry.get_dependents(fqn):
                self._flag_broken_proxy(graph, dep_path, fqn)
                
        self.clusterer.annotate(graph)
        
        intelligence = GraphIntelligence(graph, registry=self.registry)
        intelligence.annotate_coupling_metrics()
        report = intelligence.analyze()
        
        exporter = GraphExporter(
            graph,
            report=report,
            workspace_name=self.workspace.name,
        )
        
        snapshot_id = self.timeline.record_snapshot(graph, label=f"surgical_{event_type}")
        export_paths = self._run_exports(exporter)
        
        return BuildResult(
            graph=graph,
            report=report,
            snapshot_id=snapshot_id,
            export_paths=export_paths,
        )

    def _flag_broken_proxy(self, graph, file_path: str, fqn: str) -> None:
        proxy_id = f"proxy:{file_path}:{fqn}"
        if graph.has_node(proxy_id):
            graph.set_node_attr(proxy_id, "is_broken", True)

    def watch(self) -> None:
        """Start watching the workspace for file changes to trigger rebuilds."""
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
        """Stop watching the workspace for file changes."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

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

    def start_mcp(self) -> subprocess.Popen[str]:
        """Start the MCP server as a subprocess.

        Returns:
            subprocess.Popen[str]: The running MCP server process.
        """
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

        thread = threading.Thread(target=forward, name="codegenome-mcp-stderr", daemon=True)
        thread.start()

    def stop_mcp(self) -> None:
        """Stop the MCP server subprocess if it is running."""
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
        """Export the graph to various formats.

        Args:
            formats (Iterable[str] | None, optional): Formats to export (e.g. 'json', 'html'). Defaults to None.
            report (IntelligenceReport | None, optional): An existing report. Defaults to None.

        Returns:
            dict[str, Path]: A dictionary mapping format names to their exported file paths.

        Raises:
            RuntimeError: If called before a graph has been built.
        """
        graph = self.builder.graph
        if graph.number_of_nodes() == 0:
            raise RuntimeError("Cannot export before building a graph")

        if report is None:
            intelligence = GraphIntelligence(graph)
            intelligence.annotate_coupling_metrics()
            report = intelligence.analyze()

        exporter = GraphExporter(
            graph,
            report=report,
            workspace_name=self.workspace.name,
        )
        return self._run_exports(exporter, formats=formats)

    def close(self) -> None:
        """Stop all background tasks and close database connections."""
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

    def _parse_scan(
        self,
        scan: ScanResult,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> dict:
        parses = {}
        total = len(scan.files)
        if on_progress is not None:
            on_progress(f"Parsing 0 / {total:,} files...")

        for index, record in enumerate(scan.files, start=1):
            rel_path = record.path
            if scan.deleted and rel_path in scan.deleted:
                continue
            parsed = self.parser.parse_file(record.absolute_path)
            if parsed is not None:
                parses[rel_path] = parsed
            if on_progress is not None and (
                index == 1
                or index == total
                or index % PARSE_PROGRESS_INTERVAL == 0
            ):
                on_progress(f"Parsing {index:,} / {total:,} files...")
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
