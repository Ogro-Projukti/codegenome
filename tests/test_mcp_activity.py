"""Tests for MCP activity tracking."""

from __future__ import annotations

from codegenome.mcp_activity import McpActivityTracker, summarize_args


def test_summarize_args_truncates_long_strings() -> None:
    summary = summarize_args({"query": "x" * 200})
    assert summary["query"].endswith("...")
    assert len(summary["query"]) == 120


def test_tracker_records_events_and_stats() -> None:
    tracker = McpActivityTracker()
    event = tracker.record(
        tool="search_nodes",
        client="cursor",
        args={"query": "auth"},
        status="ok",
        duration_ms=12.5,
    )
    stats = tracker.stats()
    assert stats["total_calls"] == 1
    assert stats["last_tool"] == "search_nodes"
    assert stats["last_client"] == "cursor"
    assert stats["last_call_at"] == event.timestamp

    recent = tracker.recent(limit=10)
    assert len(recent) == 1
    assert recent[0]["tool"] == "search_nodes"


def test_tracker_ring_buffer_respects_limit() -> None:
    tracker = McpActivityTracker(max_events=3)
    for index in range(5):
        tracker.record(
            tool=f"tool_{index}",
            client="test",
            args={},
            status="ok",
            duration_ms=1.0,
        )
    recent = tracker.recent(limit=10)
    assert len(recent) == 3
    assert recent[0]["tool"] == "tool_4"
