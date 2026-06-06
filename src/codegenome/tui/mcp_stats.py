"""Fetch and format MCP server activity stats for the TUI."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from textual.widgets import Static

from codegenome.tui.constants import PAGE_MAIN

MCP_DEFAULT_PORT = 7331


def _fetch_json(url: str, *, timeout: float) -> dict[str, Any] | None:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    return payload


def fetch_mcp_health(
    *,
    host: str = "127.0.0.1",
    port: int = MCP_DEFAULT_PORT,
    timeout: float = 2.0,
) -> dict[str, Any] | None:
    """Return the MCP ``/health`` JSON payload, or ``None`` when unreachable."""
    return _fetch_json(f"http://{host}:{port}/health", timeout=timeout)


def fetch_mcp_activity_stats(
    *,
    host: str = "127.0.0.1",
    port: int = MCP_DEFAULT_PORT,
    timeout: float = 2.0,
) -> dict[str, Any] | None:
    """Return aggregate MCP activity stats, or ``None`` when unreachable."""
    payload = _fetch_json(f"http://{host}:{port}/mcp/activity?limit=1", timeout=timeout)
    if payload is not None and isinstance(payload.get("stats"), dict):
        return payload["stats"]

    health = fetch_mcp_health(host=host, port=port, timeout=timeout)
    activity = health.get("mcp_activity") if health else None
    return activity if isinstance(activity, dict) else None


def format_mcp_activity_bar(activity: dict[str, Any] | None) -> str:
    """Render MCP call and token-savings counters for the dashboard stats bar."""
    if activity is None:
        return (
            "[dim]MCP calls: —  |  Tokens saved: —  "
            "(start MCP HTTP to track usage)[/dim]"
        )

    session = activity.get("session") if isinstance(activity.get("session"), dict) else activity
    month = activity.get("month") if isinstance(activity.get("month"), dict) else activity
    lifetime = activity.get("lifetime") if isinstance(activity.get("lifetime"), dict) else activity

    calls = int(lifetime.get("total_calls", 0))
    session_saved = int(session.get("total_tokens_saved", 0))
    month_saved = int(month.get("total_tokens_saved", 0))
    lifetime_saved = int(lifetime.get("total_tokens_saved", 0))
    return (
        f"MCP calls: [bold cyan]{calls:,}[/bold cyan]  "
        f"[dim]|[/dim]  "
        f"Saved: session [bold green]{session_saved:,}[/bold green]  "
        f"[dim]|[/dim]  "
        f"month [bold green]{month_saved:,}[/bold green]  "
        f"[dim]|[/dim]  "
        f"lifetime [bold green]{lifetime_saved:,}[/bold green]"
    )


class McpStatsController:
    """Coordinate MCP activity polling for the TUI."""

    def __init__(self, app: Any, widget: Static) -> None:
        self._app = app
        self._widget = widget

    def initialize(self) -> None:
        """Render the disconnected state before polling starts."""
        self._widget.update(format_mcp_activity_bar(None))

    def background_refresh(self) -> None:
        """Poll the MCP health endpoint when the main dashboard is visible."""
        if self._app.pages.current != PAGE_MAIN:
            return
        self.refresh()

    def refresh(self, *, group: str = "mcp-stats", exclusive: bool = True) -> None:
        """Schedule a stats refresh worker."""
        self._app.run_worker(
            self._poll,
            thread=True,
            exclusive=exclusive,
            exit_on_error=False,
            group=group,
        )

    def refresh_after_tool_log(self, message: str) -> None:
        """Refresh immediately after the MCP server logs a completed tool call."""
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return
        if payload.get("event") == "tool_call":
            self.refresh(group="mcp-stats-tool-call", exclusive=False)

    def _poll(self) -> None:
        """Worker body: fetch MCP activity and update the stats bar on the UI thread."""
        activity = fetch_mcp_activity_stats()
        text = format_mcp_activity_bar(activity)
        self._app.call_from_thread(self._widget.update, text)
