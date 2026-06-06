# Session 4: The 3D Helix & Virtual Rendering (Level 2)

This document records the Level 2 DNA helix view: the HTML5 Canvas double-helix renderer, scroll-synced virtual rendering for large modules, and live graph-delta refresh.

## Goal

When a user clicks a **module chromosome** (Level 1), drill down to Level 2 and render that module's nucleotide sequence as a rotating 3D double helix — without crashing frame rate on modules with thousands of bases.

## Architecture

```mermaid
flowchart LR
  subgraph HTTP
    A[GET /genome/{module_id}/graph] --> B[helix.js]
  end
  subgraph WS
    C[LiveGraphServer :8765] -->|graph_delta| B
  end
  D[karyotype.js] -->|click module| A
  D -->|subscribe helix| C
  B --> E[Canvas double helix]
  E -->|scroll| F[Virtual rendering window]
```

| Layer | Responsibility |
|-------|----------------|
| `GenomeProvider.build_helix_graph()` | Dense A/T/G/C node array and edges for one module |
| `GET /genome/{module_id}/graph` | Helix payload (HTTP + live session handler) |
| `LiveGraphServer` | Broadcasts filtered `graph_delta` to `level: "helix"` subscribers |
| `helix.js` | 3D projection, colour mapping, virtual window, animation loop |
| `karyotype.{html,css,js}` | Level 2 navigation, helix shell, WebSocket room switching |

## View hierarchy

| Level | View | Trigger |
|-------|------|---------|
| 0 | Genome (community grid) | Initial load |
| 1 | Chromosome (module grid) | Click community card |
| 2 | Helix (DNA canvas) | Click module card |

Breadcrumb: **Genome / Chromosome N / module-name**

## Backend contract

### `GET /genome/{module_id}/graph`

Returns a `HelixGraphResponse` built by `HealthAggregator.build_sequence()` per file, merged into a module-wide indexed array.

```json
{
  "module_id": "core",
  "nodes": [
    {
      "index": 0,
      "file_path": "core/main.py",
      "base": "G",
      "line": 1,
      "payload": {
        "source": "file:core/main.py",
        "target": "import:core/main.py:1:os",
        "module": "os",
        "names": ["os"],
        "line": 1
      }
    },
    {
      "index": 1,
      "file_path": "core/main.py",
      "base": "A*",
      "line": 5,
      "payload": {
        "name": "BaseService",
        "kind": "abstract_class",
        "qualified_name": "BaseService",
        "start_line": 5,
        "end_line": 12,
        "complexity": 2,
        "docstring": null
      }
    }
  ],
  "edges": [
    { "source": 1, "target": 2, "edge_type": "calls" }
  ],
  "health_score": 0.89,
  "alerts": ["circular_import"]
}
```

| Field | Meaning |
|-------|---------|
| `nodes` | Dense array; `index` is stable within the response |
| `edges` | Directed links between node indices (`calls`, `imports`, …) |
| `health_score` | Module-average health |
| `alerts` | Union of per-file alerts (`circular_import`, `zombie_nodes`, `high_complexity`) |

Module ids with slashes (e.g. `src/codegenome/serializers`) are path-encoded in the URL:

```
/genome/src/codegenome/serializers/graph
```

Returns **404** when the module has no files.

### Nucleotide colour mapping (helix renderer)

| Base | Meaning | Colour | Visual indicator |
|------|---------|--------|------------------|
| **A** | Function / method | Purple `#9b59b6` | — |
| **A*** | Abstract class / interface | Lavender `#c39bd3` | Dashed ring |
| **T** | Class | Teal `#20b2aa` | — |
| **G** | Import | Coral `#ff7f50` | — |
| **C** | Call | Blue `#4e79a7` | — |
| **G!** | Circular import | Bright red `#ff2244` | Pulsing ring + `!` badge |

### WebSocket: `graph_delta`

When viewing the helix, the client re-subscribes:

```json
{ "action": "subscribe", "level": "helix", "module_id": "core" }
```

Server pushes a module-filtered delta on file changes:

```json
{
  "type": "graph_delta",
  "module_id": "core",
  "snapshot_id": 4,
  "added_nodes": ["symbol:core/main.py:run"],
  "removed_nodes": [],
  "modified_nodes": [],
  "added_edges": [],
  "removed_edges": []
}
```

The helix client re-fetches `GET /genome/{module_id}/graph` on `graph_delta` to refresh the canvas in place.

## Frontend files

| File | Role |
|------|------|
| `src/codegenome/assets/html/helix.js` | `HelixRenderer` — 3D double helix, virtual window, `requestAnimationFrame` loop |
| `src/codegenome/assets/html/karyotype.html` | Helix section: toolbar, legend, scroll container, canvas overlay |
| `src/codegenome/assets/html/karyotype.css` | Helix layout, colour legend, module card click affordance |
| `src/codegenome/assets/html/karyotype.js` | Level 2 drill-down, graph fetch, WebSocket room switching |

Assets are copied to `.genome/exports/` on export via `HtmlWriter` and `SnapshotExporter`.

## UI behaviour

### Prompt 4A — DNA helix canvas rendering

1. User clicks a **module chromosome** card at Level 1.
2. Client fetches `GET /genome/{module_id}/graph`.
3. `HelixRenderer` maps each node to a position on a vertical double helix.
4. Two backbone strands rotate slowly (`ROTATION_SPEED = 0.004` rad/frame).
5. Bases are drawn as coloured spheres on the near strand; rungs connect the two backbones.
6. **G!** nodes render bright red with a pulsing alert ring and `!` marker.
7. **A*** nodes render in lavender with a dashed ring (abstract / interface).

### Prompt 4B — Canvas virtual rendering window

Large modules may contain thousands of nucleotides. Drawing every base each frame would tank FPS.

**Strategy:**

1. A scrollable `#helix-scroll` container holds a `#helix-spacer` whose height is `nodes.length × PITCH` (16 px per base).
2. A viewport-sized `#helix-canvas` is absolutely positioned over the scroll area.
3. On scroll (and each animation frame), the renderer computes:
   - `visibleStart = floor(scrollTop / PITCH) - OVERSCAN`
   - `visibleEnd = ceil((scrollTop + clientHeight) / PITCH) + OVERSCAN`
4. Only bases in `[visibleStart, visibleEnd]` are projected and drawn (`ctx.fill()` / `ctx.stroke()`).
5. A fixed pool of 512 slot objects is recycled each frame to avoid per-frame allocations.
6. Bases outside the visible Y range are skipped entirely.

This keeps the animation loop at **30+ FPS** even for modules with thousands of genes.

### Karyotype integration

- `BASE_LETTERS` on karyotype cards includes **A*** alongside A, T, G, C.
- WebSocket subscription switches between `karyotype` (Levels 0–1) and `helix` (Level 2).
- Returning via breadcrumb stops the renderer and re-subscribes to `karyotype`.

## How to run

### Static export (after analyze)

```bash
codegenome analyze
```

Open:

```
.genome/exports/karyotype.html
```

Navigate: community card → module card → helix view. Scroll to traverse the sequence.

### Live evolution

```bash
codegenome evolve --live
```

Open:

```
http://localhost:<http-port>/karyotype.html?live=1&ws=<ws-port>
```

Live edits to files in the viewed module trigger `graph_delta` and an automatic helix refresh.

## Key source locations

| Area | Path |
|------|------|
| Helix schemas | `src/codegenome/serializers/genome_schemas.py` |
| Helix builder | `src/codegenome/serializers/genome_provider.py` → `build_helix_graph()` |
| Nucleotide mapping | `src/codegenome/serializers/nucleotide_mapper.py` |
| Circular import (G!) | `src/codegenome/serializers/health_aggregator.py` |
| REST routes | `src/codegenome/genome_routes.py` |
| Live HTTP handler | `src/codegenome/live_session.py` |
| WebSocket rooms | `src/codegenome/live_server.py` |
| Asset export | `src/codegenome/exporter/html_writer.py`, `snapshot_exporter.py` |
| Tests | `tests/test_genome_api.py`, `tests/test_live_server.py` |

## Refreshing data

After code or graph structure changes:

```bash
codegenome analyze
```

Or keep the graph live:

```bash
codegenome evolve --live
```

Re-export copies updated `helix.js` and karyotype assets into `.genome/exports/`.

## Test coverage

- `test_helix_graph_returns_dense_nodes_and_edges` — A/T/G/C nodes in helix payload
- `test_filter_graph_delta_for_module` — module-scoped WebSocket deltas
- `test_broadcast_targets_karyotype_and_helix_rooms` — helix room routing by `module_id`

## Related pivot docs

| Doc | Topic |
|-----|-------|
| `pivot/session-3-karyotype-frontend.md` | Level 0–1 karyotype grid and live patches |
| `pivot/api-layer-progressive-disclosure.md` | REST + WebSocket progressive disclosure design |
| `pivot/backend-data-shaping.md` | Nucleotide mapping and health aggregation |
| `goal/mapping.md` | Biological metaphor and virtual rendering strategy (§4.C) |
