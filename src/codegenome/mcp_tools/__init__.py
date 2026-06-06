"""MCP tool registration: guard decorator, middleware, routes, and graph tools."""

from __future__ import annotations

from codegenome.mcp_tools.guard import build_guarded_tool
from codegenome.mcp_tools.middleware import (
    ClientContextMiddleware,
    extract_client_name,
    resolve_mcp_client,
)
from codegenome.mcp_tools.routes import register_routes
from codegenome.mcp_tools.graph_tools import register_graph_tools

__all__ = [
    "build_guarded_tool",
    "ClientContextMiddleware",
    "extract_client_name",
    "resolve_mcp_client",
    "register_routes",
    "register_graph_tools",
]
