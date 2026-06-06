"""In-memory MCP tool-call activity tracking for observability."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIVITY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mcp_activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    tool TEXT NOT NULL,
    client TEXT NOT NULL,
    args_json TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    response_tokens INTEGER NOT NULL DEFAULT 0,
    tokens_saved INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_mcp_activity_events_timestamp
ON mcp_activity_events(timestamp);

CREATE INDEX IF NOT EXISTS idx_mcp_activity_events_tool
ON mcp_activity_events(tool);
"""


@dataclass(frozen=True)
class ActivityEvent:
    """Represents a single MCP tool call activity event."""

    timestamp: float
    tool: str
    client: str
    args: dict[str, Any]
    status: str
    duration_ms: float
    response_tokens: int = 0
    tokens_saved: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the ActivityEvent instance to a dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the event.
        """
        return asdict(self)


class McpActivityStore:
    """SQLite-backed MCP activity history for long-lived savings totals."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._lock:
            self._conn.executescript(ACTIVITY_SCHEMA_SQL)
            self._conn.commit()

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            self._conn.close()

    def record(self, event: ActivityEvent) -> None:
        """Persist one MCP activity event."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO mcp_activity_events (
                    timestamp, tool, client, args_json, status, duration_ms,
                    response_tokens, tokens_saved, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.timestamp,
                    event.tool,
                    event.client,
                    json.dumps(event.args, default=str, sort_keys=True),
                    event.status,
                    event.duration_ms,
                    event.response_tokens,
                    event.tokens_saved,
                    event.error,
                ),
            )
            self._conn.commit()

    def stats(self, *, since: float | None = None) -> dict[str, Any]:
        """Return aggregate stats for all persisted events or events since a time."""
        where = "WHERE timestamp >= ?" if since is not None else ""
        params: tuple[float, ...] = (since,) if since is not None else ()
        with self._lock:
            row = self._conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_calls,
                    COALESCE(SUM(CASE WHEN status = 'ok' THEN tokens_saved ELSE 0 END), 0)
                        AS total_tokens_saved,
                    COALESCE(SUM(CASE WHEN status = 'ok' THEN response_tokens ELSE 0 END), 0)
                        AS total_response_tokens,
                    MAX(timestamp) AS last_call_at
                FROM mcp_activity_events
                {where}
                """,
                params,
            ).fetchone()
            calls_by_tool = self._counts_by_tool("COUNT(*)", where, params)
            tokens_by_tool = self._counts_by_tool(
                "SUM(CASE WHEN status = 'ok' THEN tokens_saved ELSE 0 END)",
                where,
                params,
            )
            last = self._conn.execute(
                f"""
                SELECT tool, client
                FROM mcp_activity_events
                {where}
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                params,
            ).fetchone()

        return {
            "total_calls": int(row["total_calls"] or 0),
            "recent_count": int(row["total_calls"] or 0),
            "total_tokens_saved": int(row["total_tokens_saved"] or 0),
            "total_response_tokens": int(row["total_response_tokens"] or 0),
            "calls_by_tool": calls_by_tool,
            "tokens_saved_by_tool": tokens_by_tool,
            "last_call_at": row["last_call_at"],
            "last_tool": last["tool"] if last else None,
            "last_client": last["client"] if last else None,
        }

    def _counts_by_tool(
        self,
        aggregate: str,
        where: str,
        params: tuple[float, ...],
    ) -> dict[str, int]:
        rows = self._conn.execute(
            f"""
            SELECT tool, COALESCE({aggregate}, 0) AS value
            FROM mcp_activity_events
            {where}
            GROUP BY tool
            ORDER BY tool
            """,
            params,
        ).fetchall()
        return {row["tool"]: int(row["value"] or 0) for row in rows}


class McpActivityTracker:
    """Thread-safe ring buffer of recent MCP tool invocations."""

    MAX_EVENTS = 100

    def __init__(
        self,
        max_events: int | None = None,
        *,
        store: McpActivityStore | None = None,
    ) -> None:
        """Initialize the McpActivityTracker.

        Args:
            max_events (int | None, optional): The maximum number of events to retain. Defaults to None.
        """
        limit = max_events if max_events is not None else self.MAX_EVENTS
        self._max_events = max(1, limit)
        self._lock = threading.RLock()
        self._events: deque[ActivityEvent] = deque(maxlen=self._max_events)
        self._total_calls = 0
        self._total_tokens_saved = 0
        self._total_response_tokens = 0
        self._calls_by_tool: dict[str, int] = {}
        self._tokens_saved_by_tool: dict[str, int] = {}
        self._last_call_at: float | None = None
        self._last_tool: str | None = None
        self._last_client: str | None = None
        self._store = store

    def record(
        self,
        *,
        tool: str,
        client: str,
        args: dict[str, Any],
        status: str,
        duration_ms: float,
        response_tokens: int = 0,
        tokens_saved: int = 0,
        error: str | None = None,
    ) -> ActivityEvent:
        """Record a new tool call event.

        Args:
            tool (str): The name of the tool called.
            client (str): The identifier of the client making the call.
            args (dict[str, Any]): Arguments passed to the tool.
            status (str): The status of the call (e.g., 'ok', 'error').
            duration_ms (float): Execution duration in milliseconds.
            error (str | None, optional): Error message if the call failed. Defaults to None.

        Returns:
            ActivityEvent: The newly created activity event.
        """
        event = ActivityEvent(
            timestamp=time.time(),
            tool=tool,
            client=client,
            args=args,
            status=status,
            duration_ms=round(duration_ms, 2),
            response_tokens=max(0, response_tokens),
            tokens_saved=max(0, tokens_saved),
            error=error,
        )
        with self._lock:
            self._events.appendleft(event)
            self._total_calls += 1
            if status == "ok":
                self._total_tokens_saved += event.tokens_saved
                self._total_response_tokens += event.response_tokens
                self._calls_by_tool[tool] = self._calls_by_tool.get(tool, 0) + 1
                self._tokens_saved_by_tool[tool] = (
                    self._tokens_saved_by_tool.get(tool, 0) + event.tokens_saved
                )
            self._last_call_at = event.timestamp
            self._last_tool = tool
            self._last_client = client
        if self._store is not None:
            self._store.record(event)
        return event

    def stats(self) -> dict[str, Any]:
        """Get aggregate statistics for recorded MCP activities.

        Returns:
            dict[str, Any]: A dictionary containing total calls, recent count,
            last call time, last tool used, and last client.
        """
        with self._lock:
            return {
                "total_calls": self._total_calls,
                "recent_count": len(self._events),
                "total_tokens_saved": self._total_tokens_saved,
                "total_response_tokens": self._total_response_tokens,
                "calls_by_tool": dict(sorted(self._calls_by_tool.items())),
                "tokens_saved_by_tool": dict(sorted(self._tokens_saved_by_tool.items())),
                "last_call_at": self._last_call_at,
                "last_tool": self._last_tool,
                "last_client": self._last_client,
            }

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent tool call events up to a specified limit.

        Args:
            limit (int, optional): Maximum number of events to return. Defaults to 50.

        Returns:
            list[dict[str, Any]]: A list of recent events represented as dictionaries.
        """
        with self._lock:
            events = list(self._events)[:limit]
        return [event.to_dict() for event in events]

    def combined_stats(self) -> dict[str, Any]:
        """Return persisted lifetime/month stats with the current session nested."""
        session = self.stats()
        if self._store is None:
            return {
                **session,
                "session": session,
                "month": session,
                "lifetime": session,
                "persistent": False,
            }

        month = self._store.stats(since=_current_month_start())
        lifetime = self._store.stats()
        return {
            **lifetime,
            "session": session,
            "month": month,
            "lifetime": lifetime,
            "persistent": True,
        }


def summarize_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, log-safe view of tool arguments.

    Args:
        arguments (dict[str, Any]): The raw arguments to summarize.

    Returns:
        dict[str, Any]: The summarized arguments with long strings truncated.
    """
    summary: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 120:
            summary[key] = f"{value[:117]}..."
        else:
            summary[key] = value
    return summary


def _current_month_start() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()
