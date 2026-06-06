"""Map parsed AST structures into the A/T/G/C biological alphabet payload."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from codegenome.parser.types import ParsedCall, ParsedSymbol


class NucleotideBase(str, Enum):
    """DNA base letters used by the frontend helix renderer."""

    A = "A"
    A_STAR = "A*"
    T = "T"
    G = "G"
    C = "C"
    G_ALERT = "G!"


class GraphEdgeInput(BaseModel):
    """A directed graph edge with optional attributes."""

    source: str
    target: str
    edge_type: str
    line: int | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_tuple(cls, source: str, target: str, attrs: dict[str, Any]) -> GraphEdgeInput:
        """Build from a ``(source, target, attrs)`` graph iteration tuple."""
        edge_type = str(attrs.get("edge_type", ""))
        line = attrs.get("line") or attrs.get("start_line")
        return cls(
            source=source,
            target=target,
            edge_type=edge_type,
            line=int(line) if line is not None else None,
            attrs=dict(attrs),
        )


class SymbolPayload(BaseModel):
    """Payload for A, A*, and T nucleotides."""

    name: str
    kind: Literal["function", "method", "class", "abstract_class", "interface"]
    qualified_name: str | None = None
    start_line: int
    end_line: int
    complexity: int | None = None
    docstring: str | None = None


class ImportPayload(BaseModel):
    """Payload for G (import) nucleotides."""

    source: str
    target: str
    module: str | None = None
    names: list[str] = Field(default_factory=list)
    line: int


class CallPayload(BaseModel):
    """Payload for C (call) nucleotides."""

    caller: str
    callee: str
    line: int
    source: str | None = None
    target: str | None = None


class NucleotideEntry(BaseModel):
    """One base in the biological sequence."""

    base: NucleotideBase
    line: int
    payload: SymbolPayload | ImportPayload | CallPayload


class BiologicalSequence(BaseModel):
    """Ordered A/T/G/C sequence for a module or file."""

    sequence: list[NucleotideEntry]
    health_score: float = Field(default=1.0, ge=0.0, le=1.0)
    alerts: list[str] = Field(default_factory=list)


_BASE_SORT_ORDER = {
    NucleotideBase.G: 0,
    NucleotideBase.G_ALERT: 0,
    NucleotideBase.T: 1,
    NucleotideBase.A_STAR: 2,
    NucleotideBase.A: 3,
    NucleotideBase.C: 4,
}

_ABSTRACT_SYMBOL_KINDS = frozenset({"abstract_class", "interface"})


def _symbol_base(symbol: ParsedSymbol) -> NucleotideBase | None:
    if symbol.kind in _ABSTRACT_SYMBOL_KINDS:
        return NucleotideBase.A_STAR
    if symbol.kind in {"function", "method"}:
        return NucleotideBase.A
    if symbol.kind == "class":
        return NucleotideBase.T
    return None


def _symbol_payload(symbol: ParsedSymbol) -> SymbolPayload:
    kind = symbol.kind
    if kind not in {"function", "method", "class", "abstract_class", "interface"}:
        kind = "function"
    return SymbolPayload(
        name=symbol.name,
        kind=kind,  # type: ignore[arg-type]
        qualified_name=symbol.qualified_name,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        complexity=symbol.complexity,
        docstring=symbol.docstring,
    )


def _resolve_call_edge(
    call: ParsedCall,
    call_edges: list[GraphEdgeInput],
) -> tuple[str | None, str | None]:
    """Match a parsed call to its graph edge when possible."""
    for edge in call_edges:
        if edge.line == call.line:
            return edge.source, edge.target
    return None, None


def map_nucleotide_sequence(
    symbols: list[ParsedSymbol],
    edges: list[GraphEdgeInput | tuple[str, str, dict[str, Any]]],
    calls: list[ParsedCall],
    *,
    import_node_attrs: dict[str, dict[str, Any]] | None = None,
    circular_import_targets: set[str] | None = None,
) -> BiologicalSequence:
    """Map parsed symbols, import edges, and calls into AST traversal order.

    Mapping rules:
        A — ``ParsedSymbol`` with kind ``function`` or ``method``
        A* — ``ParsedSymbol`` with kind ``abstract_class`` or ``interface``
        T — ``ParsedSymbol`` with kind ``class``
        G — graph edges with ``edge_type == "imports"`` (``G!`` when circular)
        C — ``ParsedCall`` entries aligned with ``calls`` graph edges

    The returned ``sequence`` is sorted by source line, then by base kind
    (G → T → A* → A → C) to preserve declaration-before-use ordering at the same line.
    """
    normalized_edges: list[GraphEdgeInput] = []
    for edge in edges:
        if isinstance(edge, GraphEdgeInput):
            normalized_edges.append(edge)
        else:
            source, target, attrs = edge
            normalized_edges.append(GraphEdgeInput.from_tuple(source, target, attrs))

    import_edges = [edge for edge in normalized_edges if edge.edge_type == "imports"]
    call_edges = [edge for edge in normalized_edges if edge.edge_type == "calls"]
    circular_targets = circular_import_targets or set()
    node_attrs = import_node_attrs or {}

    entries: list[NucleotideEntry] = []

    for symbol in symbols:
        base = _symbol_base(symbol)
        if base is None:
            continue
        entries.append(
            NucleotideEntry(
                base=base,
                line=symbol.start_line,
                payload=_symbol_payload(symbol),
            )
        )

    for edge in import_edges:
        target_attrs = node_attrs.get(edge.target, {})
        line = edge.line or int(target_attrs.get("start_line", 0))
        module = target_attrs.get("module")
        names = list(target_attrs.get("names") or [])
        base = NucleotideBase.G_ALERT if edge.target in circular_targets else NucleotideBase.G
        entries.append(
            NucleotideEntry(
                base=base,
                line=line,
                payload=ImportPayload(
                    source=edge.source,
                    target=edge.target,
                    module=str(module) if module is not None else None,
                    names=names,
                    line=line,
                ),
            )
        )

    for call in calls:
        source_id, target_id = _resolve_call_edge(call, call_edges)
        entries.append(
            NucleotideEntry(
                base=NucleotideBase.C,
                line=call.line,
                payload=CallPayload(
                    caller=call.caller,
                    callee=call.callee,
                    line=call.line,
                    source=source_id,
                    target=target_id,
                ),
            )
        )

    entries.sort(key=lambda entry: (entry.line, _BASE_SORT_ORDER[entry.base], entry.base.value))
    return BiologicalSequence(sequence=entries)
