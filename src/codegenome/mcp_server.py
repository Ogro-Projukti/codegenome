"""FastMCP server exposing Watcher graph tools over localhost HTTP or stdio."""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from fastmcp import FastMCP
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from starlette.requests import Request
from starlette.responses import JSONResponse

from codegenome.graph_store import GraphStore, GraphStoreError
from codegenome.mcp_activity import McpActivityTracker, summarize_args
from codegenome.version import __version__

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7331
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_TRANSPORT: Literal["http", "stdio"] = "http"

ENV_HOST = "WATCHER_MCP_HOST"
ENV_PORT = "WATCHER_MCP_PORT"
ENV_DB_PATH = "WATCHER_MCP_DB_PATH"
ENV_TIMEOUT = "WATCHER_MCP_TIMEOUT"
ENV_LOG_LEVEL = "WATCHER_MCP_LOG_LEVEL"
ENV_TRANSPORT = "WATCHER_MCP_TRANSPORT"

F = TypeVar("F", bound=Callable[..., Any])

LOG = logging.getLogger("codegenome.mcp_server")

MCP_CLIENT_CONTEXT: ContextVar[str] = ContextVar("mcp_client", default="unknown")
MCP_TRANSPORT_CONTEXT: ContextVar[str] = ContextVar("mcp_transport", default="http")
MCP_SESSION_CLIENTS: dict[str, str] = {}


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"level": logging.getLevelName(level), "event": event, **fields}
    LOG.log(level, json.dumps(payload, sort_keys=True))


@dataclass(frozen=True)
class ServerConfig:
    """Configuration for the MCP server."""

    host: str
    port: int
    db_path: Path
    timeout_seconds: float
    log_level: str
    transport: Literal["http", "stdio"]
    allow_remote_http: bool = False


def configure_logging(level: str) -> None:
    """Configure basic logging for the MCP server.

    Args:
        level (str): The logging level to set (e.g., 'INFO', 'DEBUG').
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stderr,
        force=True,
    )


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


def parse_args(argv: list[str] | None = None) -> ServerConfig:
    """Parse command line arguments into a ServerConfig.

    Args:
        argv (list[str] | None, optional): Command line arguments. Defaults to None (uses sys.argv).

    Returns:
        ServerConfig: The parsed configuration.
    """
    parser = argparse.ArgumentParser(description="CodeGenome MCP graph server")
    parser.add_argument(
        "--db-path",
        default=os.getenv(ENV_DB_PATH, "test.db"),
        help="Path to the CodeGenome timeline SQLite database",
    )
    parser.add_argument(
        "--host",
        default=os.getenv(ENV_HOST, DEFAULT_HOST),
        help="Bind host (localhost only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv(ENV_PORT, str(DEFAULT_PORT))),
        help="Bind port for HTTP transport",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv(ENV_TIMEOUT, str(DEFAULT_TIMEOUT_SECONDS))),
        help="Tool execution timeout in seconds",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv(ENV_LOG_LEVEL, "INFO"),
        help="Python logging level",
    )
    parser.add_argument(
        "--transport",
        choices=("http", "stdio"),
        default=os.getenv(ENV_TRANSPORT, DEFAULT_TRANSPORT),
        help="MCP transport protocol",
    )
    parser.add_argument(
        "--allow-remote-http",
        action="store_true",
        help="Allow HTTP transport to bind non-loopback addresses.",
    )
    args = parser.parse_args(argv)
    return ServerConfig(
        host=args.host,
        port=args.port,
        db_path=Path(args.db_path).resolve(),
        timeout_seconds=args.timeout,
        log_level=args.log_level,
        transport=args.transport,
        allow_remote_http=args.allow_remote_http,
    )


def validate_config(config: ServerConfig) -> None:
    """Validate the provided server configuration.

    Args:
        config (ServerConfig): The configuration to validate.

    Raises:
        ValueError: If host, port, or timeout_seconds is invalid.
    """
    try:
        host = ipaddress.ip_address(config.host)
    except ValueError as exc:
        raise ValueError(f"Invalid host address: {config.host}") from exc

    if not host.is_loopback and not (
        config.transport == "http" and config.allow_remote_http
    ):
        raise ValueError(
            f"CodeGenome MCP server is localhost-only; refusing to bind to {config.host}"
        )

    if config.port <= 0 or config.port > 65535:
        raise ValueError(f"Invalid port: {config.port}")

    if config.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")


class GraphService:
    """Thread-safe wrapper around GraphStore for MCP tool handlers."""

    def __init__(self, config: ServerConfig) -> None:
        """Initialize the GraphService.

        Args:
            config (ServerConfig): The server configuration.
        """
        self.config = config
        self._lock = threading.RLock()
        self._store = GraphStore(config.db_path)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="watcher-mcp")

    @property
    def store(self) -> GraphStore:
        return self._store

    def startup(self) -> None:
        """Open the underlying store and log startup details."""
        with self._lock:
            self._store.open()
        summary = self._store.summary()
        LOG.info(
            json.dumps(
                {
                    "level": "INFO",
                    "event": "graph_loaded",
                    "db_path": str(self.config.db_path),
                    "snapshot_id": summary.snapshot_id,
                    "node_count": summary.node_count,
                    "edge_count": summary.edge_count,
                    "empty": summary.empty,
                },
                sort_keys=True,
            )
        )

    def shutdown(self) -> None:
        """Close the underlying store and shut down the thread pool."""
        with self._lock:
            self._store.close()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _invoke(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            self._store.refresh_latest()
            return fn(*args, **kwargs)

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run a callable within the thread pool executor.

        Args:
            fn (Callable[..., Any]): The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            Any: The result of the function call.

        Raises:
            TimeoutError: If execution exceeds the configured timeout.
        """
        future = self._executor.submit(self._invoke, fn, *args, **kwargs)
        try:
            return future.result(timeout=self.config.timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"Operation timed out after {self.config.timeout_seconds} seconds"
            ) from exc


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


def create_server(
    service: GraphService,
    *,
    activity: McpActivityTracker | None = None,
) -> FastMCP:
    """Create and configure the FastMCP server with graph tools.

    Args:
        service (GraphService): The graph service handling tool execution.
        activity (McpActivityTracker | None, optional): Tracker for tool usage. Defaults to None.

    Returns:
        FastMCP: The configured MCP server instance.
    """
    tracker = activity or McpActivityTracker()

    mcp = FastMCP(
        name="CodeGenome Graph",
        instructions=(
            "Query the CodeGenome codebase knowledge graph. "
            "For architecture, dependency, symbol, dead-code, or entry-point questions, "
            "prefer CodeGenome MCP tools over reading raw files or grep. "
            "All tool responses use a JSON envelope with status, data, and error fields."
        ),
    )
    mcp.add_middleware(ClientContextMiddleware())

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
                event = tracker.record(
                    tool=tool_name,
                    client=client,
                    args=args_summary,
                    status="ok",
                    duration_ms=duration_ms,
                )
                log_event(
                    logging.INFO,
                    "tool_call",
                    tool=event.tool,
                    client=event.client,
                    args=event.args,
                    status=event.status,
                    duration_ms=event.duration_ms,
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

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        summary = service.run(service.store.summary)
        payload = {
            "status": "ok",
            "service": "watcher-mcp",
            "version": __version__,
            "db_path": str(service.config.db_path),
            "snapshot_id": summary.snapshot_id,
            "latest_snapshot_id": summary.latest_snapshot_id,
            "current": summary.current,
            "node_count": summary.node_count,
            "edge_count": summary.edge_count,
            "empty": summary.empty,
            "mcp_activity": tracker.stats(),
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
            "stats": tracker.stats(),
            "events": tracker.recent(limit=limit),
        }
        return JSONResponse(payload)

    @mcp.tool
    @guarded_tool
    def get_graph(
        include_nodes: bool = False,
        include_edges: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return graph summary and optional node/edge payloads."""
        return service.store.get_graph(
            include_nodes=include_nodes,
            include_edges=include_edges,
            limit=limit,
        )

    @mcp.tool
    @guarded_tool
    def query_graph(
        node_type: str | None = None,
        file_path: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Filter graph nodes by type, file path prefix, or symbol kind."""
        return service.store.query_graph(
            node_type=node_type,
            file_path=file_path,
            kind=kind,
            limit=limit,
        )

    @mcp.tool
    @guarded_tool
    def get_node(node_id: str) -> dict[str, Any]:
        """Return a single node by id."""
        node = service.store.get_node(node_id)
        if node is None:
            raise GraphStoreError(f"Node not found: {node_id}")
        return node

    @mcp.tool
    @guarded_tool
    def get_neighbors(
        node_id: str,
        direction: Literal["in", "out", "both"] = "both",
    ) -> dict[str, Any]:
        """Return incoming and/or outgoing neighbors for a node."""
        return service.store.get_neighbors(node_id, direction=direction)

    @mcp.tool
    @guarded_tool
    def get_changes(snapshot_from: int, snapshot_to: int) -> dict[str, Any]:
        """Compute structural changes between two timeline snapshots."""
        return service.store.get_changes(snapshot_from, snapshot_to)

    @mcp.tool
    @guarded_tool
    def get_timeline(node_id: str | None = None) -> dict[str, Any]:
        """List stored snapshots and optional node history."""
        return service.store.get_timeline(node_id=node_id)

    @mcp.tool
    @guarded_tool
    def get_dead_code(
        include_generated: bool = False,
        include_public_api: bool = False,
    ) -> dict[str, Any]:
        """Detect likely dead code symbols."""
        return service.store.get_dead_code(
            include_generated=include_generated,
            include_public_api=include_public_api,
        )

    @mcp.tool
    @guarded_tool
    def get_entry_points() -> dict[str, Any]:
        """Detect graph entry points."""
        return service.store.get_entry_points()

    @mcp.tool
    @guarded_tool
    def get_god_nodes(include_generated: bool = False) -> dict[str, Any]:
        """Return highly connected god nodes."""
        return service.store.get_god_nodes(include_generated=include_generated)

    @mcp.tool
    @guarded_tool
    def get_circular_deps() -> dict[str, Any]:
        """Return circular file import dependencies."""
        return service.store.get_circular_deps()

    @mcp.tool
    @guarded_tool
    def get_complexity(
        limit: int = 25,
        include_generated: bool = False,
    ) -> dict[str, Any]:
        """Return top complexity-ranked symbols."""
        return service.store.get_complexity(
            limit=limit,
            include_generated=include_generated,
        )

    @mcp.tool
    @guarded_tool
    def get_churn(
        file_path: str | None = None,
        snapshot_from: int | None = None,
        snapshot_to: int | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Return churn rankings or a file churn rate across snapshots."""
        return service.store.get_churn(
            file_path=file_path,
            snapshot_from=snapshot_from,
            snapshot_to=snapshot_to,
            limit=limit,
        )

    @mcp.tool
    @guarded_tool
    def search_nodes(
        query: str,
        node_type: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search nodes by id, name, qualified name, or file path."""
        return service.store.search_nodes(query, node_type=node_type, limit=limit)

    return mcp


def main(argv: list[str] | None = None) -> int:
    """Entry point for the MCP server.

    Args:
        argv (list[str] | None, optional): Command line arguments. Defaults to None.

    Returns:
        int: Process exit code.
    """
    try:
        config = parse_args(argv)
        validate_config(config)
    except ValueError as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1

    configure_logging(config.log_level)
    log_event(
        logging.INFO,
        "starting",
        host=config.host,
        port=config.port,
        transport=config.transport,
        db_path=str(config.db_path),
    )

    service = GraphService(config)
    try:
        service.startup()
    except GraphStoreError as exc:
        log_event(logging.ERROR, "startup_failed", error=str(exc))
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1

    server = create_server(service)
    transport_token = MCP_TRANSPORT_CONTEXT.set(config.transport)
    try:
        if config.transport == "stdio":
            MCP_CLIENT_CONTEXT.set("stdio")
            server.run(transport="stdio", show_banner=False)
        else:
            server.run(
                transport="http",
                host=config.host,
                port=config.port,
                show_banner=False,
            )
    except KeyboardInterrupt:
        log_event(logging.INFO, "shutdown", reason="keyboard_interrupt")
        return 0
    except OSError as exc:
        log_event(logging.ERROR, "startup_failed", error=str(exc))
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        MCP_TRANSPORT_CONTEXT.reset(transport_token)
        service.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
