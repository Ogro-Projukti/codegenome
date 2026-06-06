"""Tests for MCP activity tracking."""

from __future__ import annotations

from pathlib import Path

from codegenome.mcp_activity import McpActivityStore, McpActivityTracker, summarize_args


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
        response_tokens=42,
        tokens_saved=900,
    )
    stats = tracker.stats()
    assert stats["total_calls"] == 1
    assert stats["total_tokens_saved"] == 900
    assert stats["total_response_tokens"] == 42
    assert stats["calls_by_tool"] == {"search_nodes": 1}
    assert stats["tokens_saved_by_tool"] == {"search_nodes": 900}
    assert stats["last_tool"] == "search_nodes"
    assert stats["last_client"] == "cursor"
    assert stats["last_call_at"] == event.timestamp

    recent = tracker.recent(limit=10)
    assert len(recent) == 1
    assert recent[0]["tool"] == "search_nodes"
    assert recent[0]["response_tokens"] == 42
    assert recent[0]["tokens_saved"] == 900


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


def test_tracker_persists_lifetime_and_monthly_stats(tmp_path: Path) -> None:
    db_path = tmp_path / "activity.db"
    store = McpActivityStore(db_path)
    tracker = McpActivityTracker(store=store)
    tracker.record(
        tool="search_nodes",
        client="mcp",
        args={"query": "auth"},
        status="ok",
        duration_ms=10,
        response_tokens=100,
        tokens_saved=900,
    )
    store.close()

    new_store = McpActivityStore(db_path)
    new_tracker = McpActivityTracker(store=new_store)
    stats = new_tracker.combined_stats()

    assert stats["session"]["total_calls"] == 0
    assert stats["lifetime"]["total_calls"] == 1
    assert stats["lifetime"]["total_tokens_saved"] == 900
    assert stats["month"]["total_tokens_saved"] == 900
    assert stats["total_calls"] == 1
    assert stats["total_tokens_saved"] == 900
    new_store.close()
