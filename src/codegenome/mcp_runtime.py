"""Shared MCP server primitives: response envelopes, logging, and contexts.

Kept dependency-free so both :mod:`codegenome.mcp_server` and the
:mod:`codegenome.mcp_tools` package can import these without a cycle.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

LOG = logging.getLogger("codegenome.mcp_server")

MCP_CLIENT_CONTEXT: ContextVar[str] = ContextVar("mcp_client", default="unknown")
MCP_TRANSPORT_CONTEXT: ContextVar[str] = ContextVar("mcp_transport", default="http")
MCP_SESSION_CLIENTS: dict[str, str] = {}


def log_event(level: int, event: str, **fields: Any) -> None:
    """Emit a structured JSON log line for an MCP server event."""
    payload = {"level": logging.getLevelName(level), "event": event, **fields}
    LOG.log(level, json.dumps(payload, sort_keys=True))


def ok(data: Any) -> dict[str, Any]:
    """Wrap data in a success response dictionary.

    Args:
        data (Any): The payload data to wrap.

    Returns:
        dict[str, Any]: A structured response indicating success.
    """
    return {"status": "ok", "data": data, "error": None}


def error(message: str, *, data: Any = None) -> dict[str, Any]:
    """Wrap a message in an error response dictionary.

    Args:
        message (str): The error message.
        data (Any, optional): Optional additional context data. Defaults to None.

    Returns:
        dict[str, Any]: A structured response indicating an error.
    """
    return {"status": "error", "data": data, "error": message}
