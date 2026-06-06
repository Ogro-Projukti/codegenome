"""Fetch and format MCP server activity stats for the TUI."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

MCP_DEFAULT_PORT = 7331


def fetch_mcp_health(
    *,
    host: str = "127.0.0.1",
    port: int = MCP_DEFAULT_PORT,
    timeout: float = 2.0,
) -> dict[str, Any] | None:
    """Return the MCP ``/health`` JSON payload, or ``None`` when unreachable."""
    url = f"http://{host}:{port}/health"
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


def format_mcp_activity_bar(activity: dict[str, Any] | None) -> str:
    """Render MCP call and token-savings counters for the dashboard stats bar."""
    if activity is None:
        return (
            "[dim]MCP calls: —  |  Tokens saved: —  "
            "(start MCP HTTP to track usage)[/dim]"
        )

    calls = int(activity.get("total_calls", 0))
    tokens_saved = int(activity.get("total_tokens_saved", 0))
    return (
        f"MCP calls: [bold cyan]{calls:,}[/bold cyan]  "
        f"[dim]|[/dim]  "
        f"Tokens saved: [bold green]{tokens_saved:,}[/bold green]"
    )
