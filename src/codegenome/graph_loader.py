"""Helpers for file-scoped graph loading from timeline snapshots."""

from __future__ import annotations

from typing import Any


def node_file_path(node_id: str, attrs: dict[str, Any] | None = None) -> str | None:
    """Resolve the owning file path for a graph node."""
    data = attrs or {}
    file_path = data.get("file_path")
    if isinstance(file_path, str) and file_path:
        return file_path

    if node_id.startswith("file:"):
        return node_id[5:] or None

    if node_id.startswith("symbol:"):
        remainder = node_id[7:]
        if ":" in remainder:
            return remainder.split(":", 1)[0] or None

    if node_id.startswith("proxy:"):
        remainder = node_id[6:]
        if ":" in remainder:
            return remainder.split(":", 1)[0] or None

    if node_id.startswith("import:"):
        remainder = node_id[7:]
        if ":" in remainder:
            return remainder.split(":", 1)[0] or None

    return None


def node_belongs_to_file(node_id: str, attrs: dict[str, Any], file_path: str) -> bool:
    """Return True when a node is owned by the given file path."""
    owner = node_file_path(node_id, attrs)
    return owner == file_path
