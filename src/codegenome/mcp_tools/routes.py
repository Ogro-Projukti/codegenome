"""Custom HTTP routes (health and activity) for the MCP server."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from codegenome.genome_routes import register_genome_routes
from codegenome.mcp_activity import McpActivityTracker
from codegenome.version import __version__


def register_routes(mcp: Any, service: Any, tracker: McpActivityTracker) -> None:
    """Register the ``/health`` and ``/mcp/activity`` routes on the server.

    Args:
        mcp (Any): The FastMCP server instance.
        service (Any): The graph service backing the routes.
        tracker (McpActivityTracker): Activity tracker for stats and events.
    """

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        summary = service.run(service.store.summary)
        payload = {
            "status": "ok",
            "service": "codegenome-mcp",
            "version": __version__,
            "db_path": str(service.config.db_path),
            "snapshot_id": summary.snapshot_id,
            "latest_snapshot_id": summary.latest_snapshot_id,
            "current": summary.current,
            "node_count": summary.node_count,
            "edge_count": summary.edge_count,
            "empty": summary.empty,
            "memory_bounded": service.config.memory_bounded,
            "mcp_activity": tracker.combined_stats(),
        }
        return JSONResponse(payload)

    @mcp.custom_route("/mcp/activity", methods=["GET"], include_in_schema=False)
    async def activity_route(request: Request) -> JSONResponse:
        limit_raw = request.query_params.get("limit", "50")
        try:
            limit = max(1, min(int(limit_raw), tracker._max_events))
        except ValueError:
            limit = 50
        payload = {
            "status": "ok",
            "stats": tracker.combined_stats(),
            "events": tracker.recent(limit=limit),
        }
        return JSONResponse(payload)

    register_genome_routes(mcp, service)
