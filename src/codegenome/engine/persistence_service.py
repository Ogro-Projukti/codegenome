"""Snapshot, registry (GDR), and metrics persistence service."""

from __future__ import annotations

from codegenome.gdr_store import GDRBackedRegistry
from codegenome.intelligence import IntelligenceReport
from codegenome.snapshot_metrics import SnapshotMetrics
from codegenome.timeline import SnapshotRetentionResult
from codegenome.working_set import WorkingSetGraph

from codegenome.engine.context import EngineContext


class PersistenceService:
    """Persist and restore snapshots, the dependency registry, and metrics."""

    def __init__(self, ctx: EngineContext) -> None:
        self.ctx = ctx

    def load_existing_graph(self) -> bool:
        """Load the latest snapshot (or bounded working set) on startup."""
        ctx = self.ctx
        snapshots = ctx.timeline.list_snapshots()
        if not snapshots:
            return False
        latest = snapshots[-1]
        ctx.active_snapshot_id = latest.snapshot_id
        self.load_existing_registry(latest.snapshot_id)
        if ctx.config.memory_bounded:
            self.enter_memory_bounded_mode(latest.snapshot_id)
            return latest.node_count > 0
        ctx.builder.graph = ctx.timeline.load_snapshot(latest.snapshot_id)
        return ctx.builder.graph.number_of_nodes() > 0

    def enter_memory_bounded_mode(self, snapshot_id: int) -> None:
        """Switch the engine to a bounded working set for the given snapshot."""
        ctx = self.ctx
        ctx.working_set = WorkingSetGraph(
            ctx.timeline,
            snapshot_id,
            max_files=ctx.config.max_working_files,
        )
        ctx.working_set.evict_all()
        ctx.builder.graph = ctx.working_set.graph

    def load_existing_registry(self, snapshot_id: int) -> None:
        """Hydrate or back the dependency registry from a stored snapshot."""
        ctx = self.ctx
        if not ctx.timeline.gdr_store.has_snapshot(snapshot_id):
            return
        if ctx.config.memory_bounded:
            ctx.registry = ctx.timeline.gdr_store.create_backed_registry(snapshot_id)
        else:
            ctx.registry = ctx.timeline.gdr_store.hydrate_registry(snapshot_id)

    def ensure_registry_files(self, file_paths: set[str]) -> None:
        """Ensure a GDR-backed registry has loaded the given files."""
        if isinstance(self.ctx.registry, GDRBackedRegistry):
            self.ctx.registry.ensure_files(file_paths)

    def load_stored_report(self, snapshot_id: int) -> IntelligenceReport | None:
        """Return the precomputed intelligence report for a snapshot, if any."""
        metrics = self.ctx.timeline.metrics_store.load_snapshot(snapshot_id)
        return metrics.report if metrics is not None else None

    def persist_snapshot_metrics(
        self,
        snapshot_id: int,
        graph: object,
        report: IntelligenceReport,
    ) -> None:
        """Compute and persist global metrics (e.g. betweenness) for a snapshot."""
        betweenness = tuple(
            self.ctx.clusterer.betweenness_rankings(graph, include_generated=False)
        )
        self.ctx.timeline.metrics_store.persist_snapshot(
            snapshot_id,
            SnapshotMetrics(report=report, betweenness_rankings=betweenness),
        )

    def persist_gdr(
        self,
        snapshot_id: int | None,
        *,
        base_snapshot_id: int | None = None,
        changed_files: set[str] | None = None,
    ) -> None:
        """Persist the dependency registry, patching from a base when possible."""
        if snapshot_id is None:
            return
        gdr_store = self.ctx.timeline.gdr_store
        if (
            base_snapshot_id is not None
            and changed_files is not None
            and gdr_store.has_snapshot(base_snapshot_id)
        ):
            gdr_store.persist_snapshot_patch(
                base_snapshot_id,
                snapshot_id,
                changed_files,
                self.ctx.registry,
            )
            return
        gdr_store.persist_snapshot(snapshot_id, self.ctx.registry)

    def enforce_snapshot_retention(self) -> SnapshotRetentionResult | None:
        """Apply configured count/age limits after a snapshot is fully persisted."""
        config = self.ctx.config
        max_count = config.snapshot_retention_count
        max_age_seconds = (
            config.snapshot_retention_days * 24 * 60 * 60
            if config.snapshot_retention_days is not None
            else None
        )
        if max_count is None and max_age_seconds is None:
            return None
        return self.ctx.timeline.prune_snapshots(
            max_snapshots=max_count,
            max_age_seconds=max_age_seconds,
            protected_snapshot_ids=(
                {self.ctx.active_snapshot_id}
                if self.ctx.active_snapshot_id is not None
                else None
            ),
        )
