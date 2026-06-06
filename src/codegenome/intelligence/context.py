"""Shared analysis context passed to the per-concern analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field

from codegenome.coupling_metrics import CouplingMetricsAnalyzer
from codegenome.graph_api import Graph
from codegenome.registry import GlobalDependencyRegistry
from codegenome.intelligence.classifier import NodeClassifier
from codegenome.intelligence.projections import FileGraphProjector


@dataclass
class AnalysisContext:
    """Bundle the graph plus shared helpers used by every analyzer."""

    graph: Graph
    registry: GlobalDependencyRegistry | None = None
    god_node_stddevs: float = 1.0
    classifier: NodeClassifier = field(default_factory=NodeClassifier)
    projector: FileGraphProjector = field(init=False)

    def __post_init__(self) -> None:
        self.projector = FileGraphProjector(self.graph, self.registry)

    def coupling_analyzer(self) -> CouplingMetricsAnalyzer:
        """Return a fresh coupling-metrics analyzer for the current graph."""
        return CouplingMetricsAnalyzer(self.graph)
