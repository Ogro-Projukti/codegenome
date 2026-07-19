"""FastMCP server exposing CodeGenome graph tools over localhost HTTP or stdio."""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from fastmcp import FastMCP

from codegenome.graph_store import GraphStore, GraphStoreError
from codegenome.mcp_activity import McpActivityStore, McpActivityTracker
from codegenome.mcp_runtime import (
    LOG,
    MCP_CLIENT_CONTEXT,
    MCP_TRANSPORT_CONTEXT,
    error as error,
    log_event,
    ok as ok,
)
from codegenome.mcp_tools import (
    ClientContextMiddleware,
    build_guarded_tool,
    register_graph_tools,
    register_routes,
)
from codegenome.network_utils import LOOPBACK_HOST

DEFAULT_HOST = LOOPBACK_HOST
DEFAULT_PORT = 7331
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_TRANSPORT: Literal["http", "stdio"] = "http"

ENV_HOST = "CODEGENOME_MCP_HOST"
ENV_PORT = "CODEGENOME_MCP_PORT"
ENV_DB_PATH = "CODEGENOME_MCP_DB_PATH"
ENV_TIMEOUT = "CODEGENOME_MCP_TIMEOUT"
ENV_LOG_LEVEL = "CODEGENOME_MCP_LOG_LEVEL"
ENV_TRANSPORT = "CODEGENOME_MCP_TRANSPORT"
ENV_MEMORY_BOUNDED = "CODEGENOME_MCP_MEMORY_BOUNDED"
ENV_MAX_QUERY_NODES = "CODEGENOME_MCP_MAX_QUERY_NODES"
ENV_NEIGHBORHOOD_DEPTH = "CODEGENOME_MCP_NEIGHBORHOOD_DEPTH"
ENV_FULL_ANALYSIS_ON_DEMAND = "CODEGENOME_MCP_FULL_ANALYSIS_ON_DEMAND"


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
    memory_bounded: bool = False
    max_query_nodes: int = 500
    neighborhood_depth: int = 1
    full_analysis_on_demand: bool = False


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
    parser.add_argument(
        "--memory-bounded",
        action="store_true",
        default=os.getenv(ENV_MEMORY_BOUNDED, "").lower() in {"1", "true", "yes"},
        help="Load query subgraphs on demand instead of keeping the full graph in memory.",
    )
    parser.add_argument(
        "--max-query-nodes",
        type=int,
        default=int(os.getenv(ENV_MAX_QUERY_NODES, "500")),
        help="Maximum nodes loaded for bounded neighborhood queries.",
    )
    parser.add_argument(
        "--neighborhood-depth",
        type=int,
        default=int(os.getenv(ENV_NEIGHBORHOOD_DEPTH, "1")),
        help="BFS depth for bounded get_neighbors queries.",
    )
    parser.add_argument(
        "--full-analysis-on-demand",
        action="store_true",
        default=os.getenv(ENV_FULL_ANALYSIS_ON_DEMAND, "").lower() in {"1", "true", "yes"},
        help="Allow global analysis tools to temporarily load the full graph in bounded mode.",
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
        memory_bounded=args.memory_bounded,
        max_query_nodes=max(1, args.max_query_nodes),
        neighborhood_depth=max(0, args.neighborhood_depth),
        full_analysis_on_demand=args.full_analysis_on_demand,
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
        self._store = GraphStore(
            config.db_path,
            memory_bounded=config.memory_bounded,
            max_query_nodes=config.max_query_nodes,
            neighborhood_depth=config.neighborhood_depth,
            full_analysis_on_demand=config.full_analysis_on_demand,
        )
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="codegenome-mcp")

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
    tracker = activity or McpActivityTracker(store=McpActivityStore(service.config.db_path))

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

    guarded_tool = build_guarded_tool(service, tracker)
    register_routes(mcp, service, tracker)
    register_graph_tools(mcp, service, guarded_tool)
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
