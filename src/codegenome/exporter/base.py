"""Protocol shared by all format-specific writers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from codegenome.exporter.context import ExportContext


@runtime_checkable
class FormatWriter(Protocol):
    """Serialize an :class:`ExportContext` to a single output location."""

    def write(self, ctx: ExportContext, output_path: Path) -> Path:
        """Write the export and return the path that was produced."""
        ...
