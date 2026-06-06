# API Layer & Progressive Disclosure

Documentation for Session 2: strict lazy-loading REST endpoints and WebSocket room subscriptions so the browser is never crushed by massive graph payloads.

---

## Overview

Large codebases cannot ship the full AST and dependency graph on initial load. Session 2 adds a **progressive disclosure API** that serves only what the UI needs at each zoom level:

| View | Biological level | Transport | When loaded |
|------|------------------|-----------|-------------|
| **Karyotype** | Genome / chromosomes | `GET /genome` + WebSocket `karyotype_update` | On startup |
| **Helix** | Genes / nucleotides | `GET /genome/{module_id}/graph` + WebSocket `graph_delta` | On chromosome click |
| **Structure map** | Package containment | `GET /genome/{module_id}/structure` | On structural drill-down |

Session 1 serializers (`HealthAggregator`, `map_nucleotide_sequence`) power the helix and health scores. Session 2 wires them into HTTP routes and scopes live WebSocket pushes to subscribed clients only.

---

## Problem & strategy

### Problem

Fetching every file’s full A/T/G/C sequence and structural tree at startup will exhaust browser memory on repos with thousands of files.

### Strategy

1. **Endpoint isolation** — three distinct REST paths with separate Pydantic contracts.
2. **Module-scoped loads** — helix and structure payloads are built only for the requested `module_id`.
3. **Room-based WebSocket** — clients declare what they are viewing; the server pushes full deltas only to matching helix rooms and lightweight patches to karyotype subscribers.

This aligns with the scaling plan in `goal/mapping.md` §4.B (Strict Lazy-Loading).

---

## Module identifiers

A **module** is the parent directory of a source file (the “chromosome” / package level in the biological metaphor).

| File path | `module_id` |
|-----------|-------------|
| `core/main.py` | `core` |
| `src/codegenome/cli.py` | `src/codegenome` |
| `solo.py` (repo root) | `__root__` |

`module_id` values are URL-encoded in path segments (e.g. `src%2Fcodegenome`).

Helpers live in `src/codegenome/serializers/genome_provider.py`:

- `module_id_for_file(path)`
- `module_id_from_node_id(node_id)`
- `file_belongs_to_module(path, module_id)`

---

## Prompt 2A — REST endpoints

Routes are registered in two places:

1. **MCP HTTP server** — `register_genome_routes()` in `src/codegenome/genome_routes.py`, called from `src/codegenome/mcp_tools/routes.py`.
2. **Live evolve HTTP server** — same handlers wired into `build_ai_request_handler()` in `src/codegenome/live_session.py`.

### `GET /genome`

Returns **top-level summaries only**: module IDs, aggregate gene (file) counts, and average health scores.

**Response schema:** `GenomeSummaryResponse`

```json
{
  "modules": [
    {
      "module_id": "core",
      "gene_count": 12,
      "health_score": 0.87
    },
    {
      "module_id": "src/codegenome",
      "gene_count": 45,
      "health_score": 0.91
    }
  ],
  "snapshot_id": 3
}
```

| Field | Meaning |
|-------|---------|
| `module_id` | Package directory identifier |
| `gene_count` | Number of source files in the module |
| `health_score` | Average per-file health (0.0–1.0) from `HealthAggregator` |
| `snapshot_id` | Current timeline snapshot (optional) |

**Try (MCP):**

```bash
curl http://127.0.0.1:7331/genome
```

**Try (live evolve):**

```bash
curl http://localhost:8000/genome
```

---

### `GET /genome/{module_id}/graph`

Returns the **dense helix payload**: indexed A/T/G/C nodes and edges for the Helix renderer. Built via `HealthAggregator.build_sequence()` per file, merged into a module-wide node array.

**Response schema:** `HelixGraphResponse`

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
      "base": "T",
      "line": 5,
      "payload": {
        "name": "Worker",
        "kind": "class",
        "qualified_name": "Worker",
        "start_line": 5,
        "end_line": 12,
        "complexity": 3,
        "docstring": null
      }
    }
  ],
  "edges": [
    { "source": 1, "target": 2, "edge_type": "calls" }
  ],
  "health_score": 0.89,
  "alerts": []
}
```

| Field | Meaning |
|-------|---------|
| `nodes` | Dense array; `index` is stable within the response |
| `edges` | Directed links between node indices (`calls`, `imports`, …) |
| `health_score` | Module-average health |
| `alerts` | Union of per-file alerts (`circular_import`, `zombie_nodes`, `high_complexity`) |

Returns **404** when `module_id` has no files.

---

### `GET /genome/{module_id}/structure`

Returns the **nested containment tree**: Package → Files → Classes → Methods.

**Response schema:** `StructureTreeResponse`

```json
{
  "module_id": "core",
  "package": "core",
  "files": [
    {
      "path": "core/main.py",
      "functions": [
        {
          "name": "run",
          "qualified_name": "run",
          "kind": "function",
          "start_line": 14,
          "end_line": 18,
          "complexity": 2
        }
      ],
      "classes": [
        {
          "name": "Worker",
          "qualified_name": "Worker",
          "kind": "class",
          "start_line": 5,
          "end_line": 12,
          "complexity": 3,
          "methods": [
            {
              "name": "save",
              "qualified_name": "Worker.save",
              "kind": "method",
              "start_line": 7,
              "end_line": 8,
              "complexity": 1
            }
          ]
        }
      ]
    }
  ]
}
```

Methods are nested under their parent class via `qualified_name` prefix (`Worker.save` → class `Worker`). Standalone functions appear under `files[].functions`.

Returns **404** when `module_id` has no files.

---

## Memory-bounded MCP

When the MCP server runs with `--memory-bounded`, the in-memory graph is empty by default. Genome endpoints call `GraphStore.graph_for_genome()`, which loads the **full snapshot from SQLite on demand** for the duration of the request.

This keeps bounded mode viable for local MCP tools while still allowing karyotype / helix / structure loads when the UI explicitly requests them.

---

## Prompt 2B — WebSocket rooms

Implementation: `src/codegenome/live_server.py`

Previously, `broadcast_graph_delta` fanned out every surgical graph delta to **all** connected clients. That defeats progressive disclosure when multiple users or tabs view different modules.

### Subscription protocol

After connecting to the WebSocket (default `ws://127.0.0.1:8765` during `codegenome evolve --live`), the client sends:

**Karyotype view (overview):**

```json
{ "action": "subscribe", "level": "karyotype" }
```

**Helix view (one module):**

```json
{ "action": "subscribe", "level": "helix", "module_id": "core" }
```

| Field | Required | Values |
|-------|----------|--------|
| `action` | yes | `"subscribe"` |
| `level` | yes | `"karyotype"` or `"helix"` |
| `module_id` | helix only | Package id (e.g. `"core"`, `"src/codegenome"`) |

Default subscription for new connections: `level: "karyotype"`.

### Outbound message types

#### `karyotype_update` (karyotype subscribers)

Lightweight health/count patch when any file in the workspace changes:

```json
{
  "type": "karyotype_update",
  "modules": [
    {
      "module_id": "core",
      "gene_count": 12,
      "health_score": 0.86
    }
  ],
  "snapshot_id": 4
}
```

#### `graph_delta` (helix subscribers in the affected module)

Full structural delta, **filtered to the subscribed module**:

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

Clients subscribed to a **different** helix `module_id` receive nothing. Karyotype clients never receive the full delta.

### Broadcast flow

```
File save (.py)
      │
      ▼
SurgicalUpdateHandler (watch_service.py)
      │
      ├─► timeline.compute_delta(prev, curr)
      │
      ├─► GenomeProvider.karyotype_updates_for_files([rel_path])
      │
      ▼
LiveGraphServer.sync_broadcast_graph_delta(...)
      │
      ├─► karyotype room  → KaryotypeUpdateMessage
      └─► helix room (matching module_id) → filter_graph_delta_for_module(...)
```

---

## Data flow (end-to-end)

```
Browser startup
      │
      ▼
GET /genome  ──► GenomeProvider.build_summary()
      │              └── HealthAggregator (per-file health → module average)
      ▼
Karyotype UI renders chromosomes

User clicks module "core"
      │
      ├─► GET /genome/core/graph     ──► build_helix_graph()
      │                                    └── build_sequence() per file
      │
      └─► GET /genome/core/structure ──► build_structure_tree()

WebSocket: { "action": "subscribe", "level": "helix", "module_id": "core" }

File saved in core/
      │
      ▼
WebSocket graph_delta (core room only) + karyotype_update (overview clients)
```

---

## Public Python API

```python
from codegenome.serializers import (
    GenomeProvider,
    GenomeSummaryResponse,
    HelixGraphResponse,
    StructureTreeResponse,
    module_id_for_file,
)

provider = GenomeProvider(graph)
summary = provider.build_summary(snapshot_id=3)
helix = provider.build_helix_graph("core")
structure = provider.build_structure_tree("core")
```

---

## File layout

```
pivot/
  backend-data-shaping.md           ← Session 1: A/T/G/C alphabet + health
  api-layer-progressive-disclosure.md  ← this document

src/codegenome/
  genome_routes.py                  ← REST handlers + MCP route registration
  live_server.py                    ← WebSocket rooms + targeted broadcast
  live_session.py                   ← HTTP genome routes on evolve server
  graph_store.py                    ← graph_for_genome() for bounded MCP
  mcp_tools/routes.py               ← wires genome routes into MCP server
  engine/watch_service.py           ← surgical update → room broadcast
  serializers/
    genome_schemas.py               ← Pydantic response models
    genome_provider.py              ← summary / helix / structure builders
    health_aggregator.py            ← health scores (Session 1)
    nucleotide_mapper.py            ← A/T/G/C mapping (Session 1)

tests/
  test_genome_api.py                ← REST payload + graph store tests
  test_live_server.py               ← WebSocket subscription tests
```

---

## Dependencies

| Package | Role |
|---------|------|
| `pydantic >=2,<3` | Response schema validation |
| `fastmcp` / Starlette | MCP custom HTTP routes |
| `websockets` | Live evolve WebSocket server |

Builds on Session 1 serializers and the existing `Graph` / timeline infrastructure.

---

## Related docs

- `pivot/backend-data-shaping.md` — nucleotide mapping and health scoring (Session 1)
- `goal/mapping.md` — biological hierarchy and lazy-loading strategy
- `goal/components_analysis.md` — codebase module mapping

---

## Next steps

1. **Frontend karyotype** — call `GET /genome` on load; subscribe to `karyotype` over WebSocket for live health bands.
2. **Frontend helix** — on chromosome click, fetch `/graph`, subscribe to `helix` with `module_id`; implement virtual rendering window (see `goal/mapping.md` §4.C).
3. **Frontend structure** — fetch `/structure` on drill-down; chunk files with “Load next 5” (see `goal/mapping.md` §4.D).
4. **SSE alternative** — optional Server-Sent Events mirror of `karyotype_update` for clients that cannot use WebSockets.
5. **Per-file helix** — optional `GET /genome/{module_id}/graph?file=...` if single-gene zoom needs a smaller payload.

After code changes, run `codegenome analyze` or `codegenome evolve --live` to keep the graph current.
