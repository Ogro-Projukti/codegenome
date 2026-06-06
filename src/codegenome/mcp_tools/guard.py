"""Guard decorator wrapping MCP tools with timing, activity, and error handling."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable, TypeVar

from codegenome.graph_store import GraphStoreError
from codegenome.mcp_activity import McpActivityTracker, summarize_args
from codegenome.mcp_token_savings import estimate_token_savings
from codegenome.mcp_runtime import (
    MCP_CLIENT_CONTEXT,
    MCP_TRANSPORT_CONTEXT,
    LOG,
    error,
    log_event,
    ok,
)

F = TypeVar("F", bound=Callable[..., Any])


def build_guarded_tool(service: Any, tracker: McpActivityTracker) -> Callable[[F], F]:
    """Build the ``guarded_tool`` decorator bound to a service and tracker.

    The returned decorator runs the wrapped tool inside the service thread pool,
    records activity, emits structured logs, and converts results/exceptions into
    the standard ``{status, data, error}`` envelope.

    Args:
        service (Any): The graph service that executes tool callables.
        tracker (McpActivityTracker): Activity tracker for tool usage.

    Returns:
        Callable[[F], F]: A decorator for MCP tool functions.
    """

    def guarded_tool(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            tool_name = fn.__name__
            client = MCP_CLIENT_CONTEXT.get()
            if client == "unknown" and MCP_TRANSPORT_CONTEXT.get() == "stdio":
                client = "stdio"
            args_summary = summarize_args(dict(kwargs))
            started = time.perf_counter()

            try:
                result = service.run(fn, *args, **kwargs)
                duration_ms = (time.perf_counter() - started) * 1000
                response_tokens, tokens_saved = estimate_token_savings(service.store, result)
                event = tracker.record(
                    tool=tool_name,
                    client=client,
                    args=args_summary,
                    status="ok",
                    duration_ms=duration_ms,
                    response_tokens=response_tokens,
                    tokens_saved=tokens_saved,
                )
                log_event(
                    logging.INFO,
                    "tool_call",
                    tool=event.tool,
                    client=event.client,
                    args=event.args,
                    status=event.status,
                    duration_ms=event.duration_ms,
                    response_tokens=event.response_tokens,
                    tokens_saved=event.tokens_saved,
                )
                return ok(result)
            except ValueError as exc:
                duration_ms = (time.perf_counter() - started) * 1000
                tracker.record(
                    tool=tool_name,
                    client=client,
                    args=args_summary,
                    status="error",
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                log_event(
                    logging.WARNING,
                    "tool_call",
                    tool=tool_name,
                    client=client,
                    args=args_summary,
                    status="error",
                    duration_ms=round(duration_ms, 2),
                    error=str(exc),
                )
                return error(str(exc))
            except GraphStoreError as exc:
                duration_ms = (time.perf_counter() - started) * 1000
                tracker.record(
                    tool=tool_name,
                    client=client,
                    args=args_summary,
                    status="error",
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                log_event(logging.ERROR, "graph_store_error", tool=tool_name, error=str(exc))
                return error(str(exc))
            except TimeoutError as exc:
                duration_ms = (time.perf_counter() - started) * 1000
                tracker.record(
                    tool=tool_name,
                    client=client,
                    args=args_summary,
                    status="error",
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                log_event(logging.ERROR, "timeout", tool=tool_name, error=str(exc))
                return error(str(exc))
            except Exception as exc:  # noqa: BLE001 - surface safe MCP errors
                duration_ms = (time.perf_counter() - started) * 1000
                tracker.record(
                    tool=tool_name,
                    client=client,
                    args=args_summary,
                    status="error",
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                log_event(logging.ERROR, "unexpected_error", tool=tool_name, error=str(exc))
                LOG.exception("unexpected_error")
                return error(f"Internal server error: {exc}")

        return wrapper  # type: ignore[return-value]

    return guarded_tool
