"""Tests for biological alphabet nucleotide mapping."""

from __future__ import annotations

from codegenome.parser.types import ParsedCall, ParsedSymbol
from codegenome.serializers.nucleotide_mapper import (
    GraphEdgeInput,
    NucleotideBase,
    map_nucleotide_sequence,
)


def test_maps_symbols_imports_and_calls_in_ast_order() -> None:
    symbols = [
        ParsedSymbol(
            name="Greeter",
            kind="class",
            start_line=5,
            end_line=15,
            qualified_name="Greeter",
            complexity=2,
        ),
        ParsedSymbol(
            name="greet",
            kind="method",
            start_line=7,
            end_line=12,
            qualified_name="Greeter.greet",
            complexity=3,
        ),
        ParsedSymbol(
            name="helper",
            kind="function",
            start_line=17,
            end_line=19,
            qualified_name="helper",
        ),
    ]
    edges = [
        GraphEdgeInput(
            source="file:sample.py",
            target="import:sample.py:2:os",
            edge_type="imports",
        ),
        GraphEdgeInput(
            source="symbol:sample.py:Greeter.greet",
            target="proxy:sample.py:helper",
            edge_type="calls",
            line=10,
        ),
    ]
    calls = [ParsedCall(caller="Greeter.greet", callee="helper", line=10)]
    import_attrs = {
        "import:sample.py:2:os": {"module": "os", "names": ["os"], "start_line": 2},
    }

    result = map_nucleotide_sequence(
        symbols,
        edges,
        calls,
        import_node_attrs=import_attrs,
    )

    bases = [entry.base for entry in result.sequence]
    lines = [entry.line for entry in result.sequence]
    assert bases == [
        NucleotideBase.G,
        NucleotideBase.T,
        NucleotideBase.A,
        NucleotideBase.C,
        NucleotideBase.A,
    ]
    assert lines == [2, 5, 7, 10, 17]
    assert result.health_score == 1.0
    assert result.alerts == []


def test_skips_unknown_symbol_kinds() -> None:
    symbols = [
        ParsedSymbol(name="x", kind="variable", start_line=1, end_line=1),
        ParsedSymbol(name="run", kind="function", start_line=2, end_line=3),
    ]
    result = map_nucleotide_sequence(symbols, [], [])
    assert len(result.sequence) == 1
    assert result.sequence[0].base == NucleotideBase.A


def test_flags_circular_imports_as_g_alert() -> None:
    edges = [
        GraphEdgeInput(
            source="file:a.py",
            target="import:a.py:1:beta",
            edge_type="imports",
        ),
    ]
    import_attrs = {
        "import:a.py:1:beta": {"module": "beta", "names": ["beta"], "start_line": 1},
    }
    result = map_nucleotide_sequence(
        [],
        edges,
        [],
        import_node_attrs=import_attrs,
        circular_import_targets={"import:a.py:1:beta"},
    )
    assert result.sequence[0].base == NucleotideBase.G_ALERT


def test_accepts_raw_edge_tuples() -> None:
    edges = [
        (
            "file:mod.py",
            "import:mod.py:3:json",
            {"edge_type": "imports"},
        ),
    ]
    import_attrs = {
        "import:mod.py:3:json": {"module": "json", "start_line": 3},
    }
    result = map_nucleotide_sequence([], edges, [], import_node_attrs=import_attrs)
    assert result.sequence[0].base == NucleotideBase.G
    assert result.sequence[0].line == 3


def test_maps_abstract_classes_and_interfaces_to_a_star() -> None:
    symbols = [
        ParsedSymbol(
            name="AbstractRepo",
            kind="abstract_class",
            start_line=3,
            end_line=8,
            qualified_name="AbstractRepo",
        ),
        ParsedSymbol(
            name="Readable",
            kind="interface",
            start_line=10,
            end_line=12,
            qualified_name="Readable",
        ),
        ParsedSymbol(
            name="Concrete",
            kind="class",
            start_line=14,
            end_line=16,
            qualified_name="Concrete",
        ),
    ]
    result = map_nucleotide_sequence(symbols, [], [])
    bases = [entry.base for entry in result.sequence]
    assert bases == [NucleotideBase.A_STAR, NucleotideBase.A_STAR, NucleotideBase.T]
    assert result.sequence[0].payload.kind == "abstract_class"
    assert result.sequence[1].payload.kind == "interface"
