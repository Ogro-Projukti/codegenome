# CBO and LCOM Coupling Metrics

This document describes the coupling-metrics update added to CodeGenome for tighter god-class detection and architectural analysis.

## Summary

CodeGenome now computes two Chidamber–Kemerer (CK) class-level metrics:

- **CBO** (Coupling Between Objects) — how many other classes a class depends on
- **LCOM** (Lack of Cohesion in Methods) — how little instance state is shared across a class’s methods

These metrics improve detection of **tightly coupled** and **god-class** candidates beyond raw graph degree alone.

## What changed

### New module

- `src/codegenome/coupling_metrics.py` — core CBO/LCOM computation from the dependency graph

### Parser and graph builder

- Method bodies are scanned for `self` / `this` attribute access
- Parsed `instance_attrs` are stored on symbol nodes and used for LCOM

### Intelligence layer

- `IntelligenceReport` includes:
  - `cbo_rankings`
  - `lcom_rankings`
  - `tightly_coupled_classes`
- `GraphIntelligence.annotate_coupling_metrics()` writes `cbo` and `lcom` onto class nodes during analysis
- `detect_god_nodes()` boosts class scores using `max(degree, cbo + lcom)`

### MCP and exports

- New MCP tool: **`get_coupling_metrics`**
- JSON exports include the new ranking fields

### Agent rules (under `src/`)

Rule templates and installed copies were updated to document:

- `get_coupling_metrics` (CBO/LCOM)
- God-node scoring that incorporates coupling metrics

## Metric definitions

### CBO (Coupling Between Objects)

For each class symbol, CBO counts **distinct coupled classes** via:

1. **Inheritance** — `inherits` edges to base classes
2. **Outgoing calls** — methods in the class calling methods owned by other classes
3. **Incoming calls** — methods in other classes calling this class’s methods

Higher CBO indicates stronger external coupling.

### LCOM (Lack of Cohesion in Methods)

For each class with more than one method, LCOM uses the CK formula:

```
LCOM = max(0, |P| - |Q|)
```

Where:

- **P** — pairs of methods that share **no** instance attributes
- **Q** — pairs of methods that share **at least one** instance attribute

Instance attributes are collected from:

- `self.attr` / `this.attr` in method bodies (parser)
- `self.attr` patterns in outgoing call targets (graph fallback)

Higher LCOM means lower cohesion (methods tend to work on disjoint state).

### Tightly coupled classes

Classes with **CBO ≥ 5** (default threshold) are listed as tightly coupled. The threshold is configurable via MCP.

## MCP usage

After rebuilding the graph:

```bash
codegenome analyze .
```

Query coupling metrics:

```text
get_coupling_metrics(limit=25)
get_coupling_metrics(limit=10, min_cbo=8)
get_coupling_metrics(include_generated=true)
```

### Response shape

```json
{
  "classes": [
    {
      "node_id": "symbol:path/to/file.py:MyClass",
      "qualified_name": "MyClass",
      "cbo": 7,
      "lcom": 12,
      "method_count": 8
    }
  ],
  "cbo_rankings": [{"node_id": "...", "cbo": 7}],
  "lcom_rankings": [{"node_id": "...", "lcom": 12}],
  "tightly_coupled_classes": [{"node_id": "...", "cbo": 7}],
  "limit": 25
}
```

## God-class detection

`get_god_nodes` still returns highly connected nodes, but **class symbols** now also factor in coupling:

```
class_score = max(in_degree + out_degree, cbo + lcom)
```

A class with moderate graph degree but very high CBO and LCOM can still surface as a god-node candidate.

## Files touched

| Area | Files |
|------|-------|
| Metrics | `src/codegenome/coupling_metrics.py` |
| Parser | `src/codegenome/parser.py` |
| Builder | `src/codegenome/builder.py` |
| Intelligence | `src/codegenome/intelligence.py` |
| Engine | `src/codegenome/core.py` |
| MCP store | `src/codegenome/graph_store.py` |
| MCP server | `src/codegenome/mcp_server.py` |
| Exports | `src/codegenome/exporter.py` |
| Rules | `src/codegenome/templates/rules/*`, `src/.cursor/rules/*`, `src/AGENTS.md`, etc. |
| Tests | `tests/test_coupling_metrics.py`, updates to `test_intelligence.py`, `test_parser.py`, `test_mcp_server.py` |

## Keeping the graph current

After code changes, refresh the knowledge graph so MCP tools return up-to-date metrics:

```bash
codegenome analyze .
```

Or run live updates:

```bash
codegenome evolve --live
```

## Limitations

- CBO resolves cross-file coupling through inheritance, direct call edges, and proxy nodes; unresolved dynamic calls may be under-counted
- LCOM depends on static `self`/`this` attribute access; languages or patterns that hide instance state may reduce accuracy
- Metrics apply to **class/trait** symbols; module-level functions are not scored with CBO/LCOM
