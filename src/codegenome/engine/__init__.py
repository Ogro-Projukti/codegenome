"""Engine service layer for CodeGenome.

This package decomposes the former monolithic ``CodeGenomeEngine`` into a set of
focused, single-responsibility services that share an :class:`EngineContext`:

- :class:`~codegenome.engine.scan_service.ScanService` - workspace scan + parse
- :class:`~codegenome.engine.build_service.BuildService` - graph build/update
- :class:`~codegenome.engine.persistence_service.PersistenceService` - snapshots, GDR, metrics
- :class:`~codegenome.engine.export_service.ExportService` - artifact exports
- :class:`~codegenome.engine.watch_service.WatchService` - filesystem watchers
- :class:`~codegenome.engine.mcp_process.McpProcessManager` - MCP subprocess lifecycle
"""

from codegenome.engine.types import (
    BuildResult,
    CodeGenomeConfig,
    DEFAULT_EXPORT_FORMATS,
    PARSE_PROGRESS_INTERVAL,
    ProgressCallback,
)
from codegenome.engine.context import EngineContext
from codegenome.engine.scan_service import ScanService
from codegenome.engine.persistence_service import PersistenceService
from codegenome.engine.export_service import ExportService
from codegenome.engine.build_service import BuildService
from codegenome.engine.watch_service import (
    SurgicalUpdateHandler,
    WatchService,
    _RebuildHandler,
)
from codegenome.engine.mcp_process import McpProcessManager

__all__ = [
    "BuildResult",
    "CodeGenomeConfig",
    "DEFAULT_EXPORT_FORMATS",
    "PARSE_PROGRESS_INTERVAL",
    "ProgressCallback",
    "EngineContext",
    "ScanService",
    "PersistenceService",
    "ExportService",
    "BuildService",
    "WatchService",
    "SurgicalUpdateHandler",
    "_RebuildHandler",
    "McpProcessManager",
]
