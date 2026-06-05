"""Poll workspace metrics and trigger incremental graph rebuilds on growth."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from codegenome.workspace_metrics import (
    WorkspaceMetrics,
    WorkspaceMetricsScanner,
    metrics_increased,
)

if TYPE_CHECKING:
    from codegenome.core import CodeGenomeEngine

LOG = logging.getLogger(__name__)


class LiveGraphMonitor:
    """Track file/line totals and rebuild the graph when either increases."""

    def __init__(
        self,
        engine: CodeGenomeEngine,
        poll_interval_seconds: float,
    ) -> None:
        """Initialize the LiveGraphMonitor.

        Args:
            engine (CodeGenomeEngine): The engine used for checking and rebuilding the graph.
            poll_interval_seconds (float): Interval in seconds between polls.
        """
        self._engine = engine
        self._poll_interval_seconds = max(1.0, float(poll_interval_seconds))
        self._scanner = WorkspaceMetricsScanner(engine.workspace)
        self._previous: WorkspaceMetrics | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rebuild_lock = threading.Lock()

    def start(self) -> None:
        """Start polling the workspace metrics in a background daemon thread."""
        self._previous = self._scanner.scan()
        LOG.info(
            "Live graph monitor started (interval=%ss, files=%s, lines=%s)",
            self._poll_interval_seconds,
            self._previous.file_count,
            self._previous.line_count,
        )
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="codegenome-live-graph",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the polling thread and wait for it to exit."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval_seconds + 5.0)
            self._thread = None

    def _poll_loop(self) -> None:
        """Internal loop that polls workspace metrics until stopped."""
        while not self._stop.wait(self._poll_interval_seconds):
            self._poll_once()

    def _poll_once(self) -> None:
        """Perform a single poll of workspace metrics and trigger rebuild if grown."""
        current = self._scanner.scan()
        previous = self._previous
        if previous is None:
            self._previous = current
            return

        if not metrics_increased(previous, current):
            LOG.debug(
                "Live graph metrics unchanged (files=%s, lines=%s)",
                current.file_count,
                current.line_count,
            )
            return

        LOG.info(
            "Workspace grew (files %s→%s, lines %s→%s); rebuilding graph incrementally",
            previous.file_count,
            current.file_count,
            previous.line_count,
            current.line_count,
        )

        with self._rebuild_lock:
            try:
                self._engine.rebuild_incremental()
            except Exception:  # noqa: BLE001 - keep monitor alive
                LOG.exception("Live graph incremental rebuild failed")
                return

        self._previous = current

    def run_forever(self) -> None:
        """Block the current thread while polling until interrupted."""
        self.start()
        try:
            while not self._stop.is_set():
                time.sleep(1.0)
        except KeyboardInterrupt:
            LOG.info("Stopping live graph monitor")
        finally:
            self.stop()
