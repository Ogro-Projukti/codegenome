"""Initialization module for the codegenome package.

This module exposes the main components of the codebase knowledge graph builder,
including parsers, scanners, graph building, intelligence, and exporters.
"""

from .builder import GraphBuilder
from .clusterer import ClusterResult, GraphClusterer
from .exporter import GraphExporter, GraphStatistics, SUPPORTED_FORMATS
from .intelligence import GraphIntelligence, IntelligenceReport
from .parser import ParseResult, SourceParser
from .scanner import ScanResult, WorkspaceScanner
from .gdr_store import ChangeScope, GDRFileEntry, GDRStore
from .timeline import GraphDelta, GraphTimeline, SnapshotInfo
from .version import __version__
from .core import BuildResult, CodeGenomeConfig, CodeGenomeEngine

__all__ = [
    "__version__",
    "BuildResult",
    "ClusterResult",
    "GraphBuilder",
    "GraphClusterer",
    "ChangeScope",
    "GDRFileEntry",
    "GDRStore",
    "GraphDelta",
    "GraphExporter",
    "GraphIntelligence",
    "GraphStatistics",
    "GraphTimeline",
    "IntelligenceReport",
    "ParseResult",
    "ScanResult",
    "SnapshotInfo",
    "SourceParser",
    "SUPPORTED_FORMATS",
    "CodeGenomeConfig",
    "CodeGenomeEngine",
    "WorkspaceScanner",
]
