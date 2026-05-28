import importlib

import pytest

PACKAGES = [
    "tree_sitter",
    "watchdog",
    "fastmcp",
    "leidenalg",
    "igraph",
    "jinja2",
]


@pytest.mark.parametrize("pkg", PACKAGES)
def test_third_party_import(pkg: str) -> None:
    importlib.import_module(pkg)


def test_codegenome_import() -> None:
    import codegenome

    assert codegenome.__version__ == "0.1.0"
