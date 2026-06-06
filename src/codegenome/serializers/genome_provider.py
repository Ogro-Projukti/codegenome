"""Build progressive-disclosure genome payloads from a CodeGenome graph."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from codegenome.builder import file_node_id
from codegenome.graph_api import Graph
from codegenome.parser.types import ParsedCall, ParsedSymbol
from codegenome.serializers.genome_schemas import (
    ClassNode,
    FileStructureNode,
    GenomeSummaryResponse,
    HelixEdge,
    HelixGraphResponse,
    HelixNode,
    KaryotypeModuleUpdate,
    MethodNode,
    ModuleSummary,
    StructureTreeResponse,
)
from codegenome.serializers.health_aggregator import HealthAggregator
from codegenome.serializers.nucleotide_mapper import GraphEdgeInput, NucleotideBase

ROOT_MODULE_ID = "__root__"


def module_id_for_file(file_path: str) -> str:
    """Map a source file path to its package module identifier."""
    normalized = file_path.replace("\\", "/").strip("/")
    if not normalized or "/" not in normalized:
        return ROOT_MODULE_ID
    return normalized.rsplit("/", 1)[0]


def module_id_from_node_id(node_id: str) -> str | None:
    """Derive a module id from a graph node id when possible."""
    if node_id.startswith("file:"):
        return module_id_for_file(node_id[5:])
    for prefix in ("symbol:", "import:", "proxy:"):
        if node_id.startswith(prefix):
            parts = node_id.split(":", 2)
            if len(parts) >= 2:
                return module_id_for_file(parts[1])
    return None


def file_belongs_to_module(file_path: str, module_id: str) -> bool:
    """Return True when ``file_path`` is contained in ``module_id``."""
    return module_id_for_file(file_path) == module_id


def list_file_paths(graph: Graph) -> list[str]:
    """Return sorted source file paths present in the graph."""
    paths = [
        str(attrs.get("file_path"))
        for _, attrs in graph.iter_nodes()
        if attrs.get("node_type") == "file" and attrs.get("file_path")
    ]
    return sorted(set(paths))


def list_module_ids(graph: Graph) -> list[str]:
    """Return sorted unique module ids derived from file nodes."""
    module_ids = {module_id_for_file(path) for path in list_file_paths(graph)}
    return sorted(module_ids)


class GenomeProvider:
    """Serialize graph slices for karyotype, helix, and structure views."""

    def __init__(self, graph: Graph, *, test_coverage: dict[str, float] | None = None) -> None:
        self.graph = graph
        self._aggregator = HealthAggregator(graph, test_coverage=test_coverage)

    def build_summary(self, *, snapshot_id: int | None = None) -> GenomeSummaryResponse:
        """Return top-level module summaries only."""
        modules: list[ModuleSummary] = []
        files_by_module: dict[str, list[str]] = defaultdict(list)
        for path in list_file_paths(self.graph):
            files_by_module[module_id_for_file(path)].append(path)

        base_counts_by_module, community_by_module = self._module_metadata(files_by_module)

        for module_id in sorted(files_by_module):
            file_paths = files_by_module[module_id]
            health_scores = [
                self._aggregator.compute_module_health(path).health_score for path in file_paths
            ]
            average_health = sum(health_scores) / len(health_scores) if health_scores else 1.0
            modules.append(
                ModuleSummary(
                    module_id=module_id,
                    gene_count=len(file_paths),
                    health_score=round(average_health, 4),
                    community_id=community_by_module.get(module_id),
                    base_counts=base_counts_by_module.get(module_id, {}),
                )
            )
        return GenomeSummaryResponse(modules=modules, snapshot_id=snapshot_id)

    def _module_metadata(
        self,
        files_by_module: dict[str, list[str]],
    ) -> tuple[dict[str, dict[str, int]], dict[str, int | None]]:
        """Tally A/T/G/C bases and resolve a dominant Leiden community per module.

        Counts are derived in a single pass over the graph so the lightweight
        karyotype summary stays cheap even on large repositories:

            A — function/method symbols       T — class symbols
            A* — abstract class/interface      G — import edges
            C — call edges
        """
        base_counts: dict[str, dict[str, int]] = {
            module_id: {"A": 0, "A*": 0, "T": 0, "G": 0, "C": 0}
            for module_id in files_by_module
        }
        community_votes: dict[str, Counter] = {
            module_id: Counter() for module_id in files_by_module
        }

        for _, attrs in self.graph.iter_nodes():
            file_path = attrs.get("file_path")
            if not file_path:
                continue
            module_id = module_id_for_file(str(file_path))
            counts = base_counts.get(module_id)
            if counts is None:
                continue
            node_type = attrs.get("node_type")
            if node_type == "file":
                community_id = attrs.get("community_id")
                if community_id is not None:
                    community_votes[module_id][int(community_id)] += 1
            elif node_type == "symbol":
                kind = str(attrs.get("kind", ""))
                if kind in {"function", "method"}:
                    counts["A"] += 1
                elif kind in {"abstract_class", "interface"}:
                    counts["A*"] += 1
                elif kind == "class":
                    counts["T"] += 1

        for source, _, attrs in self.graph.iter_edges():
            edge_type = attrs.get("edge_type")
            if edge_type not in {"imports", "calls"}:
                continue
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            file_path = source_attrs.get("file_path")
            if not file_path:
                continue
            counts = base_counts.get(module_id_for_file(str(file_path)))
            if counts is None:
                continue
            counts["G" if edge_type == "imports" else "C"] += 1

        community_by_module: dict[str, int | None] = {
            module_id: (votes.most_common(1)[0][0] if votes else None)
            for module_id, votes in community_votes.items()
        }
        return base_counts, community_by_module

    def build_helix_graph(self, module_id: str) -> HelixGraphResponse | None:
        """Return dense nucleotide nodes and edges for one module."""
        file_paths = [
            path
            for path in list_file_paths(self.graph)
            if file_belongs_to_module(path, module_id)
        ]
        if not file_paths:
            return None

        nodes: list[HelixNode] = []
        node_key_to_index: dict[tuple[str, int, str], int] = {}
        edges: list[HelixEdge] = []
        alerts: set[str] = set()
        health_scores: list[float] = []

        for file_path in file_paths:
            symbols, calls, import_edges, import_attrs = self._extract_file_graph_data(file_path)
            sequence = self._aggregator.build_sequence(
                file_path,
                symbols,
                import_edges,
                calls,
                import_node_attrs=import_attrs,
            )
            health_scores.append(sequence.health_score)
            alerts.update(sequence.alerts)

            for entry in sequence.sequence:
                key = (file_path, entry.line, entry.base.value)
                if key in node_key_to_index:
                    index = node_key_to_index[key]
                else:
                    index = len(nodes)
                    node_key_to_index[key] = index
                    nodes.append(
                        HelixNode(
                            index=index,
                            file_path=file_path,
                            base=entry.base,
                            line=entry.line,
                            payload=entry.payload,
                        )
                    )

            for source, target, attrs in self.graph.iter_edges():
                edge_type = attrs.get("edge_type")
                if edge_type not in {"calls", "imports"}:
                    continue
                source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
                target_attrs = self.graph.get_node(target) if self.graph.has_node(target) else {}
                source_path = source_attrs.get("file_path")
                target_path = target_attrs.get("file_path") or source_path
                if source_path != file_path and target_path != file_path:
                    continue
                source_index = self._index_for_edge_endpoint(
                    nodes,
                    node_key_to_index,
                    source_attrs,
                    source,
                    attrs.get("line") or source_attrs.get("start_line"),
                    edge_type,
                )
                target_index = self._index_for_edge_endpoint(
                    nodes,
                    node_key_to_index,
                    target_attrs,
                    target,
                    attrs.get("line") or target_attrs.get("start_line"),
                    edge_type,
                )
                if source_index is None or target_index is None:
                    continue
                edge = HelixEdge(
                    source=source_index,
                    target=target_index,
                    edge_type=edge_type,  # type: ignore[arg-type]
                )
                if edge not in edges:
                    edges.append(edge)

        average_health = sum(health_scores) / len(health_scores) if health_scores else 1.0
        return HelixGraphResponse(
            module_id=module_id,
            nodes=nodes,
            edges=edges,
            health_score=round(average_health, 4),
            alerts=sorted(alerts),
        )

    def build_structure_tree(self, module_id: str) -> StructureTreeResponse | None:
        """Return nested Package -> Files -> Classes -> Methods tree."""
        file_paths = [
            path
            for path in list_file_paths(self.graph)
            if file_belongs_to_module(path, module_id)
        ]
        if not file_paths:
            return None

        files: list[FileStructureNode] = []
        for file_path in file_paths:
            symbols = self._symbols_for_file(file_path)
            classes: dict[str, ClassNode] = {}
            functions: list[MethodNode] = []

            for symbol in symbols:
                if symbol.kind in {"class", "abstract_class", "interface"}:
                    classes[symbol.qualified_name or symbol.name] = ClassNode(
                        name=symbol.name,
                        qualified_name=symbol.qualified_name or symbol.name,
                        kind=symbol.kind,  # type: ignore[arg-type]
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        complexity=symbol.complexity,
                        methods=[],
                    )
                    continue
                if symbol.kind == "method":
                    parent = self._parent_class_name(symbol.qualified_name or symbol.name)
                    if parent and parent in classes:
                        classes[parent].methods.append(self._method_node(symbol))
                    continue
                if symbol.kind == "function":
                    functions.append(self._method_node(symbol))

            files.append(
                FileStructureNode(
                    path=file_path,
                    functions=sorted(functions, key=lambda item: item.start_line),
                    classes=sorted(classes.values(), key=lambda item: item.start_line),
                )
            )

        package_label = module_id if module_id != ROOT_MODULE_ID else "."
        return StructureTreeResponse(module_id=module_id, package=package_label, files=files)

    def karyotype_updates_for_files(self, file_paths: list[str]) -> list[KaryotypeModuleUpdate]:
        """Build lightweight module patches for changed files."""
        modules = sorted({module_id_for_file(path) for path in file_paths})
        updates: list[KaryotypeModuleUpdate] = []
        for module_id in modules:
            summary = self.build_summary()
            match = next((item for item in summary.modules if item.module_id == module_id), None)
            if match is not None:
                updates.append(
                    KaryotypeModuleUpdate(
                        module_id=match.module_id,
                        gene_count=match.gene_count,
                        health_score=match.health_score,
                        community_id=match.community_id,
                        base_counts=match.base_counts,
                    )
                )
        return updates

    def _extract_file_graph_data(
        self,
        file_path: str,
    ) -> tuple[list[ParsedSymbol], list[ParsedCall], list[GraphEdgeInput], dict[str, dict]]:
        symbols = self._symbols_for_file(file_path)
        calls: list[ParsedCall] = []
        import_edges: list[GraphEdgeInput] = []
        import_attrs: dict[str, dict] = {}

        for source, target, attrs in self.graph.iter_edges():
            edge_type = attrs.get("edge_type")
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            if source_attrs.get("file_path") != file_path:
                continue
            if edge_type == "calls":
                caller = str(source_attrs.get("qualified_name") or source_attrs.get("name") or "")
                target_attrs = self.graph.get_node(target) if self.graph.has_node(target) else {}
                callee = str(target_attrs.get("qualified_name") or target_attrs.get("name") or "")
                calls.append(
                    ParsedCall(
                        caller=caller,
                        callee=callee,
                        line=int(attrs.get("line") or source_attrs.get("start_line") or 0),
                    )
                )
            elif edge_type == "imports":
                import_edges.append(GraphEdgeInput.from_tuple(source, target, attrs))
                if self.graph.has_node(target):
                    import_attrs[target] = self.graph.get_node(target)

        return symbols, calls, import_edges, import_attrs

    def _symbols_for_file(self, file_path: str) -> list[ParsedSymbol]:
        symbols: list[ParsedSymbol] = []
        for _, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "symbol" or attrs.get("file_path") != file_path:
                continue
            symbols.append(
                ParsedSymbol(
                    name=str(attrs.get("name", "")),
                    kind=str(attrs.get("kind", "function")),
                    start_line=int(attrs.get("start_line") or 0),
                    end_line=int(attrs.get("end_line") or 0),
                    docstring=attrs.get("docstring"),
                    complexity=attrs.get("complexity"),
                    qualified_name=attrs.get("qualified_name"),
                )
            )
        symbols.sort(key=lambda item: (item.start_line, item.qualified_name or item.name))
        return symbols

    @staticmethod
    def _method_node(symbol: ParsedSymbol) -> MethodNode:
        return MethodNode(
            name=symbol.name,
            qualified_name=symbol.qualified_name or symbol.name,
            kind=symbol.kind,  # type: ignore[arg-type]
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            complexity=symbol.complexity,
        )

    @staticmethod
    def _parent_class_name(qualified_name: str) -> str | None:
        if "." not in qualified_name:
            return None
        return qualified_name.rsplit(".", 1)[0]

    @staticmethod
    def _index_for_edge_endpoint(
        nodes: list[HelixNode],
        node_key_to_index: dict[tuple[str, int, str], int],
        attrs: dict[str, Any],
        node_id: str,
        line: Any,
        edge_type: str,
    ) -> int | None:
        file_path = str(attrs.get("file_path") or "")
        if not file_path:
            return None
        resolved_line = int(line or attrs.get("start_line") or 0)
        if edge_type == "imports":
            base = NucleotideBase.G_ALERT if "!" in node_id else NucleotideBase.G
            key = (file_path, resolved_line, base.value)
            return node_key_to_index.get(key)
        if attrs.get("node_type") == "symbol":
            kind = str(attrs.get("kind", "function"))
            if kind in {"abstract_class", "interface"}:
                base = NucleotideBase.A_STAR
            elif kind == "class":
                base = NucleotideBase.T
            elif kind in {"function", "method"}:
                base = NucleotideBase.A
            else:
                return None
            key = (file_path, resolved_line, base.value)
            return node_key_to_index.get(key)
        if edge_type == "calls":
            for index, node in enumerate(nodes):
                if node.file_path == file_path and node.base == NucleotideBase.C and node.line == resolved_line:
                    return index
        return None


def filter_graph_delta_for_module(delta_payload: dict[str, Any], module_id: str) -> dict[str, Any]:
    """Keep only delta elements that belong to ``module_id``."""
    filtered = dict(delta_payload)
    for key in ("added_nodes", "removed_nodes", "modified_nodes"):
        node_ids = delta_payload.get(key, [])
        filtered[key] = [
            node_id
            for node_id in node_ids
            if module_id_from_node_id(str(node_id)) == module_id
        ]
    for key in ("added_edges", "removed_edges"):
        edge_list = delta_payload.get(key, [])
        filtered[key] = [
            edge
            for edge in edge_list
            if _edge_belongs_to_module(edge, module_id)
        ]
    return filtered


def _edge_belongs_to_module(edge: Any, module_id: str) -> bool:
    if not isinstance(edge, (list, tuple)) or len(edge) < 2:
        return False
    source_module = module_id_from_node_id(str(edge[0]))
    target_module = module_id_from_node_id(str(edge[1]))
    return source_module == module_id or target_module == module_id


def resolve_changed_file_paths(delta_payload: dict[str, Any], fallback: str | None = None) -> list[str]:
    """Infer changed file paths from a graph delta payload."""
    paths: set[str] = set()
    if fallback:
        paths.add(fallback)
    for key in ("added_nodes", "removed_nodes", "modified_nodes"):
        for node_id in delta_payload.get(key, []):
            module = module_id_from_node_id(str(node_id))
            if module is None:
                continue
            if str(node_id).startswith("file:"):
                paths.add(str(node_id)[5:])
    return sorted(paths)
