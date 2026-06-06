"""Tests for MCP token savings estimation."""

from __future__ import annotations

from codegenome.mcp_token_savings import (
    estimate_alternative_tokens,
    estimate_token_savings,
    estimate_tokens,
    extract_file_paths,
)


class _FakeStore:
    def __init__(self, sizes: dict[str, int]) -> None:
        self._sizes = sizes

    def get_node(self, node_id: str) -> dict[str, int] | None:
        path = node_id.removeprefix("file:")
        size = self._sizes.get(path)
        if size is None:
            return None
        return {"node_id": node_id, "file_path": path, "size": size}


def test_estimate_tokens_from_json_payload() -> None:
    payload = {"node_id": "file:alpha.py", "file_path": "alpha.py"}
    assert estimate_tokens(payload) == max(1, len('{"file_path": "alpha.py", "node_id": "file:alpha.py"}') // 4)


def test_extract_file_paths_from_nested_result() -> None:
    result = {
        "node_id": "file:alpha.py",
        "outgoing": [
            {
                "node_id": "symbol:beta.py:run",
                "node": {"file_path": "beta.py"},
            }
        ],
    }
    assert extract_file_paths(result) == {"alpha.py", "beta.py"}


def test_estimate_alternative_tokens_uses_file_sizes() -> None:
    store = _FakeStore({"alpha.py": 8000, "beta.py": 4000})
    result = [
        {"node_id": "symbol:alpha.py:alpha", "file_path": "alpha.py"},
        {"node_id": "symbol:beta.py:beta", "file_path": "beta.py"},
    ]
    assert estimate_alternative_tokens(store, result) == 3000


def test_estimate_token_savings_subtracts_response_tokens() -> None:
    store = _FakeStore({"alpha.py": 8000})
    result = {"node_id": "file:alpha.py", "file_path": "alpha.py", "name": "alpha"}
    response_tokens, tokens_saved = estimate_token_savings(store, result)
    assert response_tokens > 0
    assert tokens_saved == max(0, 2000 - response_tokens)
