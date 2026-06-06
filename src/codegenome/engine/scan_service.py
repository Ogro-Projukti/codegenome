"""Workspace scanning and source parsing service."""

from __future__ import annotations

from codegenome.scanner import ScanResult

from codegenome.engine.context import EngineContext
from codegenome.engine.types import (
    PARSE_PROGRESS_INTERVAL,
    ProgressCallback,
    make_emitter,
)


class ScanService:
    """Scan the workspace and parse changed source files."""

    def __init__(self, ctx: EngineContext) -> None:
        self.ctx = ctx

    def scan(
        self,
        *,
        incremental: bool,
        on_progress: ProgressCallback | None = None,
    ) -> ScanResult:
        """Scan the workspace, reporting human-readable progress."""
        emit = make_emitter(on_progress)
        return self.ctx.scanner.scan(
            incremental=incremental,
            on_progress=lambda count: emit(f"Scanning... {count:,} files"),
        )

    @staticmethod
    def change_summary(scan: ScanResult) -> str:
        """Build a parenthesized summary of added/modified/deleted counts."""
        change_parts: list[str] = []
        if scan.added:
            change_parts.append(f"{len(scan.added):,} added")
        if scan.modified:
            change_parts.append(f"{len(scan.modified):,} modified")
        if scan.deleted:
            change_parts.append(f"{len(scan.deleted):,} deleted")
        return f" ({', '.join(change_parts)})" if change_parts else ""

    def parse_scan(
        self,
        scan: ScanResult,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> dict:
        """Parse every non-deleted file in the scan into a ParseResult map."""
        parses: dict = {}
        total = len(scan.files)
        if on_progress is not None:
            on_progress(f"Parsing 0 / {total:,} files...")

        for index, record in enumerate(scan.files, start=1):
            rel_path = record.path
            if scan.deleted and rel_path in scan.deleted:
                continue
            parsed = self.ctx.parser.parse_file(record.absolute_path)
            if parsed is not None:
                parses[rel_path] = parsed
            if on_progress is not None and (
                index == 1
                or index == total
                or index % PARSE_PROGRESS_INTERVAL == 0
            ):
                on_progress(f"Parsing {index:,} / {total:,} files...")
        return parses
