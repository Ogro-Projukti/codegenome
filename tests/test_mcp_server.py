"""Tests for Watcher MCP server and graph store."""

from __future__ import annotations

import asyncio
from pathlib import Path

from codegenome.graph_api import create_graph
import pytest

from codegenome.graph_store import GraphStore
from codegenome.mcp_server import (
    create_server,
    error,
    GraphService,
    ok,
    parse_args,
    ServerConfig,
    validate_config,
)
from codegenome.timeline import GraphTimeline


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    graph = create_graph("igraph")
    graph.add_node(
        "file:alpha.py",
        node_type="file",
        file_path="alpha.py",
        churn=2,
        complexity=1,
    )
    graph.add_node(
        "symbol:alpha.py:alpha",
        node_type="symbol",
        file_path="alpha.py",
        name="alpha",
        qualified_name="alpha",
        kind="function",
        complexity=3,
        churn=1,
    )
    graph.add_edge("file:alpha.py", "symbol:alpha.py:alpha", edge_type="contains")

    db_path = tmp_path / "test.db"
    timeline = GraphTimeline(db_path)
    timeline.record_snapshot(graph, label="baseline")
    timeline.close()
    return db_path


def test_envelope_helpers() -> None:
    assert ok({"count": 1}) == {"status": "ok", "data": {"count": 1}, "error": None}
    assert error("boom") == {"status": "error", "data": None, "error": "boom"}


def test_validate_config_rejects_non_localhost() -> None:
    config = ServerConfig(
        host="0.0.0.0",
        port=7331,
        db_path=Path("test.db"),
        timeout_seconds=30.0,
        log_level="INFO",
        transport="http",
    )
    with pytest.raises(ValueError, match="localhost-only"):
        validate_config(config)


def test_validate_config_allows_remote_http_with_opt_in() -> None:
    config = ServerConfig(
        host="0.0.0.0",
        port=7331,
        db_path=Path("test.db"),
        timeout_seconds=30.0,
        log_level="INFO",
        transport="http",
        allow_remote_http=True,
    )
    validate_config(config)


def test_validate_config_rejects_remote_stdio_even_with_opt_in() -> None:
    config = ServerConfig(
        host="0.0.0.0",
        port=7331,
        db_path=Path("test.db"),
        timeout_seconds=30.0,
        log_level="INFO",
        transport="stdio",
        allow_remote_http=True,
    )
    with pytest.raises(ValueError, match="localhost-only"):
        validate_config(config)


def test_graph_store_empty_db(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    store = GraphStore(db_path)
    store.open()
    summary = store.summary()
    assert summary.empty is True
    assert summary.node_count == 0
    assert store.get_dead_code() == []
    assert store.search_nodes("alpha") == []
    store.close()


def test_graph_store_queries(sample_db: Path) -> None:
    store = GraphStore(sample_db)
    store.open()
    try:
        summary = store.summary()
        assert summary.empty is False
        assert summary.node_count == 2

        node = store.get_node("file:alpha.py")
        assert node is not None
        assert node["file_path"] == "alpha.py"

        neighbors = store.get_neighbors("file:alpha.py", direction="out")
        assert len(neighbors["outgoing"]) == 1

        matches = store.search_nodes("alpha")
        assert len(matches) >= 1

        timeline = store.get_timeline()
        assert timeline["count"] == 1
    finally:
        store.close()


def test_graph_service_startup(sample_db: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    assert service.store.summary().node_count == 2
    service.shutdown()


def test_graph_service_get_timeline_from_worker_thread(sample_db: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    try:
        timeline = service.run(service.store.get_timeline)
        assert timeline["count"] == 1
    finally:
        service.shutdown()


def test_graph_service_refreshes_latest_snapshot_before_tool_reads(sample_db: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    try:
        updated_graph = create_graph("igraph")
        updated_graph.add_node(
            "file:alpha.py",
            node_type="file",
            file_path="alpha.py",
            churn=2,
            complexity=1,
        )
        updated_graph.add_node(
            "file:beta.py",
            node_type="file",
            file_path="beta.py",
            churn=1,
            complexity=1,
        )
        timeline = GraphTimeline(sample_db)
        try:
            latest_snapshot_id = timeline.record_snapshot(updated_graph, label="updated")
        finally:
            timeline.close()

        graph = service.run(service.store.get_graph)

        assert graph["snapshot_id"] == latest_snapshot_id
        assert graph["latest_snapshot_id"] == latest_snapshot_id
        assert graph["current"] is True
        assert graph["node_count"] == 2
    finally:
        service.shutdown()


def test_create_server_registers_tools(sample_db: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    server = create_server(service)
    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}
    expected = {
        "get_graph",
        "query_graph",
        "get_node",
        "get_neighbors",
        "get_changes",
        "get_timeline",
        "get_dead_code",
        "get_entry_points",
        "get_god_nodes",
        "get_circular_deps",
        "get_complexity",
        "get_churn",
        "search_nodes",
    }
    assert expected.issubset(tool_names)
    service.shutdown()


def test_parse_args_defaults() -> None:
    config = parse_args(["--db-path", "test.db"])
    assert config.port == 7331
    assert config.host == "127.0.0.1"
    assert config.transport == "http"


def test_parse_args_remote_http_opt_in() -> None:
    config = parse_args(
        [
            "--db-path",
            "test.db",
            "--transport",
            "http",
            "--host",
            "0.0.0.0",
            "--allow-remote-http",
            "--port",
            "8123",
        ]
    )
    assert config.transport == "http"
    assert config.host == "0.0.0.0"
    assert config.allow_remote_http is True
    assert config.port == 8123


def test_invalid_request_returns_error_envelope(sample_db: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    server = create_server(service)
    tools = asyncio.run(server.list_tools())
    tool = next(item for item in tools if item.name == "search_nodes")
    result = tool.fn(query="", node_type=None, limit=25)
    assert result["status"] == "error"
    service.shutdown()


def test_tool_call_records_activity(sample_db: Path) -> None:
    from codegenome.mcp_activity import McpActivityTracker

    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    tracker = McpActivityTracker()
    server = create_server(service, activity=tracker)
    tools = asyncio.run(server.list_tools())
    tool = next(item for item in tools if item.name == "search_nodes")
    result = tool.fn(query="alpha", node_type=None, limit=25)
    assert result["status"] == "ok"
    stats = tracker.stats()
    assert stats["total_calls"] == 1
    assert stats["last_tool"] == "search_nodes"
    service.shutdown()


def test_mcp_data_availability_for_ai(sample_db: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    try:
        server = create_server(service)
        tools = asyncio.run(server.list_tools())
        
        # Test get_neighbors
        get_neighbors = next(item for item in tools if item.name == "get_neighbors")
        result = get_neighbors.fn(node_id="file:alpha.py", direction="out")
        assert result["status"] == "ok"
        data = result["data"]
        assert "outgoing" in data
        assert len(data["outgoing"]) > 0
        assert len(data["outgoing"]) > 0

        # Test get_node
        get_node = next(item for item in tools if item.name == "get_node")
        result = get_node.fn(node_id="file:alpha.py")
        assert result["status"] == "ok"
        assert result["data"]["file_path"] == "alpha.py"

        # Test get_graph (returns summary)
        get_graph = next(item for item in tools if item.name == "get_graph")
        result = get_graph.fn()
        assert result["status"] == "ok"
        assert "node_count" in result["data"]
    finally:
        service.shutdown()
