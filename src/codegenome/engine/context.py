"""Shared mutable state for the engine service layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codegenome.builder import GraphBuilder
from codegenome.clusterer import GraphClusterer
from codegenome.parser import SourceParser
from codegenome.registry import GlobalDependencyRegistry
from codegenome.scanner import WorkspaceScanner
from codegenome.timeline import GraphTimeline
from codegenome.working_set import WorkingSetGraph

from codegenome.engine.types import CodeGenomeConfig


@dataclass
class EngineContext:
    """Holds the resolved configuration, components, and runtime state.

    A single context instance is shared across all engine services so they can
    cooperate without each service re-deriving paths or re-instantiating
    components. Runtime fields (``working_set``, ``active_snapshot_id``,
    ``loaded_existing_graph``, ``registry``) are mutated as builds progress.
    """

    config: CodeGenomeConfig
    workspace: Path
    genome_dir: Path
    db_path: Path
    export_dir: Path
    graph_json_path: Path
    scanner: WorkspaceScanner
    parser: SourceParser
    builder: GraphBuilder
    clusterer: GraphClusterer
    timeline: GraphTimeline
    registry: GlobalDependencyRegistry
    working_set: WorkingSetGraph | None = None
    active_snapshot_id: int | None = None
    loaded_existing_graph: bool = False

    @classmethod
    def create(cls, config: CodeGenomeConfig) -> "EngineContext":
        """Resolve paths, create directories, and instantiate components."""
        workspace = config.workspace.resolve()
        genome_dir = workspace / ".genome"
        db_path = (config.db_path or genome_dir / "codegenome.db").resolve()
        export_dir = (config.export_dir or genome_dir / "exports").resolve()
        graph_json_path = (
            config.graph_json_path or genome_dir / "graph.json"
        ).resolve()

        genome_dir.mkdir(parents=True, exist_ok=True)
        export_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            config=config,
            workspace=workspace,
            genome_dir=genome_dir,
            db_path=db_path,
            export_dir=export_dir,
            graph_json_path=graph_json_path,
            scanner=WorkspaceScanner(
                workspace,
                cache_db=genome_dir / "scan_cache.db",
            ),
            parser=SourceParser(),
            builder=GraphBuilder(),
            clusterer=GraphClusterer(),
            timeline=GraphTimeline(db_path),
            registry=GlobalDependencyRegistry(),
        )

    def should_process_path(self, rel_path: str) -> bool:
        """Return False for runtime artifacts and gitignored paths."""
        normalized = rel_path.replace("\\", "/").strip("/")
        if not normalized or normalized.startswith(".genome/") or normalized == ".genome":
            return False
        return not self.scanner.ignore.is_ignored(normalized)

    def flag_broken_proxy(self, graph, file_path: str, fqn: str) -> None:
        """Mark a proxy node broken when its provider symbol disappeared."""
        proxy_id = f"proxy:{file_path}:{fqn}"
        if graph.has_node(proxy_id):
            graph.set_node_attr(proxy_id, "is_broken", True)
