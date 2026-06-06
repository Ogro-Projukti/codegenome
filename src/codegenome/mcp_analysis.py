"""Analysis-source selection for the MCP graph store.

Encapsulates the decision of *where* architectural analysis comes from:
precomputed per-snapshot metrics (memory-bounded mode) versus live
:class:`GraphIntelligence` computation over the loaded/full graph. This keeps
``GraphStore`` focused on MCP query orchestration and result formatting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codegenome.graph_api import Graph
from codegenome.intelligence import GraphIntelligence
from codegenome.snapshot_metrics import SnapshotMetrics

if TYPE_CHECKING:
    from codegenome.graph_store import GraphStore


class McpAnalysisProvider:
    """Resolve architectural analysis from stored metrics or live intelligence."""

    def __init__(self, store: "GraphStore") -> None:
        self._store = store

    @property
    def use_stored_metrics(self) -> bool:
        """True when analysis must come from precomputed snapshot metrics."""
        store = self._store
        return store._memory_bounded and not store._full_analysis_on_demand

    def stored_report(self):
        """Return the precomputed intelligence report (bounded mode)."""
        return self.require_bounded_metrics().report

    def require_bounded_metrics(self) -> SnapshotMetrics:
        """Return precomputed snapshot metrics or raise a helpful error."""
        from codegenome.graph_store import GraphStoreError

        metrics = self._store._load_stored_metrics()
        if metrics is None:
            raise GraphStoreError(
                "No precomputed global metrics for this snapshot. "
                "Run a full `codegenome analyze` build first, or restart MCP with "
                "--full-analysis-on-demand."
            )
        return metrics

    def require_intelligence(self) -> GraphIntelligence:
        """Return a GraphIntelligence over the loaded or full graph."""
        from codegenome.graph_store import GraphStoreError

        store = self._store
        if store._memory_bounded and not store._full_analysis_on_demand:
            raise GraphStoreError(
                "Global graph analysis is disabled in memory-bounded MCP mode. "
                "Use get_node, get_neighbors, query_graph, or search_nodes for local queries, "
                "or restart the MCP server with --full-analysis-on-demand."
            )
        if store._memory_bounded and store._full_analysis_on_demand:
            return GraphIntelligence(store._load_full_graph())
        if store._intelligence is None:
            raise GraphStoreError("Intelligence engine is not initialized")
        return store._intelligence

    def betweenness_graph(self) -> Graph:
        """Return the graph to compute betweenness over (full when bounded)."""
        store = self._store
        return store._load_full_graph() if store._memory_bounded else store._graph
