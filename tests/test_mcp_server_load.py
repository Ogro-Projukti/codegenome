"""Load-oriented tests for MCP server tool handlers."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from codegenome.graph_api import create_graph
from codegenome.mcp_server import GraphService, ServerConfig, create_server
from codegenome.timeline import GraphTimeline


@pytest.fixture
def sample_db_for_load(tmp_path: Path) -> Path:
    graph = create_graph("igraph")
    for idx in range(40):
        file_id = f"file:mod_{idx}.py"
        symbol_id = f"symbol:mod_{idx}.py:fn_{idx}"
        graph.add_node(file_id, node_type="file", file_path=f"mod_{idx}.py")
        graph.add_node(
            symbol_id,
            node_type="symbol",
            file_path=f"mod_{idx}.py",
            name=f"fn_{idx}",
            qualified_name=f"fn_{idx}",
            kind="function",
        )
        graph.add_edge(file_id, symbol_id, edge_type="contains")

    db_path = tmp_path / "load.db"
    timeline = GraphTimeline(db_path)
    timeline.record_snapshot(graph, label="baseline")
    timeline.close()
    return db_path


def test_search_nodes_tool_sustains_repeated_calls(sample_db_for_load: Path) -> None:
    config = ServerConfig(
        host="127.0.0.1",
        port=7331,
        db_path=sample_db_for_load,
        timeout_seconds=5.0,
        log_level="INFO",
        transport="http",
    )
    service = GraphService(config)
    service.startup()
    try:
        server = create_server(service)
        tools = asyncio.run(server.list_tools())
        search_nodes = next(item for item in tools if item.name == "search_nodes")

        iterations = 300
        started = time.perf_counter()
        ok_count = 0
        for _ in range(iterations):
            result = search_nodes.fn(query="mod_", node_type=None, limit=25)
            assert result["status"] == "ok"
            assert result["data"]
            ok_count += 1
        elapsed = time.perf_counter() - started

        assert ok_count == iterations
        # Broad threshold to catch severe regressions while staying CI-friendly.
        assert elapsed < 20.0
    finally:
        service.shutdown()
