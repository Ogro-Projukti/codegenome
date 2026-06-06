"""Chidamber--Kemerer coupling (CBO) and cohesion (LCOM) metrics for class symbols."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from codegenome.graph_api import Graph

CLASS_KINDS = frozenset({"class", "trait"})
METHOD_KINDS = frozenset({"function", "method"})
INSTANCE_RECEIVERS = frozenset({"self", "this"})
SELF_ATTR_PATTERN = re.compile(r"^(?:self|this)\.([A-Za-z_]\w*)$")


@dataclass(frozen=True)
class ClassCouplingMetrics:
    """Coupling and cohesion metrics for a single class symbol."""

    node_id: str
    qualified_name: str
    cbo: int
    lcom: int
    method_count: int


class CouplingMetricsAnalyzer:
    """Compute CBO and LCOM from a CodeGenome dependency graph."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self._classes: dict[str, dict[str, Any]] = {}
        self._class_ids_by_name: dict[str, set[str]] = {}
        self._methods_by_class: dict[str, list[str]] = {}
        self._method_attrs: dict[str, set[str]] = {}
        self._build_indexes()

    def compute_all(self) -> dict[str, ClassCouplingMetrics]:
        """Return CBO/LCOM metrics keyed by class node id."""
        metrics: dict[str, ClassCouplingMetrics] = {}
        for class_id, attrs in self._classes.items():
            methods = self._methods_by_class.get(class_id, [])
            metrics[class_id] = ClassCouplingMetrics(
                node_id=class_id,
                qualified_name=str(attrs.get("qualified_name") or attrs.get("name") or class_id),
                cbo=self._compute_cbo(class_id, methods),
                lcom=self._compute_lcom(methods),
                method_count=len(methods),
            )
        return metrics

    def cbo_rankings(self) -> list[tuple[str, int]]:
        """Rank classes by descending CBO."""
        ranked = [(node_id, value.cbo) for node_id, value in self.compute_all().items() if value.cbo > 0]
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    def lcom_rankings(self) -> list[tuple[str, int]]:
        """Rank classes by descending LCOM (higher means lower cohesion)."""
        ranked = [(node_id, value.lcom) for node_id, value in self.compute_all().items() if value.lcom > 0]
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    def tightly_coupled_classes(self, *, min_cbo: int = 5) -> list[tuple[str, int]]:
        """Return classes whose CBO meets or exceeds ``min_cbo``."""
        return [(node_id, cbo) for node_id, cbo in self.cbo_rankings() if cbo >= min_cbo]

    def _build_indexes(self) -> None:
        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            kind = str(attrs.get("kind", ""))
            if kind in CLASS_KINDS:
                self._classes[node] = attrs
                name = str(attrs.get("name", ""))
                if name:
                    self._class_ids_by_name.setdefault(name, set()).add(node)

        class_qnames = {
            node_id: str(attrs.get("qualified_name") or attrs.get("name") or "")
            for node_id, attrs in self._classes.items()
        }

        for node, attrs in self.graph.iter_nodes():
            if attrs.get("node_type") != "symbol":
                continue
            if str(attrs.get("kind", "")) not in METHOD_KINDS:
                continue
            owner = _owner_class_for_method(
                str(attrs.get("qualified_name") or attrs.get("name") or ""),
                class_qnames,
            )
            if owner is None:
                continue
            self._methods_by_class.setdefault(owner, []).append(node)
            self._method_attrs[node] = _method_instance_attrs(node, attrs, self.graph)

    def _compute_cbo(self, class_id: str, methods: list[str]) -> int:
        coupled: set[str] = set()

        for _, target, edge_attrs in self.graph.out_edges(class_id):
            if edge_attrs.get("edge_type") != "inherits":
                continue
            resolved = self._resolve_class_node(target)
            if resolved and resolved != class_id:
                coupled.add(resolved)

        for method_id in methods:
            for _, target, edge_attrs in self.graph.out_edges(method_id):
                if edge_attrs.get("edge_type") != "calls":
                    continue
                resolved = self._resolve_call_target_class(target, source_method_id=method_id)
                if resolved and resolved != class_id:
                    coupled.add(resolved)

            for source, _, edge_attrs in self.graph.in_edges(method_id):
                if edge_attrs.get("edge_type") != "calls":
                    continue
                source_attrs = self.graph.get_node(source) if self.graph.has_node(source) else {}
                owner = _owner_class_for_method(
                    str(source_attrs.get("qualified_name") or source_attrs.get("name") or ""),
                    {
                        node_id: str(attrs.get("qualified_name") or attrs.get("name") or "")
                        for node_id, attrs in self._classes.items()
                    },
                )
                if owner and owner != class_id:
                    coupled.add(owner)

        return len(coupled)

    def _compute_lcom(self, methods: list[str]) -> int:
        """Chidamber--Kemerer LCOM: max(0, |P| - |Q|) over method pairs."""
        count = len(methods)
        if count <= 1:
            return 0

        disjoint_pairs = 0
        shared_pairs = 0
        for index, left_id in enumerate(methods):
            left_attrs = self._method_attrs.get(left_id, set())
            for right_id in methods[index + 1 :]:
                right_attrs = self._method_attrs.get(right_id, set())
                if left_attrs & right_attrs:
                    shared_pairs += 1
                else:
                    disjoint_pairs += 1

        return max(0, disjoint_pairs - shared_pairs)

    def _resolve_class_node(self, node_id: str) -> str | None:
        if node_id in self._classes:
            return node_id

        attrs = self.graph.get_node(node_id) if self.graph.has_node(node_id) else {}
        if attrs.get("node_type") == "symbol" and str(attrs.get("kind", "")) in CLASS_KINDS:
            return node_id

        name = str(attrs.get("name", ""))
        if not name:
            return None

        matches = self._class_ids_by_name.get(name, set())
        if len(matches) == 1:
            return next(iter(matches))
        return None

    def _resolve_call_target_class(self, node_id: str, *, source_method_id: str) -> str | None:
        if node_id in self._classes:
            return node_id

        attrs = self.graph.get_node(node_id) if self.graph.has_node(node_id) else {}
        node_type = attrs.get("node_type")
        if node_type == "symbol":
            qname = str(attrs.get("qualified_name") or attrs.get("name") or "")
            return _owner_class_for_method(
                qname,
                {
                    class_id: str(class_attrs.get("qualified_name") or class_attrs.get("name") or "")
                    for class_id, class_attrs in self._classes.items()
                },
            )

        if node_type == "proxy":
            return self._resolve_class_node(node_id)

        return None


def _owner_class_for_method(method_qname: str, class_qnames: dict[str, str]) -> str | None:
    owner_id: str | None = None
    owner_len = -1
    for class_id, class_qname in class_qnames.items():
        if not class_qname:
            continue
        prefix = f"{class_qname}."
        if method_qname.startswith(prefix) and len(class_qname) > owner_len:
            owner_id = class_id
            owner_len = len(class_qname)
    return owner_id


def _method_instance_attrs(method_id: str, attrs: dict[str, Any], graph: Graph) -> set[str]:
    stored = attrs.get("instance_attrs")
    instance_attrs: set[str] = set()
    if isinstance(stored, (list, tuple, set, frozenset)):
        instance_attrs.update(str(value) for value in stored if value)

    for _, target, edge_attrs in graph.out_edges(method_id):
        if edge_attrs.get("edge_type") != "calls":
            continue
        target_attrs = graph.get_node(target) if graph.has_node(target) else {}
        callee = str(target_attrs.get("name") or target_attrs.get("qualified_name") or "")
        match = SELF_ATTR_PATTERN.match(callee)
        if match:
            instance_attrs.add(match.group(1))

    return instance_attrs
