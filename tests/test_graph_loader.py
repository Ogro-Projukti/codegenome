"""Tests for file-scoped graph loading helpers."""

from __future__ import annotations

from codegenome.builder import file_node_id, symbol_node_id
from codegenome.graph_loader import node_file_path


def test_node_file_path_from_ids() -> None:
    assert node_file_path(file_node_id("alpha.py")) == "alpha.py"
    assert node_file_path(symbol_node_id("alpha.py", "run")) == "alpha.py"
    assert node_file_path("proxy:alpha.py:helper") == "alpha.py"
    assert node_file_path("import:alpha.py:1:os") == "alpha.py"


def test_node_file_path_prefers_attrs() -> None:
    assert node_file_path("custom:id", {"file_path": "alpha.py"}) == "alpha.py"
