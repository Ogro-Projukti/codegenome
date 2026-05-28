"""Resolve bundled static assets for development and PyInstaller builds."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PACKAGE_ROOT = Path(__file__).resolve().parent


def bundle_root() -> Path:
    """Return the root directory for bundled assets and templates."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return PACKAGE_ROOT


def asset_path(*parts: str) -> Path:
    """Resolve a path under the bundled assets directory."""
    return bundle_root() / "assets" / Path(*parts)


def template_dir() -> Path:
    """Return the bundled Jinja2 templates directory."""
    return bundle_root() / "templates"


def scaffold_template_dir() -> Path:
    """Return bundled project scaffold templates."""
    return template_dir() / "scaffold"


@lru_cache(maxsize=1)
def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir())),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        keep_trailing_newline=True,
    )


def render_template(name: str, **context: object) -> str:
    """Render a bundled Jinja2 template."""
    return jinja_env().get_template(name).render(**context)


def html_asset(name: str) -> Path:
    """Return the path to a bundled HTML asset such as vis-network.min.js."""
    return asset_path("html", name)


def copy_html_asset(name: str, destination: Path) -> Path | None:
    """Copy a bundled HTML asset next to an export file, if present."""
    source = html_asset(name)
    if not source.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    return destination
