"""REST route handlers for progressive-disclosure genome endpoints."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from starlette.requests import Request
from starlette.responses import JSONResponse

from codegenome.serializers.genome_provider import GenomeProvider


def _decode_module_id(raw: str) -> str:
    return unquote(raw).replace("\\", "/")


def _json_response(payload: Any, *, status: int = 200) -> JSONResponse:
    if hasattr(payload, "model_dump"):
        body = payload.model_dump(mode="json")
    else:
        body = payload
    return JSONResponse(body, status_code=status)


def handle_genome_get(graph: Any, *, snapshot_id: int | None = None) -> JSONResponse:
    """Serve GET /genome."""
    provider = GenomeProvider(graph)
    return _json_response(provider.build_summary(snapshot_id=snapshot_id))


def handle_genome_graph_get(
    graph: Any,
    module_id: str,
) -> JSONResponse:
    """Serve GET /genome/{module_id}/graph."""
    decoded = _decode_module_id(module_id)
    provider = GenomeProvider(graph)
    payload = provider.build_helix_graph(decoded)
    if payload is None:
        return JSONResponse({"error": f"Unknown module: {decoded}"}, status_code=404)
    return _json_response(payload)


def handle_genome_structure_get(
    graph: Any,
    module_id: str,
) -> JSONResponse:
    """Serve GET /genome/{module_id}/structure."""
    decoded = _decode_module_id(module_id)
    provider = GenomeProvider(graph)
    payload = provider.build_structure_tree(decoded)
    if payload is None:
        return JSONResponse({"error": f"Unknown module: {decoded}"}, status_code=404)
    return _json_response(payload)


def register_genome_routes(mcp: Any, service: Any) -> None:
    """Register genome REST routes on a FastMCP server."""

    def _graph_for_request() -> Any:
        return service.run(service.store.graph_for_genome)

    @mcp.custom_route("/genome", methods=["GET"], include_in_schema=False)
    async def genome_summary(_request: Request) -> JSONResponse:
        graph = _graph_for_request()
        snapshot_id = service.store.snapshot_id
        return handle_genome_get(graph, snapshot_id=snapshot_id)

    @mcp.custom_route("/genome/{module_id}/graph", methods=["GET"], include_in_schema=False)
    async def genome_graph(_request: Request) -> JSONResponse:
        module_id = _request.path_params["module_id"]
        graph = _graph_for_request()
        return handle_genome_graph_get(graph, module_id)

    @mcp.custom_route("/genome/{module_id}/structure", methods=["GET"], include_in_schema=False)
    async def genome_structure(_request: Request) -> JSONResponse:
        module_id = _request.path_params["module_id"]
        graph = _graph_for_request()
        return handle_genome_structure_get(graph, module_id)
