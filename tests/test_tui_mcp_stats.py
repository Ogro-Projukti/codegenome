"""Tests for TUI MCP activity stats helpers."""

from __future__ import annotations

import json
from types import SimpleNamespace

from codegenome.tui.constants import PAGE_MAIN
from codegenome.tui.mcp_stats import (
    McpStatsController,
    fetch_mcp_activity_stats,
    fetch_mcp_health,
    format_mcp_activity_bar,
)


def test_format_mcp_activity_bar_without_server() -> None:
    text = format_mcp_activity_bar(None)
    assert "MCP calls: —" in text
    assert "Tokens saved: —" in text


def test_format_mcp_activity_bar_with_stats() -> None:
    text = format_mcp_activity_bar(
        {
            "session": {"total_calls": 2, "total_tokens_saved": 1200},
            "month": {"total_calls": 8, "total_tokens_saved": 12000},
            "lifetime": {"total_calls": 12, "total_tokens_saved": 45800},
        }
    )
    assert "MCP calls:" in text
    assert "12" in text
    assert "Saved:" in text
    assert "1,200" in text
    assert "12,000" in text
    assert "45,800" in text


def test_format_mcp_activity_bar_supports_legacy_flat_stats() -> None:
    text = format_mcp_activity_bar(
        {
            "total_calls": 12,
            "total_tokens_saved": 45800,
        }
    )
    assert "MCP calls:" in text
    assert "12" in text
    assert "Saved:" in text
    assert "45,800" in text


def test_fetch_mcp_health_parses_activity(monkeypatch) -> None:
    payload = {
        "status": "ok",
        "mcp_activity": {
            "total_calls": 3,
            "total_tokens_saved": 1200,
        },
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    def fake_urlopen(request, timeout=2.0):  # type: ignore[no-untyped-def]
        assert request.full_url == "http://127.0.0.1:7331/health"
        return FakeResponse()

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = fetch_mcp_health()
    assert result is not None
    assert result["mcp_activity"]["total_calls"] == 3
    assert result["mcp_activity"]["total_tokens_saved"] == 1200


def test_fetch_mcp_activity_stats_uses_activity_endpoint(monkeypatch) -> None:
    payload = {
        "status": "ok",
        "stats": {
            "total_calls": 5,
            "total_tokens_saved": 24489,
        },
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    def fake_urlopen(request, timeout=2.0):  # type: ignore[no-untyped-def]
        assert request.full_url == "http://127.0.0.1:7331/mcp/activity?limit=1"
        return FakeResponse()

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = fetch_mcp_activity_stats()
    assert result is not None
    assert result["total_calls"] == 5
    assert result["total_tokens_saved"] == 24489


class _FakeWidget:
    def __init__(self) -> None:
        self.text = ""

    def update(self, text: str) -> None:
        self.text = text


class _FakeApp:
    def __init__(self, page: str = PAGE_MAIN) -> None:
        self.pages = SimpleNamespace(current=page)
        self.worker = None

    def run_worker(self, worker, **kwargs):  # type: ignore[no-untyped-def]
        self.worker = (worker, kwargs)

    def call_from_thread(self, callback, text):  # type: ignore[no-untyped-def]
        callback(text)


def test_mcp_stats_controller_initializes_disconnected_state() -> None:
    widget = _FakeWidget()
    controller = McpStatsController(_FakeApp(), widget)  # type: ignore[arg-type]

    controller.initialize()

    assert "MCP calls: —" in widget.text


def test_mcp_stats_controller_only_polls_on_main_page() -> None:
    app = _FakeApp(page="other")
    controller = McpStatsController(app, _FakeWidget())  # type: ignore[arg-type]

    controller.background_refresh()

    assert app.worker is None


def test_mcp_stats_controller_updates_activity_text(monkeypatch) -> None:
    app = _FakeApp()
    widget = _FakeWidget()
    controller = McpStatsController(app, widget)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "codegenome.tui.mcp_stats.fetch_mcp_activity_stats",
        lambda: {"total_calls": 4, "total_tokens_saved": 1600},
    )

    controller.background_refresh()
    worker, kwargs = app.worker
    worker()

    assert kwargs["group"] == "mcp-stats"
    assert "4" in widget.text
    assert "1,600" in widget.text


def test_mcp_stats_controller_refreshes_after_tool_call_log() -> None:
    app = _FakeApp()
    controller = McpStatsController(app, _FakeWidget())  # type: ignore[arg-type]

    controller.refresh_after_tool_log(
        json.dumps({"event": "tool_call", "tool": "get_graph", "tokens_saved": 0})
    )

    assert app.worker is not None
    _, kwargs = app.worker
    assert kwargs["group"] == "mcp-stats-tool-call"
    assert kwargs["exclusive"] is False
