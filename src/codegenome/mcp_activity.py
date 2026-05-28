"""In-memory MCP tool-call activity tracking for observability."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ActivityEvent:
    timestamp: float
    tool: str
    client: str
    args: dict[str, Any]
    status: str
    duration_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class McpActivityTracker:
    """Thread-safe ring buffer of recent MCP tool invocations."""

    MAX_EVENTS = 100

    def __init__(self, max_events: int | None = None) -> None:
        limit = max_events if max_events is not None else self.MAX_EVENTS
        self._max_events = max(1, limit)
        self._lock = threading.RLock()
        self._events: deque[ActivityEvent] = deque(maxlen=self._max_events)
        self._total_calls = 0
        self._last_call_at: float | None = None
        self._last_tool: str | None = None
        self._last_client: str | None = None

    def record(
        self,
        *,
        tool: str,
        client: str,
        args: dict[str, Any],
        status: str,
        duration_ms: float,
        error: str | None = None,
    ) -> ActivityEvent:
        event = ActivityEvent(
            timestamp=time.time(),
            tool=tool,
            client=client,
            args=args,
            status=status,
            duration_ms=round(duration_ms, 2),
            error=error,
        )
        with self._lock:
            self._events.appendleft(event)
            self._total_calls += 1
            self._last_call_at = event.timestamp
            self._last_tool = tool
            self._last_client = client
        return event

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_calls": self._total_calls,
                "recent_count": len(self._events),
                "last_call_at": self._last_call_at,
                "last_tool": self._last_tool,
                "last_client": self._last_client,
            }

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)[:limit]
        return [event.to_dict() for event in events]


def summarize_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, log-safe view of tool arguments."""
    summary: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 120:
            summary[key] = f"{value[:117]}..."
        else:
            summary[key] = value
    return summary
