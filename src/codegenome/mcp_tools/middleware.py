"""FastMCP middleware capturing client identity for activity logging."""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext

from codegenome.mcp_runtime import (
    MCP_CLIENT_CONTEXT,
    MCP_SESSION_CLIENTS,
    MCP_TRANSPORT_CONTEXT,
)


class ClientContextMiddleware(Middleware):
    """Capture MCP client identity for activity logging."""

    async def on_initialize(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        client_name = extract_client_name(context)
        response = await call_next(context)
        session_id = (
            context.fastmcp_context.session_id if context.fastmcp_context else None
        )
        if session_id and client_name != "unknown":
            MCP_SESSION_CLIENTS[session_id] = client_name
        return response

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        token = MCP_CLIENT_CONTEXT.set(resolve_mcp_client(context))
        try:
            return await call_next(context)
        finally:
            MCP_CLIENT_CONTEXT.reset(token)


def extract_client_name(context: MiddlewareContext[Any]) -> str:
    """Extract the client name from the MCP request context.

    Args:
        context (MiddlewareContext[Any]): The request context.

    Returns:
        str: The extracted client name, or 'unknown' if unavailable.
    """
    message = context.message
    params = getattr(message, "params", None)
    if params is None:
        return "unknown"

    client_info = getattr(params, "clientInfo", None)
    if client_info is None and isinstance(params, dict):
        client_info = params.get("clientInfo")
    if client_info is None:
        return "unknown"

    name = getattr(client_info, "name", None)
    if name is None and isinstance(client_info, dict):
        name = client_info.get("name")
    return str(name) if name else "unknown"


def resolve_mcp_client(context: MiddlewareContext[Any]) -> str:
    """Resolve a unified client identifier based on the MCP context.

    Args:
        context (MiddlewareContext[Any]): The request context.

    Returns:
        str: The resolved client identifier.
    """
    fastmcp_context = context.fastmcp_context
    if fastmcp_context is None:
        return "stdio" if MCP_TRANSPORT_CONTEXT.get() == "stdio" else "unknown"

    session_id = fastmcp_context.session_id
    if session_id and session_id in MCP_SESSION_CLIENTS:
        return MCP_SESSION_CLIENTS[session_id]

    client_id = fastmcp_context.client_id
    if client_id:
        return client_id

    if session_id:
        return f"session:{session_id[:12]}"

    return "unknown"
