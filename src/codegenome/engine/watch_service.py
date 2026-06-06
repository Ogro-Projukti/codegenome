"""Filesystem watch handlers and the watch service."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from codegenome.core import CodeGenomeEngine

LOG = logging.getLogger(__name__)


class _RebuildHandler(FileSystemEventHandler):
    """File system event handler to trigger incremental rebuilds with debouncing."""

    def __init__(self, engine: "CodeGenomeEngine", debounce_seconds: float) -> None:
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
        if not self._engine.should_process_path(rel_path):
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

    def __init__(self, engine: "CodeGenomeEngine", live_server=None) -> None:
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
                rel_path = (
                    Path(event.src_path)
                    .resolve()
                    .relative_to(self._engine.workspace)
                    .as_posix()
                )
                if not self._engine.should_process_path(rel_path):
                    return
                LOG.info(f"Surgical update triggered by {event_type} on {rel_path}")
                build_result = self._engine.surgical_update(
                    event.src_path, rel_path, event_type
                )

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


class WatchService:
    """Own the watchdog observer lifecycle for debounced rebuilds."""

    def __init__(self, engine: "CodeGenomeEngine") -> None:
        self._engine = engine
        self._observer: Observer | None = None

    def watch(self) -> None:
        """Start watching the workspace for file changes to trigger rebuilds."""
        engine = self._engine
        handler = _RebuildHandler(engine, engine.config.watch_debounce_seconds)
        self._observer = Observer()
        self._observer.schedule(handler, str(engine.workspace), recursive=True)
        self._observer.start()
        LOG.info("Watching workspace: %s", engine.workspace)
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            LOG.info("Stopping filesystem watch")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop watching the workspace for file changes."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
