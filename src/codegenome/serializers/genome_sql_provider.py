"""SQL-backed projections for memory-bounded genome REST responses."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codegenome.builder import file_node_id
from codegenome.serializers.genome_provider import GenomeProvider, module_id_for_file
from codegenome.serializers.genome_schemas import (
    GenomeSummaryResponse,
    HelixGraphResponse,
    ModuleSummary,
    StructureTreeResponse,
)
from codegenome.serializers.health_aggregator import (
    HealthAggregator,
    weighted_health_score,
)

if TYPE_CHECKING:
    from codegenome.timeline import GraphTimeline


@dataclass
class _FileProjection:
    """Small per-file aggregate retained while projecting a snapshot."""

    community_id: int | None = None
    total_symbols: int = 0
    dead_symbols: int = 0
    complexity_sum: float = 0.0
    complexity_count: int = 0
    base_counts: dict[str, int] = field(
        default_factory=lambda: {"A": 0, "A*": 0, "T": 0, "G": 0, "C": 0}
    )


class SqlGenomeProvider:
    """Build genome payloads from SQLite without loading a complete graph.

    The overview is projected to one compact aggregate per source file. Module
    details load only the requested module's subgraph, whose size is bounded by
    the response itself rather than by the repository's complete snapshot.
    """

    def __init__(self, timeline: GraphTimeline, snapshot_id: int) -> None:
        self.timeline = timeline
        self.snapshot_id = snapshot_id
        metrics = timeline.metrics_store.load_snapshot(snapshot_id)
        self._report = metrics.report if metrics is not None else None
        self._cyclic_files = (
            {
                str(file_id)
                for cycle in self._report.circular_dependencies
                for file_id in cycle
            }
            if self._report is not None
            else set()
        )

    def build_summary(self, *, snapshot_id: int | None = None) -> GenomeSummaryResponse:
        """Return module aggregates using streaming SQL projections."""
        files = self._project_files()
        modules: dict[str, list[tuple[str, _FileProjection]]] = defaultdict(list)
        for file_path, projection in files.items():
            modules[module_id_for_file(file_path)].append((file_path, projection))

        summaries: list[ModuleSummary] = []
        for module_id in sorted(modules):
            members = modules[module_id]
            base_counts = {"A": 0, "A*": 0, "T": 0, "G": 0, "C": 0}
            community_votes: Counter[int] = Counter()
            health_scores: list[float] = []
            for file_path, projection in members:
                for base, count in projection.base_counts.items():
                    base_counts[base] += count
                if projection.community_id is not None:
                    community_votes[projection.community_id] += 1
                health_scores.append(self._health_score(file_path, projection))

            summaries.append(
                ModuleSummary(
                    module_id=module_id,
                    gene_count=len(members),
                    health_score=round(sum(health_scores) / len(health_scores), 4),
                    coverage_available=False,
                    community_id=(community_votes.most_common(1)[0][0] if community_votes else None),
                    base_counts=base_counts,
                )
            )
        return GenomeSummaryResponse(
            modules=summaries,
            snapshot_id=self.snapshot_id if snapshot_id is None else snapshot_id,
        )

    def build_helix_graph(self, module_id: str) -> HelixGraphResponse | None:
        """Build one module's helix from an SQL-selected graph slice."""
        provider = self._module_provider(module_id)
        return provider.build_helix_graph(module_id) if provider is not None else None

    def build_structure_tree(self, module_id: str) -> StructureTreeResponse | None:
        """Build one module's structure tree from an SQL-selected graph slice."""
        provider = self._module_provider(module_id)
        return provider.build_structure_tree(module_id) if provider is not None else None

    def _module_provider(self, module_id: str) -> GenomeProvider | None:
        file_paths = self.timeline.file_paths_for_module(self.snapshot_id, module_id)
        if not file_paths:
            return None
        graph = self.timeline.load_file_subgraph(self.snapshot_id, file_paths)
        return GenomeProvider(graph, intelligence_report=self._report)

    def _project_files(self) -> dict[str, _FileProjection]:
        connection = self.timeline.connection
        projections: dict[str, _FileProjection] = {}
        file_rows = connection.execute(
            """
            SELECT node_id, attrs_json
            FROM graph_nodes
            WHERE snapshot_id = ? AND node_id LIKE 'file:%'
            ORDER BY node_id
            """,
            (self.snapshot_id,),
        )
        for row in file_rows:
            attrs = json.loads(row["attrs_json"])
            if attrs.get("node_type") != "file" or not attrs.get("file_path"):
                continue
            community_id = attrs.get("community_id")
            projections[str(attrs["file_path"])] = _FileProjection(
                community_id=int(community_id) if community_id is not None else None
            )

        dead_symbols = set(self._report.dead_code) if self._report is not None else set()
        symbol_rows = connection.execute(
            """
            SELECT node_id, attrs_json
            FROM graph_nodes
            WHERE snapshot_id = ? AND node_id LIKE 'symbol:%'
            ORDER BY node_id
            """,
            (self.snapshot_id,),
        )
        for row in symbol_rows:
            attrs = json.loads(row["attrs_json"])
            file_path = str(attrs.get("file_path") or "")
            projection = projections.get(file_path)
            if projection is None or attrs.get("node_type") != "symbol":
                continue
            projection.total_symbols += 1
            if row["node_id"] in dead_symbols:
                projection.dead_symbols += 1
            complexity = attrs.get("complexity")
            if isinstance(complexity, (int, float)):
                projection.complexity_sum += float(complexity)
                projection.complexity_count += 1
            kind = str(attrs.get("kind") or "")
            if kind in {"function", "method"}:
                projection.base_counts["A"] += 1
            elif kind in {"abstract_class", "interface"}:
                projection.base_counts["A*"] += 1
            elif kind == "class":
                projection.base_counts["T"] += 1

        edge_rows = connection.execute(
            """
            SELECT source.attrs_json AS source_attrs_json,
                   edge.attrs_json AS edge_attrs_json
            FROM graph_edges AS edge
            JOIN graph_nodes AS source
              ON source.snapshot_id = edge.snapshot_id
             AND source.node_id = edge.source_id
            WHERE edge.snapshot_id = ?
            ORDER BY edge.source_id, edge.target_id, edge.edge_key
            """,
            (self.snapshot_id,),
        )
        for row in edge_rows:
            source_attrs = json.loads(row["source_attrs_json"])
            projection = projections.get(str(source_attrs.get("file_path") or ""))
            if projection is None:
                continue
            edge_type = json.loads(row["edge_attrs_json"]).get("edge_type")
            if edge_type == "imports":
                projection.base_counts["G"] += 1
            elif edge_type == "calls":
                projection.base_counts["C"] += 1
        return projections

    def _health_score(self, file_path: str, projection: _FileProjection) -> float:
        circular_factor = 0.0 if file_node_id(file_path) in self._cyclic_files else 1.0
        zombie_rate = (
            projection.dead_symbols / projection.total_symbols
            if projection.total_symbols
            else 0.0
        )
        if projection.complexity_count:
            average_complexity = projection.complexity_sum / projection.complexity_count
            complexity_factor = max(
                0.0,
                1.0 - min(average_complexity / HealthAggregator.MAX_COMPLEXITY, 1.0),
            )
        else:
            complexity_factor = 1.0
        return weighted_health_score(
            coverage=None,
            circular_factor=circular_factor,
            zombie_factor=1.0 - zombie_rate,
            complexity_factor=complexity_factor,
        )
