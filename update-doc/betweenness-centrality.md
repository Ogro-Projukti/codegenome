# Betweenness Centrality

This document describes the betweenness centrality update added to CodeGenome to complement Leiden community detection and bridge-node analysis.

## Summary

CodeGenome now computes **betweenness centrality** on the file-level dependency graph used for community clustering. The metric ranks files that lie on many shortest paths between other files — architectural choke points that community bridge flags alone may miss or under-rank.

Reference: Brandes (2001), *A faster algorithm for betweenness centrality*.

## What changed

### Clusterer

- `src/codegenome/clusterer.py` — core betweenness computation and graph annotation
- `ClusterResult` includes a `betweenness_centrality` map keyed by file node ID
- `compute_betweenness_centrality()` runs NetworkX normalized betweenness on the undirected file clustering graph
- `betweenness_rankings()` returns file nodes sorted by descending score
- `annotate()` writes `betweenness_centrality` onto file and symbol nodes (symbols inherit the score from their containing file)

### MCP

- New MCP tool: **`get_betweenness_centrality`**

### Paper

- `paper/main.tex` — structural analyses section updated to list betweenness as implemented

## Metric definition

### Betweenness centrality

For each file node `v`, betweenness counts how often `v` appears on shortest paths between other file pairs in the undirected dependency graph:

```
betweenness(v) = Σ (shortest paths through v) / (shortest paths between s and t)
                 over all s ≠ v ≠ t
```

NetworkX returns **normalized** scores in `[0, 1]` for undirected graphs.

The graph used is the same **file-level clustering graph** as Leiden community detection:

- **Import edges** — resolved to target file nodes
- **Call edges** — cross-file call relationships

Self-loops and unresolved imports are excluded.

## Bridge nodes vs betweenness

CodeGenome exposes two complementary structural signals:

| Signal | Detection rule | What it highlights |
|--------|----------------|--------------------|
| `is_bridge` | File has neighbors in other Leiden communities | Cross-community connectors |
| `betweenness_centrality` | High share of shortest paths pass through the file | Path-level choke points |

Examples of divergence:

- A file can be a **bridge** with **low betweenness** if it has only one cross-community edge and few alternate routes depend on it.
- A file can have **high betweenness** without being flagged **`is_bridge`** if it sits on many paths inside a densely connected hub.

Use both when triaging refactor targets, dependency cuts, or module-boundary changes.

## MCP usage

After rebuilding the graph:

```bash
codegenome analyze .
```

Query betweenness rankings:

```text
get_betweenness_centrality(limit=25)
get_betweenness_centrality(limit=10, include_generated=true)
```

### Response shape

```json
{
  "rankings": [
    {
      "node_id": "file:bridge.py",
      "betweenness_centrality": 0.42
    }
  ],
  "limit": 25
}
```

## Graph node attributes

During `codegenome analyze`, the clusterer annotates nodes with:

- `community_id` — Leiden community membership
- `is_bridge` — boolean cross-community bridge flag
- `betweenness_centrality` — normalized float score (file nodes; propagated to symbols via `file_path`)

These attributes are included in JSON exports and available to the HTML graph viewer through node payloads.

## Files touched

| Area | Files |
|------|-------|
| Clusterer | `src/codegenome/clusterer.py` |
| MCP store | `src/codegenome/graph_store.py` |
| MCP server | `src/codegenome/mcp_server.py` |
| Paper | `paper/main.tex` |
| Tests | `tests/test_clusterer.py`, `tests/test_mcp_server.py` |

## Keeping the graph current

After code changes, refresh the knowledge graph so MCP tools return up-to-date scores:

```bash
codegenome analyze .
```

Or run live updates:

```bash
codegenome evolve --live
```

## Limitations

- Scores are computed at **file granularity**, not per symbol or class
- The metric uses the static dependency graph; runtime call frequency is not weighted
- Disconnected files receive a score of `0.0`
- Very large graphs may incur higher analysis cost because betweenness scales with graph size
