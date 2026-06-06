"""Graph build, incremental rebuild, and surgical update service."""

from __future__ import annotations

import logging
import os

from codegenome.exporter import GraphExporter
from codegenome.intelligence import GraphIntelligence, IntelligenceReport
from codegenome.registry import RegistryEntry
from codegenome.scanner import FileRecord, ScanResult

from codegenome.engine.context import EngineContext
from codegenome.engine.export_service import ExportService
from codegenome.engine.persistence_service import PersistenceService
from codegenome.engine.scan_service import ScanService
from codegenome.engine.types import BuildResult, ProgressCallback, make_emitter

LOG = logging.getLogger(__name__)


class BuildService:
    """Coordinate scanning, building, analysis, persistence, and export."""

    def __init__(
        self,
        ctx: EngineContext,
        scan_service: ScanService,
        persistence: PersistenceService,
        export_service: ExportService,
    ) -> None:
        self.ctx = ctx
        self._scan = scan_service
        self._persistence = persistence
        self._export = export_service

    def build(
        self,
        *,
        full: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> BuildResult:
        """Build or rebuild the graph from source files."""
        ctx = self.ctx
        emit = make_emitter(on_progress)

        if (
            not full
            and ctx.config.memory_bounded
            and ctx.working_set is not None
            and ctx.active_snapshot_id is not None
            and ctx.loaded_existing_graph
        ):
            return self._rebuild_incremental_bounded(on_progress=on_progress)

        incremental = not full and ctx.loaded_existing_graph
        emit("Scanning workspace...")
        scan = self._scan.scan(incremental=incremental, on_progress=on_progress)
        file_count = len(scan.files)
        change_summary = self._scan.change_summary(scan)
        emit(f"Scan complete: {file_count:,} files{change_summary}")

        parses = self._scan.parse_scan(scan, on_progress=on_progress)

        if incremental and ctx.builder.graph.number_of_nodes() > 0:
            emit("Updating graph...")
            graph, provides, consumes = ctx.builder.update(scan, parses)
            label = "incremental"
        else:
            emit("Building graph...")
            graph, provides, consumes = ctx.builder.build(scan, parses)
            label = "full"

        self._apply_registry_updates(graph, scan.deleted, provides, consumes)

        ctx.clusterer.annotate(graph)
        emit("Analyzing dependencies...")
        intelligence = GraphIntelligence(graph, registry=ctx.registry)
        intelligence.annotate_coupling_metrics()
        intel_report = intelligence.analyze()

        emit("Exporting graph...")
        exporter = GraphExporter(
            graph,
            report=intel_report,
            workspace_name=ctx.workspace.name,
        )

        snapshot_id = ctx.timeline.record_snapshot(graph, label=label)
        self._persistence.persist_gdr(snapshot_id)
        self._persistence.persist_snapshot_metrics(snapshot_id, graph, intel_report)
        ctx.active_snapshot_id = snapshot_id
        if ctx.config.memory_bounded:
            self._persistence.enter_memory_bounded_mode(snapshot_id)
        export_paths = self._export.run_exports(exporter)
        ctx.loaded_existing_graph = True

        return BuildResult(
            graph=graph,
            report=intel_report,
            snapshot_id=snapshot_id,
            export_paths=export_paths,
        )

    def surgical_update(
        self,
        abs_path: str,
        rel_path: str,
        event_type: str,
    ) -> BuildResult | None:
        """Perform a surgical update on the graph for a single file change."""
        ctx = self.ctx
        if not ctx.loaded_existing_graph:
            LOG.warning(
                "Cannot surgical update without existing graph. Rebuilding incremental..."
            )
            return self.build(full=False)

        files: list[FileRecord] = []
        added: set[str] = set()
        modified: set[str] = set()
        deleted: set[str] = set()
        parses: dict = {}

        if event_type == "deleted" or not os.path.exists(abs_path):
            deleted.add(rel_path)
        else:
            try:
                stat = os.stat(abs_path)
                record = FileRecord(
                    path=rel_path,
                    absolute_path=abs_path,
                    sha256="",
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
                files.append(record)
                if event_type == "created":
                    added.add(rel_path)
                else:
                    modified.add(rel_path)

                parsed = ctx.parser.parse_file(abs_path)
                if parsed is not None:
                    parses[rel_path] = parsed
            except OSError:
                deleted.add(rel_path)

        scan = ScanResult(
            root=str(ctx.workspace),
            files=files,
            added=added,
            modified=modified,
            deleted=deleted,
            unchanged=set(),
        )

        changed_files = set(added) | set(modified) | set(deleted)
        base_snapshot_id = self._resolve_base_snapshot_id()

        if (
            ctx.config.memory_bounded
            and ctx.working_set is not None
            and base_snapshot_id is not None
            and ctx.timeline.gdr_store.has_snapshot(base_snapshot_id)
        ):
            removed_fqns: set[str] = set()
            for path in changed_files:
                if path in deleted:
                    removed_fqns.update(
                        ctx.registry.files.get(path, RegistryEntry()).provides
                    )
            scope = ctx.timeline.gdr_store.resolve_change_scope(
                base_snapshot_id,
                changed_files=changed_files,
                removed_fqns=removed_fqns,
            )
            ctx.working_set.ensure_files(set(scope.all_files))
            self._persistence.ensure_registry_files(set(scope.all_files))
            ctx.builder.graph = ctx.working_set.graph

        graph, provides, consumes = ctx.builder.update(scan, parses)
        self._apply_registry_updates(graph, deleted, provides, consumes)

        use_bounded_patch = (
            ctx.config.memory_bounded
            and ctx.working_set is not None
            and base_snapshot_id is not None
        )
        if use_bounded_patch:
            snapshot_id = ctx.timeline.record_snapshot_patch(
                base_snapshot_id,
                changed_files,
                graph,
                label=f"surgical_{event_type}",
            )
            ctx.working_set.set_snapshot_id(snapshot_id)
            ctx.active_snapshot_id = snapshot_id
            analysis_graph = graph
        else:
            snapshot_id = ctx.timeline.record_snapshot(
                graph, label=f"surgical_{event_type}"
            )
            analysis_graph = graph

        self._persistence.persist_gdr(
            snapshot_id,
            base_snapshot_id=base_snapshot_id if use_bounded_patch else None,
            changed_files=changed_files if use_bounded_patch else None,
        )

        if use_bounded_patch:
            report = self._persistence.load_stored_report(snapshot_id) or IntelligenceReport()
            export_paths = self._export.run_exports_bounded(
                snapshot_id, analysis_graph, report
            )
            ctx.builder.graph = ctx.working_set.graph
            return BuildResult(
                graph=ctx.working_set.graph,
                report=report,
                snapshot_id=snapshot_id,
                export_paths=export_paths,
            )

        ctx.clusterer.annotate(analysis_graph)
        intelligence = GraphIntelligence(analysis_graph, registry=ctx.registry)
        intelligence.annotate_coupling_metrics()
        report = intelligence.analyze()

        exporter = GraphExporter(
            analysis_graph,
            report=report,
            workspace_name=ctx.workspace.name,
        )
        export_paths = self._export.run_exports(exporter)

        return BuildResult(
            graph=analysis_graph,
            report=report,
            snapshot_id=snapshot_id,
            export_paths=export_paths,
        )

    def _rebuild_incremental_bounded(
        self,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> BuildResult:
        """Incremental rebuild that patches SQLite and keeps the working set bounded."""
        ctx = self.ctx
        emit = make_emitter(on_progress)

        base_snapshot_id = self._resolve_base_snapshot_id()
        if base_snapshot_id is None or ctx.working_set is None:
            return self.build(full=True, on_progress=on_progress)

        emit("Scanning workspace...")
        scan = self._scan.scan(incremental=True, on_progress=on_progress)
        changed_files = set(scan.added) | set(scan.modified) | set(scan.deleted)
        if not changed_files:
            emit("No file changes detected.")
            return BuildResult(
                graph=ctx.working_set.graph,
                report=IntelligenceReport(),
                snapshot_id=base_snapshot_id,
                export_paths={},
            )

        emit(
            f"Scan complete: {len(changed_files):,} changed file(s); updating working set..."
        )
        parses = self._scan.parse_scan(scan, on_progress=on_progress)

        removed_fqns: set[str] = set()
        for path in changed_files:
            if path in scan.deleted:
                removed_fqns.update(
                    ctx.registry.files.get(path, RegistryEntry()).provides
                )

        if ctx.timeline.gdr_store.has_snapshot(base_snapshot_id):
            scope = ctx.timeline.gdr_store.resolve_change_scope(
                base_snapshot_id,
                changed_files=changed_files,
                removed_fqns=removed_fqns,
            )
            ctx.working_set.ensure_files(set(scope.all_files))
            self._persistence.ensure_registry_files(set(scope.all_files))
        ctx.builder.graph = ctx.working_set.graph

        graph, provides, consumes = ctx.builder.update(scan, parses)
        self._apply_registry_updates(graph, scan.deleted, provides, consumes)

        snapshot_id = ctx.timeline.record_snapshot_patch(
            base_snapshot_id,
            changed_files,
            graph,
            label="incremental_bounded",
        )
        ctx.working_set.set_snapshot_id(snapshot_id)
        ctx.active_snapshot_id = snapshot_id
        self._persistence.persist_gdr(
            snapshot_id,
            base_snapshot_id=base_snapshot_id,
            changed_files=changed_files,
        )

        intel_report = self._persistence.load_stored_report(snapshot_id) or IntelligenceReport()

        emit("Exporting graph...")
        export_paths = self._export.run_exports_bounded(snapshot_id, graph, intel_report)
        ctx.builder.graph = ctx.working_set.graph

        return BuildResult(
            graph=ctx.working_set.graph,
            report=intel_report,
            snapshot_id=snapshot_id,
            export_paths=export_paths,
        )

    def _resolve_base_snapshot_id(self) -> int | None:
        """Return the active snapshot id, falling back to the latest stored one."""
        ctx = self.ctx
        base_snapshot_id = ctx.active_snapshot_id
        if base_snapshot_id is None:
            snapshots = ctx.timeline.list_snapshots()
            base_snapshot_id = snapshots[-1].snapshot_id if snapshots else None
        return base_snapshot_id

    def _apply_registry_updates(
        self,
        graph,
        deleted,
        provides: dict[str, set[str]],
        consumes: dict[str, set[str]],
    ) -> None:
        """Update the registry for changed files and flag any broken proxies."""
        ctx = self.ctx
        deleted_fqns: set[str] = set()
        for deleted_path in deleted:
            deleted_fqns.update(ctx.registry.remove_file(deleted_path))

        for path, p_set in provides.items():
            deleted_fqns.update(
                ctx.registry.update_file(path, p_set, consumes.get(path, set()))
            )

        for fqn in deleted_fqns:
            for dep_path in ctx.registry.get_dependents(fqn):
                ctx.flag_broken_proxy(graph, dep_path, fqn)
