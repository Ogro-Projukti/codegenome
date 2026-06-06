"""Registration of CodeGenome graph query tools on the FastMCP server."""

from __future__ import annotations

from typing import Any, Callable, Literal

from codegenome.graph_store import GraphStoreError


def register_graph_tools(
    mcp: Any,
    service: Any,
    guarded_tool: Callable[[Callable[..., Any]], Callable[..., Any]],
) -> None:
    """Register all graph query tools, wrapping each with ``guarded_tool``.

    Args:
        mcp (Any): The FastMCP server instance.
        service (Any): The graph service exposing the underlying store.
        guarded_tool (Callable): Decorator that adds timing, activity, and
            error-envelope handling to each tool.
    """

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
    def get_betweenness_centrality(
        limit: int = 25,
        include_generated: bool = False,
    ) -> dict[str, Any]:
        """Return file nodes ranked by betweenness centrality."""
        return service.store.get_betweenness_centrality(
            limit=limit,
            include_generated=include_generated,
        )

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
    def get_coupling_metrics(
        limit: int = 25,
        include_generated: bool = False,
        min_cbo: int | None = None,
    ) -> dict[str, Any]:
        """Return CBO/LCOM coupling metrics and tightly coupled classes."""
        return service.store.get_coupling_metrics(
            limit=limit,
            include_generated=include_generated,
            min_cbo=min_cbo,
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
