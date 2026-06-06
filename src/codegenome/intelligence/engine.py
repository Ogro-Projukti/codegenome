"""GraphIntelligence facade composing the per-concern analyzers."""

from __future__ import annotations

from codegenome.graph_api import Graph
from codegenome.registry import GlobalDependencyRegistry
from codegenome.intelligence.classifier import NodeClassifier
from codegenome.intelligence.context import AnalysisContext
from codegenome.intelligence.coupling import CouplingAnalyzer
from codegenome.intelligence.rankings import GodNodeAnalyzer, RankingAnalyzer
from codegenome.intelligence.report import IntelligenceReport
from codegenome.intelligence.structural import (
    CircularDependencyAnalyzer,
    DeadCodeAnalyzer,
    EntryPointAnalyzer,
    OrphanModuleAnalyzer,
)


class GraphIntelligence:
    """Derive actionable architectural signals from a CodeGenome graph.

    This is a thin facade that delegates each analysis to a focused analyzer
    (dead code, cycles, god nodes, entry points, orphans, rankings, coupling),
    all sharing a single :class:`AnalysisContext`.
    """

    # Backward-compatible class-level constants (now owned by NodeClassifier).
    ENTRY_SYMBOL_NAMES = NodeClassifier.ENTRY_SYMBOL_NAMES
    ENTRY_FILE_NAMES = NodeClassifier.ENTRY_FILE_NAMES
    GENERATED_PATH_PARTS = NodeClassifier.GENERATED_PATH_PARTS
    GENERATED_FILE_SUFFIXES = NodeClassifier.GENERATED_FILE_SUFFIXES

    def __init__(
        self,
        graph: Graph,
        *,
        registry: GlobalDependencyRegistry | None = None,
        god_node_stddevs: float = 1.0,
    ) -> None:
        """Initialize the GraphIntelligence analyzer.

        Args:
            graph (Graph): The dependency graph to analyze.
            registry (GlobalDependencyRegistry | None): Optional global dependency registry.
            god_node_stddevs (float): Number of standard deviations above the mean
                to use as the threshold for detecting god nodes. Defaults to 1.0.
        """
        self.graph = graph
        self.registry = registry
        self.god_node_stddevs = god_node_stddevs
        self._ctx = AnalysisContext(
            graph=graph,
            registry=registry,
            god_node_stddevs=god_node_stddevs,
        )
        self._dead_code = DeadCodeAnalyzer(self._ctx)
        self._circular = CircularDependencyAnalyzer(self._ctx)
        self._god_nodes = GodNodeAnalyzer(self._ctx)
        self._entry_points = EntryPointAnalyzer(self._ctx)
        self._orphans = OrphanModuleAnalyzer(self._ctx)
        self._rankings = RankingAnalyzer(self._ctx)
        self._coupling = CouplingAnalyzer(self._ctx)

    def analyze(self) -> IntelligenceReport:
        """Run all architectural analyses and aggregate the results."""
        return IntelligenceReport(
            dead_code=self.detect_dead_code(),
            circular_dependencies=self.detect_circular_dependencies(),
            god_nodes=self.detect_god_nodes(),
            entry_points=self.detect_entry_points(),
            orphan_modules=self.detect_orphan_modules(),
            complexity_rankings=self.complexity_rankings(),
            churn_rankings=self.churn_rankings(),
            cbo_rankings=self.cbo_rankings(),
            lcom_rankings=self.lcom_rankings(),
            tightly_coupled_classes=self.tightly_coupled_classes(),
        )

    def detect_dead_code(
        self,
        *,
        include_generated: bool = False,
        include_public_api: bool = False,
    ) -> list[str]:
        """Detect functions and methods that are never called."""
        return self._dead_code.detect(
            include_generated=include_generated,
            include_public_api=include_public_api,
        )

    def detect_circular_dependencies(self) -> list[list[str]]:
        """Identify circular import dependencies between files."""
        return self._circular.detect()

    def detect_god_nodes(
        self,
        *,
        include_generated: bool = False,
    ) -> list[tuple[str, float]]:
        """Identify nodes with excessively high degrees (god nodes)."""
        return self._god_nodes.detect(include_generated=include_generated)

    def detect_entry_points(self) -> list[str]:
        """Detect file and symbol nodes that serve as application entry points."""
        return self._entry_points.detect()

    def detect_orphan_modules(self) -> list[str]:
        """Identify files that have no incoming or outgoing dependencies."""
        return self._orphans.detect()

    def complexity_rankings(
        self,
        *,
        include_generated: bool = False,
    ) -> list[tuple[str, int]]:
        """Rank symbols based on their cyclomatic complexity."""
        return self._rankings.complexity_rankings(include_generated=include_generated)

    def churn_rankings(self) -> list[tuple[str, int]]:
        """Rank nodes based on their churn rate (how often they change)."""
        return self._rankings.churn_rankings()

    def cbo_rankings(self, *, include_generated: bool = False) -> list[tuple[str, int]]:
        """Rank classes by descending coupling between objects (CBO)."""
        return self._coupling.cbo_rankings(include_generated=include_generated)

    def lcom_rankings(self, *, include_generated: bool = False) -> list[tuple[str, int]]:
        """Rank classes by descending lack of cohesion in methods (LCOM)."""
        return self._coupling.lcom_rankings(include_generated=include_generated)

    def tightly_coupled_classes(
        self,
        *,
        include_generated: bool = False,
        min_cbo: int = 5,
    ) -> list[tuple[str, int]]:
        """Return classes with CBO at or above ``min_cbo``."""
        return self._coupling.tightly_coupled_classes(
            include_generated=include_generated,
            min_cbo=min_cbo,
        )

    def coupling_metrics(
        self,
        *,
        include_generated: bool = False,
    ) -> list[dict[str, object]]:
        """Return per-class CBO and LCOM metrics."""
        return self._coupling.coupling_metrics(include_generated=include_generated)

    def annotate_coupling_metrics(self) -> None:
        """Write computed CBO/LCOM values onto class symbol nodes."""
        self._coupling.annotate_coupling_metrics()
