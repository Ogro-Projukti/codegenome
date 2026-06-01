"""Architectural intelligence analysis over Watcher dependency graphs.

This module provides tools for analyzing a dependency graph and deriving
actionable architectural signals such as dead code detection, circular
dependency identification, and complexity rankings.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
import networkx as nx

from codegenome.builder import file_node_id
from codegenome.graph_api import Graph
from codegenome.registry import GlobalDependencyRegistry


@dataclass(frozen=True)
class IntelligenceReport:
    """Aggregated architectural intelligence for a codebase graph.

    Attributes:
        dead_code (list[str]): List of node IDs representing unused symbols.
        circular_dependencies (list[list[str]]): List of cycles (each a list of nodes).
        god_nodes (list[tuple[str, float]]): Nodes with unusually high in/out degrees.
        entry_points (list[str]): File and symbol IDs that act as entry points.
        orphan_modules (list[str]): Files that are not imported by and do not import others.
        complexity_rankings (list[tuple[str, int]]): Symbols ranked by cyclomatic complexity.
        churn_rankings (list[tuple[str, int]]): Nodes ranked by churn rate.
    """

    dead_code: list[str] = field(default_factory=list)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    god_nodes: list[tuple[str, float]] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    orphan_modules: list[str] = field(default_factory=list)
    complexity_rankings: list[tuple[str, int]] = field(default_factory=list)
    churn_rankings: list[tuple[str, int]] = field(default_factory=list)


class GraphIntelligence:
    """Derive actionable architectural signals from a Watcher graph.

    This class provides various methods to analyze the codebase graph
    and detect issues like dead code, god nodes, and circular dependencies.
    """

    ENTRY_SYMBOL_NAMES = frozenset({"main", "run", "cli", "app"})
    ENTRY_FILE_NAMES = frozenset(
        {"__main__.py", "main.py", "app.py", "index.js", "index.ts", "index.tsx"}
    )
    GENERATED_PATH_PARTS = frozenset(
        {
            ".cache",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            "build",
            "coverage",
            "dist",
            "node_modules",
            "site-packages",
            "vendor",
            "vendors",
            "venv",
        }
    )
    GENERATED_FILE_SUFFIXES = (
        ".bundle.css",
        ".bundle.js",
        ".generated.css",
        ".generated.js",
        ".map",
        ".min.css",
        ".min.js",
    )

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

    def analyze(self) -> IntelligenceReport:
        """Run all architectural analyses and aggregate the results.

        Returns:
            IntelligenceReport: A comprehensive report of the graph intelligence.
        """
        return IntelligenceReport(
            dead_code=self.detect_dead_code(),
            circular_dependencies=self.detect_circular_dependencies(),
            god_nodes=self.detect_god_nodes(),
            entry_points=self.detect_entry_points(),
            orphan_modules=self.detect_orphan_modules(),
            complexity_rankings=self.complexity_rankings(),
            churn_rankings=self.churn_rankings(),
        )

    def detect_dead_code(
        self,
        *,
        include_generated: bool = False,
        include_public_api: bool = False,
    ) -> list[str]:
        """Detect functions and methods that are never called.

        Returns:
            list[str]: A sorted list of node IDs corresponding to dead code.
        """
        if self.graph.number_of_nodes() == 0:
            return []

        entry_symbols = set(self._entry_symbol_ids())
        dead: list[str] = []
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            if not include_generated and self._is_generated_or_vendor(attrs):
                continue
            if attrs.get("kind") not in {"function", "method"}:
                continue
            name = str(attrs.get("name", ""))
            if self._is_dunder_name(name):
                continue
            if not include_public_api and self._is_public_api_method(attrs):
                continue
            if node in entry_symbols:
                continue
            if any(
                edge_attrs.get("edge_type") == "calls"
                for _, _, edge_attrs in self.graph.out_edges(node)
            ):
                continue
            if any(
                pred_attrs.get("edge_type") == "calls"
                for _, _, pred_attrs in self.graph.in_edges(node)
            ):
                continue
            dead.append(node)
        return sorted(dead)

    def detect_circular_dependencies(self) -> list[list[str]]:
        """Identify circular import dependencies between files.

        Returns:
            list[list[str]]: A list of cycles, where each cycle is a list of node IDs.
        """
        file_graph = self._file_import_graph()
        if file_graph.number_of_nodes() == 0:
            return []

        cycles: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for component in nx.strongly_connected_components(file_graph):
            if len(component) < 2:
                continue
            subgraph = file_graph.subgraph(component)
            for cycle in nx.simple_cycles(subgraph):
                normalized = tuple(sorted(cycle))
                if normalized in seen:
                    continue
                seen.add(normalized)
                cycles.append(cycle)
        cycles.sort(key=lambda cycle: (len(cycle), cycle))
        return cycles

    def detect_god_nodes(
        self,
        *,
        include_generated: bool = False,
    ) -> list[tuple[str, float]]:
        """Identify nodes with excessively high degrees (god nodes).

        Returns:
            list[tuple[str, float]]: A list of tuples containing node IDs and their
                corresponding scores, sorted in descending order of score.
        """
        scores: dict[str, float] = {}
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") not in {"file", "symbol"}:
                continue
            if not include_generated and self._is_generated_or_vendor(attrs):
                continue
            in_degree = self.graph.in_degree(node)
            out_degree = self.graph.out_degree(node)
            
            if self.registry and attrs.get("node_type") == "symbol":
                fqn = attrs.get("qualified_name") or attrs.get("name")
                if fqn:
                    in_degree += len(self.registry.get_dependents(fqn))

            scores[node] = float(in_degree + out_degree)

        if not scores:
            return []

        values = list(scores.values())
        if len(values) == 1:
            node, score = next(iter(scores.items()))
            return [(node, score)]

        mean = statistics.fmean(values)
        try:
            spread = statistics.pstdev(values)
        except statistics.StatisticsError:
            spread = 0.0
        threshold = mean + self.god_node_stddevs * spread
        ranked = sorted(
            ((node, score) for node, score in scores.items() if score >= threshold),
            key=lambda item: (-item[1], item[0]),
        )
        return ranked

    def detect_entry_points(self) -> list[str]:
        """Detect file and symbol nodes that serve as application entry points.

        Returns:
            list[str]: A sorted list of node IDs representing entry points.
        """
        if self.graph.number_of_nodes() == 0:
            return []

        file_graph = self._file_import_graph()
        imported_files = {
            target
            for _, target in file_graph.edges()
        }
        all_files = {
            attrs["file_path"]
            for _, attrs in self.graph.iter_nodes()
            if attrs.get("node_type") == "file" and attrs.get("file_path")
        }
        file_entries = sorted(
            file_node_id(path)
            for path in all_files
            if file_node_id(path) not in imported_files
            or PathLike(path).name in self.ENTRY_FILE_NAMES
        )

        symbol_entries = self._entry_symbol_ids()
        return sorted(set(file_entries) | set(symbol_entries))

    def detect_orphan_modules(self) -> list[str]:
        """Identify files that have no incoming or outgoing dependencies.

        Returns:
            list[str]: A sorted list of file paths that are orphans.
        """
        if self.graph.number_of_nodes() == 0:
            return []

        file_graph = self._file_dependency_graph()
        orphans: list[str] = []
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "file":
                continue
            path = attrs.get("file_path")
            if not path:
                continue
            if file_graph.number_of_nodes() <= 1:
                continue
            if file_graph.degree(node) == 0:
                orphans.append(path)
        return sorted(orphans)

    def complexity_rankings(
        self,
        *,
        include_generated: bool = False,
    ) -> list[tuple[str, int]]:
        """Rank symbols based on their cyclomatic complexity.

        Returns:
            list[tuple[str, int]]: A list of tuples containing symbol node IDs and
                their complexity scores, sorted in descending order.
        """
        ranked: list[tuple[str, int]] = []
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            if not include_generated and self._is_generated_or_vendor(attrs):
                continue
            complexity = attrs.get("complexity")
            if complexity is None:
                continue
            ranked.append((node, int(complexity)))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    def churn_rankings(self) -> list[tuple[str, int]]:
        """Rank nodes based on their churn rate (how often they change).

        Returns:
            list[tuple[str, int]]: A list of tuples containing node IDs and their
                churn values, sorted in descending order.
        """
        ranked: list[tuple[str, int]] = []
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") not in {"file", "symbol"}:
                continue
            churn = int(attrs.get("churn", 0))
            if churn <= 0:
                continue
            ranked.append((node, churn))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    def _entry_symbol_ids(self) -> list[str]:
        entries: list[str] = []
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            name = str(attrs.get("name", ""))
            qname = str(attrs.get("qualified_name", ""))
            if name in self.ENTRY_SYMBOL_NAMES or qname.endswith(".main"):
                entries.append(node)
        return entries

    def _file_import_graph(self) -> nx.DiGraph:
        file_graph = nx.DiGraph()

        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") == "file":
                file_graph.add_node(node)

        if self.registry:
            for file_path, entry in self.registry.files.items():
                source_id = file_node_id(file_path)
                if source_id not in file_graph:
                    file_graph.add_node(source_id)
                for fqn in entry.consumes:
                    target_path = self.registry.get_provider(fqn)
                    if target_path and target_path != file_path:
                        target_id = file_node_id(target_path)
                        if target_id not in file_graph:
                            file_graph.add_node(target_id)
                        file_graph.add_edge(source_id, target_id)
            return file_graph

        module_index = self._module_to_file_index()
        for source, target, edge_attrs in self.graph.iter_edges():
            if edge_attrs.get("edge_type") != "imports":
                continue
            target_attrs = self.graph.get_node(target) if self.graph.has_node(target) else {}
            if target_attrs.get("node_type") != "import":
                continue
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            source_path = source_attrs.get("file_path")
            if not source_path:
                continue
            module = str(target_attrs.get("module", ""))
            target_file = self._resolve_module_to_file(module, source_path, module_index)
            if not target_file:
                continue
            target_id = file_node_id(target_file)
            if target_id in file_graph and source in file_graph:
                file_graph.add_edge(source, target_id)

        return file_graph

    def _file_dependency_graph(self) -> nx.Graph:
        dependency = nx.Graph()

        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") == "file":
                dependency.add_node(node)

        if self.registry:
            for file_path, entry in self.registry.files.items():
                source_id = file_node_id(file_path)
                if source_id not in dependency:
                    dependency.add_node(source_id)
                for fqn in entry.consumes:
                    target_path = self.registry.get_provider(fqn)
                    if target_path and target_path != file_path:
                        target_id = file_node_id(target_path)
                        if target_id not in dependency:
                            dependency.add_node(target_id)
                        dependency.add_edge(source_id, target_id)
            return dependency

        module_index = self._module_to_file_index()
        for source, target, edge_attrs in self.graph.iter_edges():
            edge_type = edge_attrs.get("edge_type")
            source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
            target_attrs = self.graph.get_node(target) if self.graph.has_node(target) else {}

            if edge_type == "imports" and target_attrs.get("node_type") == "import":
                source_path = source_attrs.get("file_path")
                module = str(target_attrs.get("module", ""))
                if not source_path:
                    continue
                target_file = self._resolve_module_to_file(module, source_path, module_index)
                if not target_file:
                    continue
                target_id = file_node_id(target_file)
                if source in dependency and target_id in dependency:
                    dependency.add_edge(source, target_id)
                continue

            if edge_type != "calls":
                continue
            source_file = source_attrs.get("file_path")
            target_file = target_attrs.get("file_path")
            if not source_file or not target_file or source_file == target_file:
                continue
            source_id = file_node_id(source_file)
            target_id = file_node_id(target_file)
            if source_id in dependency and target_id in dependency:
                dependency.add_edge(source_id, target_id)

        return dependency

    def _module_to_file_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "file":
                continue
            path = str(attrs.get("file_path", ""))
            if not path:
                continue
            stem = PathLike(path).stem
            index[stem] = path
            normalized = path.replace("\\", "/")
            without_ext = normalized.rsplit(".", 1)[0]
            index[without_ext] = path
            index[normalized] = path
            parts = without_ext.split("/")
            index[".".join(parts)] = path
            index[parts[-1]] = path
        return index

    def _resolve_module_to_file(
        self,
        module: str,
        source_path: str,
        module_index: dict[str, str],
    ) -> str | None:
        module = module.strip()
        if not module:
            return None

        normalized = module.replace("\\", "/")
        candidates = [
            normalized,
            normalized.replace(".", "/"),
            f"{normalized.replace('.', '/')}.py",
        ]
        if module.startswith("."):
            source_dir = PathLike(source_path).parent.as_posix()
            pieces = [part for part in module.split(".") if part]
            rel = source_dir
            for piece in pieces:
                if piece == "":
                    rel = str(PathLike(rel).parent) if rel and rel != "." else ""
                else:
                    rel = f"{rel}/{piece}".strip("/") if rel and rel != "." else piece
            candidates.extend([rel, f"{rel}.py"])

        for candidate in candidates:
            candidate = candidate.strip("/")
            if candidate in module_index:
                return module_index[candidate]
            if PathLike(candidate).stem in module_index:
                return module_index[PathLike(candidate).stem]
        return None

    def _is_generated_or_vendor(self, attrs: dict[str, object]) -> bool:
        path = str(attrs.get("file_path") or attrs.get("absolute_path") or "")
        if not path:
            return False

        normalized = path.replace("\\", "/").casefold()
        parts = {part for part in normalized.split("/") if part}
        if parts & self.GENERATED_PATH_PARTS:
            return True

        name = PathLike(normalized).name
        return name.endswith(self.GENERATED_FILE_SUFFIXES)

    @staticmethod
    def _is_dunder_name(name: str) -> bool:
        return len(name) > 4 and name.startswith("__") and name.endswith("__")

    @staticmethod
    def _is_public_api_method(attrs: dict[str, object]) -> bool:
        name = str(attrs.get("name", ""))
        if not name or name.startswith("_"):
            return False

        qname = str(attrs.get("qualified_name") or "")
        if "." not in qname:
            return False

        owner = qname.rsplit(".", 1)[0].rsplit(".", 1)[-1]
        return bool(owner) and owner[:1].isupper() and not owner.startswith("_")


class PathLike:
    """Minimal path helper to avoid importing pathlib in hot loops.

    Attributes:
        _value (str): The internal normalized path string.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        """Initialize the PathLike object.

        Args:
            value (str): The path string to normalize and wrap.
        """
        self._value = value.replace("\\", "/")

    @property
    def name(self) -> str:
        return self._value.rsplit("/", 1)[-1]

    @property
    def stem(self) -> str:
        name = self.name
        if "." in name:
            return name.rsplit(".", 1)[0]
        return name

    @property
    def parent(self) -> PathLike:
        if "/" not in self._value:
            return PathLike(".")
        return PathLike(self._value.rsplit("/", 1)[0])

    def as_posix(self) -> str:
        return self._value

    def __str__(self) -> str:
        return self._value
