# Backend Data Shaping & The Biological Alphabet

Documentation for Session 1: translating tree-sitter parse results and igraph dependency data into biological payloads for the frontend helix renderer.

---

## Overview

CodeGenome maps source structure into a **biological alphabet** so the UI can visualize code as DNA. Each AST-level element becomes a nucleotide in a strictly ordered sequence per module (source file).

### The alphabet

| Base | Name | Meaning | Source |
|------|------|---------|--------|
| **A** | Adenine | Functions / methods | `ParsedSymbol` where `kind` is `function` or `method` |
| **A\*** | Adenine (abstract) | Abstract classes / interfaces | `ParsedSymbol` where `kind` is `abstract_class` or `interface` |
| **T** | Thymine | Concrete classes | `ParsedSymbol` where `kind` is `class` |
| **G** | Guanine | Import statements | Graph edges with `edge_type == "imports"` |
| **C** | Cytosine | Function / method calls | `ParsedCall` entries (aligned with `calls` edges) |
| **G!** | Guanine (alert) | Circular import | Import nodes on files in a detected dependency cycle |

Extended variants follow the epigenetic model in `goal/mapping.md`: **A\*** marks abstract contracts; **G!** marks architectural risk.

Implementation lives under `src/codegenome/serializers/`. Parser classification helpers live in `src/codegenome/parser/common.py`.

---

## Data flow

```
tree-sitter AST
      │
      ▼
  SourceParser  ──►  ParseResult (symbols, imports, calls)
      │
      ▼
  GraphBuilder  ──►  Graph (nodes + edges: imports, calls, contains, …)
      │
      ├──────────────────────────────────────┐
      ▼                                      ▼
map_nucleotide_sequence()            HealthAggregator
      │                                      │
      └──────────────┬───────────────────────┘
                     ▼
            BiologicalSequence
         (sequence + health_score + alerts)
```

---

## Prompt 1A — Nucleotide Mapper

**Module:** `src/codegenome/serializers/nucleotide_mapper.py`

### Public API

```python
from codegenome.serializers import (
    BiologicalSequence,
    GraphEdgeInput,
    NucleotideBase,
    NucleotideEntry,
    map_nucleotide_sequence,
)
```

### Pydantic models

| Model | Fields / values |
|-------|-----------------|
| `NucleotideBase` | `A`, `A*`, `T`, `G`, `C`, `G!` |
| `GraphEdgeInput` | `source`, `target`, `edge_type`, `line`, `attrs` |
| `SymbolPayload` | `name`, `kind`, `qualified_name`, `start_line`, `end_line`, `complexity`, `docstring` |
| `ImportPayload` | `source`, `target`, `module`, `names`, `line` |
| `CallPayload` | `caller`, `callee`, `line`, `source`, `target` |
| `NucleotideEntry` | `base`, `line`, `payload` (discriminated by base) |
| `BiologicalSequence` | `sequence`, `health_score` (0.0–1.0), `alerts` |

`SymbolPayload.kind` is one of: `function`, `method`, `class`, `abstract_class`, `interface`.

### Mapping rules

| Input | Base | Notes |
|-------|------|-------|
| `ParsedSymbol` kind `function` / `method` | **A** | Pure logic |
| `ParsedSymbol` kind `abstract_class` / `interface` | **A\*** | Abstract contract |
| `ParsedSymbol` kind `class` | **T** | Concrete OOP structure |
| Graph edge `edge_type == "imports"` | **G** or **G!** | **G!** when target is in `circular_import_targets` |
| `ParsedCall` (+ matching `calls` edge) | **C** | Execution flow |

Unknown symbol kinds are skipped.

### Core function

```python
sequence = map_nucleotide_sequence(
    symbols,          # list[ParsedSymbol]
    edges,            # list[GraphEdgeInput | (source, target, attrs)]
    calls,            # list[ParsedCall]
    import_node_attrs={
        "import:repo.py:2:os": {
            "module": "os",
            "names": ["os"],
            "start_line": 2,
        }
    },
    circular_import_targets={"import:repo.py:1:beta"},  # → G!
)
```

`GraphEdgeInput.from_tuple(source, target, attrs)` normalizes raw graph iteration tuples.

### Traversal order

The `sequence` array is sorted by:

1. **Source line** (ascending)
2. **Base priority** at the same line: **G** / **G!** → **T** → **A\*** → **A** → **C**

This mirrors AST walk order from the parser (imports and type declarations before methods and calls).

### Example sequence

For a file containing an import, an ABC, a concrete class, a method call, and a standalone function:

```
Line  Base  Payload kind
────  ────  ────────────
  2   G     import os
  5   A*    abstract_class  AbstractRepo
  7   A     method          AbstractRepo.save
 10   C     call            → helper
 14   T     class           ConcreteRepo
 17   A     function        helper
```

---

## Parser layer — A\* detection

Before mapping, language extractors classify symbols into the correct `kind`. Helpers in `src/codegenome/parser/common.py`:

| Helper | Purpose |
|--------|---------|
| `python_class_kind()` | `class`, `abstract_class`, or `interface` for Python |
| `typescript_class_kind()` | `class` or `abstract_class` for TS/JS |
| `go_type_kind()` | `class` (struct) or `interface` for Go |

### Per-language rules

| Language | `abstract_class` | `interface` | `class` (→ **T**) |
|----------|----------------|-------------|-------------------|
| **Python** | Bases `ABC`, `ABCMeta`; `@abstractmethod` on any method; `@abstract` decorator | Base `Protocol` | All other `class` definitions |
| **TypeScript / JS** | `abstract class` AST node | `interface` declaration | Regular `class` |
| **Go** | — | `type Name interface { ... }` | `type Name struct { ... }` and other type specs |
| **Rust** | — | `trait` items | `struct`, `enum` items |

### Python example

```python
from abc import ABC, abstractmethod
from typing import Protocol

class AbstractRepo(ABC):       # kind: abstract_class  →  A*
    @abstractmethod
    def save(self): ...

class Readable(Protocol):      # kind: interface       →  A*
    def read(self) -> str: ...

class ConcreteRepo:            # kind: class           →  T
    def save(self): ...
```

### TypeScript example

```typescript
export abstract class BaseService {  // abstract_class → A*
  abstract run(): void;
}
export interface Reader {           // interface      → A*
  read(): string;
}
export class Worker { }              // class          → T
```

Parser types are defined in `src/codegenome/parser/types.py`:

- `ParsedSymbol` — name, kind, line range, complexity, docstring, qualified name
- `ParsedCall` — caller, callee, line
- Import **G** nucleotides come from graph edges built by `GraphBuilder` (`src/codegenome/builder.py`), not directly from `ParsedImport` objects

---

## Prompt 1B — Health Aggregator

**Module:** `src/codegenome/serializers/health_aggregator.py`

### Public API

```python
from codegenome.serializers import HealthAggregator, ModuleHealthReport
```

### `HealthAggregator`

```python
aggregator = HealthAggregator(
    graph,
    test_coverage={"alpha.py": 0.92},  # optional per-module overrides
    weights=HealthWeights(              # optional; defaults 0.25 each
        coverage=0.25,
        circular=0.25,
        zombie=0.25,
        complexity=0.25,
    ),
)
```

| Method | Returns | Purpose |
|--------|---------|---------|
| `compute_module_health(module_path)` | `ModuleHealthReport` | 0.0–1.0 score + alerts + factor breakdown |
| `circular_import_targets()` | `set[str]` | Import node IDs to render as **G!** |
| `files_in_cycles()` | `set[str]` | File node IDs in circular import cycles |
| `dead_symbol_ids()` | `set[str]` | Zombie (dead-code) symbol node IDs |
| `build_sequence(...)` | `BiologicalSequence` | Full pipeline: map + health + **G!** flags |

### Health score formula

Per-module score is a weighted sum (default weight **0.25** each):

```
health_score = w.coverage  × test_coverage
             + w.circular  × (1 - circular_dep_rate)
             + w.zombie    × (1 - zombie_node_rate)
             + w.complexity × normalized_complexity
```

| Factor | Source | Default when missing |
|--------|--------|----------------------|
| `test_coverage` | `test_coverage` dict | **0.85** (mocked) |
| `circular_dep_rate` | `1.0` if file is in an import cycle, else `0.0` | igraph SCC on file import graph |
| `zombie_node_rate` | dead symbols ÷ total symbols in module | `DeadCodeAnalyzer` |
| `normalized_complexity` | `1 - min(avg_mccabe / 50, 1.0)` | symbol `complexity` graph attrs |

Result is clamped to `[0.0, 1.0]`.

### `ModuleHealthReport`

```python
ModuleHealthReport(
    module_path="alpha.py",
    health_score=0.72,
    alerts=["circular_import"],
    test_coverage=0.85,
    circular_dep_rate=1.0,
    zombie_node_rate=0.0,
    normalized_complexity=0.91,
)
```

### Alerts

| Alert | Trigger |
|-------|---------|
| `circular_import` | Module file participates in an import cycle |
| `zombie_nodes` | One or more dead-code symbols in the module |
| `high_complexity` | Normalized complexity score &lt; 0.5 |

### G! flagging

1. Build file-level import graph via `FileGraphProjector`
2. Detect cycles with **igraph** strongly-connected components (≥ 2 nodes)
3. Fallback: `CircularDependencyAnalyzer` (NetworkX)
4. Collect import node IDs on cyclic files → pass as `circular_import_targets` to the mapper

### Combined pipeline

```python
payload = aggregator.build_sequence(
    module_path="alpha.py",
    symbols=parse_result.symbols,
    edges=list(graph.iter_edges()),
    calls=parse_result.calls,
    import_node_attrs={
        node_id: graph.get_node(node_id)
        for _, node_id, attrs in graph.iter_edges()
        if attrs.get("edge_type") == "imports"
    },
)

# payload.sequence     → ordered A / A* / T / G / G! / C entries
# payload.health_score → float 0.0–1.0
# payload.alerts       → e.g. ["circular_import", "zombie_nodes"]
```

---

## Example JSON output

```json
{
  "sequence": [
    {
      "base": "G",
      "line": 2,
      "payload": {
        "source": "file:repo.py",
        "target": "import:repo.py:2:abc",
        "module": "abc",
        "names": ["ABC"],
        "line": 2
      }
    },
    {
      "base": "A*",
      "line": 5,
      "payload": {
        "name": "AbstractRepo",
        "kind": "abstract_class",
        "qualified_name": "AbstractRepo",
        "start_line": 5,
        "end_line": 8,
        "complexity": 2,
        "docstring": null
      }
    },
    {
      "base": "T",
      "line": 14,
      "payload": {
        "name": "ConcreteRepo",
        "kind": "class",
        "qualified_name": "ConcreteRepo",
        "start_line": 14,
        "end_line": 20,
        "complexity": 3,
        "docstring": "Concrete implementation."
      }
    }
  ],
  "health_score": 0.91,
  "alerts": []
}
```

---

## File layout

```
pivot/
  backend-data-shaping.md          ← this document

src/codegenome/serializers/
  __init__.py                      ← public exports
  nucleotide_mapper.py             ← A / A* / T / G / C / G! mapping + Pydantic schema
  health_aggregator.py             ← health score, alerts, G! detection

src/codegenome/parser/
  common.py                        ← python_class_kind, typescript_class_kind, go_type_kind
  types.py                         ← ParsedSymbol, ParsedCall, ParseResult
  languages/
    python.py                      ← ABC / Protocol / abstractmethod detection
    javascript.py                  ← abstract class + interface extraction
    go.py                          ← interface type detection
    rust.py                        ← trait → interface kind

tests/
  test_nucleotide_mapper.py        ← mapping + A* tests
  test_health_aggregator.py        ← health score + G! tests
  test_parser.py                   ← abstract_class / interface parser tests
```

---

## Dependencies

| Package | Role |
|---------|------|
| `pydantic >=2,<3` | Output schema validation (`pyproject.toml`) |
| `python-igraph` | Circular dependency cycle detection |
| `networkx` | Fallback cycle analysis, file import graph |

Reuses existing intelligence modules: `FileGraphProjector`, `CircularDependencyAnalyzer`, `DeadCodeAnalyzer`.

---

## Related docs

- `goal/mapping.md` — biological metaphor, 6-level hierarchy, scaling strategy
- `goal/components_analysis.md` — mapping metaphor to existing codebase modules

---

## Next steps

1. Wire `HealthAggregator.build_sequence()` into an API route (e.g. `GET /genome/{module_id}/structure`)
2. Expose module-level `health_score` on the karyotype `GET /genome` payload
3. Push sequence deltas over the WebSocket live server on file save
4. Replace mocked test coverage with real coverage provider integration
5. Frontend: render **A\*** with a distinct visual variant (e.g. decorated adenine purple)

After code changes, run `codegenome analyze` or `codegenome evolve --live` to keep the graph current.
