"""Unified module health scoring and circular-import alerting."""

from __future__ import annotations

from dataclasses import dataclass

import igraph as ig
import networkx as nx
from pydantic import BaseModel, Field

from codegenome.builder import file_node_id
from codegenome.graph_api import Graph
from codegenome.intelligence.projections import FileGraphProjector
from codegenome.intelligence.structural import CircularDependencyAnalyzer, DeadCodeAnalyzer
from codegenome.intelligence.context import AnalysisContext
from codegenome.parser.types import ParsedCall, ParsedSymbol
from codegenome.serializers.nucleotide_mapper import (
    BiologicalSequence,
    GraphEdgeInput,
    map_nucleotide_sequence,
)


class ModuleHealthReport(BaseModel):
    """Health audit for a single module (source file)."""

    module_path: str
    health_score: float = Field(ge=0.0, le=1.0)
    alerts: list[str] = Field(default_factory=list)
    test_coverage: float = Field(ge=0.0, le=1.0)
    circular_dep_rate: float = Field(ge=0.0, le=1.0)
    zombie_node_rate: float = Field(ge=0.0, le=1.0)
    normalized_complexity: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class HealthWeights:
    """Relative weights for the four health factors (must sum to 1)."""

    coverage: float = 0.25
    circular: float = 0.25
    zombie: float = 0.25
    complexity: float = 0.25


class HealthAggregator:
    """Compute per-module health scores and circular-import (G!) alerts."""

    DEFAULT_COVERAGE = 0.85
    MAX_COMPLEXITY = 50.0

    def __init__(
        self,
        graph: Graph,
        *,
        test_coverage: dict[str, float] | None = None,
        weights: HealthWeights | None = None,
    ) -> None:
        self.graph = graph
        self.test_coverage = test_coverage or {}
        self.weights = weights or HealthWeights()
        self._ctx = AnalysisContext(graph)
        self._files_in_cycles: set[str] | None = None
        self._dead_symbol_ids: set[str] | None = None

    def files_in_cycles(self) -> set[str]:
        """Return file node IDs participating in circular import cycles."""
        if self._files_in_cycles is not None:
            return self._files_in_cycles

        file_graph = FileGraphProjector(self.graph).file_import_graph()
        if file_graph.number_of_nodes() == 0:
            self._files_in_cycles = set()
            return self._files_in_cycles

        cycles = self._detect_cycles_igraph(file_graph)
        if cycles:
            self._files_in_cycles = {file_id for cycle in cycles for file_id in cycle}
            return self._files_in_cycles

        analyzer = CircularDependencyAnalyzer(self._ctx)
        nx_cycles = analyzer.detect()
        self._files_in_cycles = {file_id for cycle in nx_cycles for file_id in cycle}
        return self._files_in_cycles

    def circular_import_targets(self) -> set[str]:
        """Return import node IDs that should render as G! (circular import)."""
        cyclic_files = self.files_in_cycles()
        if not cyclic_files:
            return set()

        targets: set[str] = set()
        for source, target, attrs in self.graph.iter_edges():
            if attrs.get("edge_type") != "imports":
                continue
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            file_path = source_attrs.get("file_path")
            if file_path and file_node_id(str(file_path)) in cyclic_files:
                targets.add(target)
        return targets

    def dead_symbol_ids(self) -> set[str]:
        """Return symbol node IDs classified as dead code (zombie nodes)."""
        if self._dead_symbol_ids is not None:
            return self._dead_symbol_ids
        analyzer = DeadCodeAnalyzer(self._ctx)
        self._dead_symbol_ids = set(analyzer.detect())
        return self._dead_symbol_ids

    def compute_module_health(self, module_path: str) -> ModuleHealthReport:
        """Compute a 0.0–1.0 health score and alert list for one module."""
        file_id = file_node_id(module_path)
        alerts: list[str] = []

        coverage = self._coverage_for(module_path)
        circular_rate = 1.0 if file_id in self.files_in_cycles() else 0.0
        if circular_rate > 0:
            alerts.append("circular_import")

        symbol_nodes = self._symbols_for_module(module_path)
        total_symbols = len(symbol_nodes)
        dead_in_module = sum(1 for node_id in symbol_nodes if node_id in self.dead_symbol_ids())
        zombie_rate = dead_in_module / total_symbols if total_symbols else 0.0
        if zombie_rate > 0:
            alerts.append("zombie_nodes")

        complexity_score = self._normalized_complexity(symbol_nodes)
        if complexity_score < 0.5:
            alerts.append("high_complexity")

        circular_factor = 1.0 - circular_rate
        zombie_factor = 1.0 - zombie_rate
        w = self.weights
        health_score = (
            w.coverage * coverage
            + w.circular * circular_factor
            + w.zombie * zombie_factor
            + w.complexity * complexity_score
        )
        health_score = max(0.0, min(1.0, health_score))

        return ModuleHealthReport(
            module_path=module_path,
            health_score=round(health_score, 4),
            alerts=alerts,
            test_coverage=round(coverage, 4),
            circular_dep_rate=round(circular_rate, 4),
            zombie_node_rate=round(zombie_rate, 4),
            normalized_complexity=round(complexity_score, 4),
        )

    def build_sequence(
        self,
        module_path: str,
        symbols: list[ParsedSymbol],
        edges: list[GraphEdgeInput | tuple[str, str, dict]],
        calls: list[ParsedCall],
        *,
        import_node_attrs: dict[str, dict] | None = None,
    ) -> BiologicalSequence:
        """Map nucleotides and attach module health score, alerts, and G! flags."""
        circular_targets = self.circular_import_targets()
        health = self.compute_module_health(module_path)
        sequence = map_nucleotide_sequence(
            symbols,
            edges,
            calls,
            import_node_attrs=import_node_attrs,
            circular_import_targets=circular_targets,
        )
        return sequence.model_copy(
            update={
                "health_score": health.health_score,
                "alerts": list(health.alerts),
            }
        )

    def _coverage_for(self, module_path: str) -> float:
        if module_path in self.test_coverage:
            return max(0.0, min(1.0, self.test_coverage[module_path]))
        return self.DEFAULT_COVERAGE

    def _symbols_for_module(self, module_path: str) -> list[str]:
        return [
            node_id
            for node_id, attrs in self.graph.iter_nodes()
            if attrs.get("node_type") == "symbol" and attrs.get("file_path") == module_path
        ]

    def _normalized_complexity(self, symbol_node_ids: list[str]) -> float:
        if not symbol_node_ids:
            return 1.0
        values: list[int] = []
        for node_id in symbol_node_ids:
            attrs = self.graph.get_node(node_id)
            complexity = attrs.get("complexity")
            if complexity is not None:
                values.append(int(complexity))
        if not values:
            return 1.0
        average = sum(values) / len(values)
        return max(0.0, 1.0 - min(average / self.MAX_COMPLEXITY, 1.0))

    @staticmethod
    def _detect_cycles_igraph(file_graph: nx.DiGraph) -> list[list[str]]:
        """Detect circular import cycles using igraph strongly-connected components."""
        if file_graph.number_of_nodes() == 0:
            return []

        nodes = list(file_graph.nodes())
        index = {name: idx for idx, name in enumerate(nodes)}
        edges = [(index[source], index[target]) for source, target in file_graph.edges()]

        ig_graph = ig.Graph(n=len(nodes), edges=edges, directed=True)
        ig_graph.vs["name"] = nodes

        cycles: list[list[str]] = []
        for component in ig_graph.components(mode="strong"):
            if len(component) < 2:
                continue
            member_names = [nodes[idx] for idx in component]
            cycles.append(member_names)
        cycles.sort(key=lambda cycle: (len(cycle), cycle))
        return cycles
