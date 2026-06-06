"""Estimate MCP response size and tokens saved versus reading source files."""

from __future__ import annotations

import json
from typing import Any

CHARS_PER_TOKEN = 4
FALLBACK_FILE_TOKENS = 1500


def estimate_tokens(value: Any) -> int:
    """Estimate token count for a JSON-serializable value."""
    try:
        text = json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def extract_file_paths(value: Any) -> set[str]:
    """Collect unique file paths referenced in a tool result."""
    paths: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            file_path = obj.get("file_path")
            if isinstance(file_path, str) and file_path:
                paths.add(file_path)
            node_id = obj.get("node_id")
            if isinstance(node_id, str) and node_id.startswith("file:"):
                paths.add(node_id.removeprefix("file:"))
            for child in obj.values():
                walk(child)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(value)
    return paths


def _file_read_tokens(store: Any, file_path: str) -> int:
    node = store.get_node(f"file:{file_path}")
    if node is not None:
        size = node.get("size")
        if isinstance(size, (int, float)) and size > 0:
            return max(1, int(size) // CHARS_PER_TOKEN)
    return FALLBACK_FILE_TOKENS


def estimate_alternative_tokens(store: Any, result: Any) -> int:
    """Estimate tokens an agent would spend reading raw files for the same query."""
    file_paths = extract_file_paths(result)
    if file_paths:
        return sum(_file_read_tokens(store, path) for path in sorted(file_paths))

    if isinstance(result, list) and result:
        return len(result) * FALLBACK_FILE_TOKENS

    if isinstance(result, dict):
        for key in ("nodes", "results", "symbols", "files", "entries"):
            items = result.get(key)
            if isinstance(items, list) and items:
                return len(items) * FALLBACK_FILE_TOKENS
        count = result.get("count")
        if isinstance(count, int) and count > 0:
            return count * FALLBACK_FILE_TOKENS

    return 0


def estimate_token_savings(store: Any, result: Any) -> tuple[int, int]:
    """Return ``(response_tokens, tokens_saved)`` for a successful tool result."""
    response_tokens = estimate_tokens(result)
    alternative_tokens = estimate_alternative_tokens(store, result)
    tokens_saved = max(0, alternative_tokens - response_tokens)
    return response_tokens, tokens_saved
