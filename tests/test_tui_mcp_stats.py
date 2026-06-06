"""Tests for TUI MCP activity stats helpers."""

from __future__ import annotations

import json

from codegenome.tui.mcp_stats import fetch_mcp_health, format_mcp_activity_bar


def test_format_mcp_activity_bar_without_server() -> None:
    text = format_mcp_activity_bar(None)
    assert "MCP calls: —" in text
    assert "Tokens saved: —" in text


def test_format_mcp_activity_bar_with_stats() -> None:
    text = format_mcp_activity_bar(
        {
            "total_calls": 12,
            "total_tokens_saved": 45800,
        }
    )
    assert "MCP calls:" in text
    assert "12" in text
    assert "Tokens saved:" in text
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
