# Session 5: Structural Map & Semantic Collapsing (Level 3)

This document records the Level 3 structural containment view: nested Package → Files → Classes → Methods cards, McCabe complexity badges, semantic file pagination, and surgical WebSocket patching for live IDE edits.

## Goal

When a user clicks a **gene** (nucleotide) on the helix (Level 2), drill down to Level 3 and render the module's containment hierarchy at the lowest practical detail — while protecting DOM memory on modules with 80+ files.

## Architecture

```mermaid
flowchart LR
  subgraph HTTP
    A[GET /genome/{module_id}/structure] --> B[structure.js]
  end
  subgraph WS
    C[LiveGraphServer :8765] -->|graph_delta| D[karyotype.js]
  end
  E[karyotype.js] -->|click helix gene| A
  E -->|subscribe structure| C
  B --> F[StructureMap]
  F -->|paginate 5 files| G[DOM file cards]
  D -->|patch visible files| G
```

| Layer | Responsibility |
|-------|----------------|
| `GenomeProvider.build_structure_tree()` | Nested Package → Files → Classes → Methods tree for one module |
| `GET /genome/{module_id}/structure` | Structure payload (HTTP + live session handler) |
| `LiveGraphServer` | Broadcasts filtered `graph_delta` to `level: "structure"` subscribers |
| `structure.js` | `StructureMap` — render, paginate, surgical codon patching |
| `karyotype.{html,css,js}` | Level 3 navigation, helix click drill-down, WebSocket room switching |

## View hierarchy

| Level | View | Trigger |
|-------|------|---------|
| 0 | Genome (community grid) | Initial load |
| 1 | Chromosome (module grid) | Click community card |
| 2 | Helix (DNA canvas) | Click module card |
| 3 | Structure map (containment tree) | Click a gene on the helix |

Breadcrumb: **Genome / Chromosome N / module-name / Structure**

Clicking the module crumb returns to the helix. Clicking Genome or the chromosome crumb returns to Levels 0–1.

## Backend contract

### `GET /genome/{module_id}/structure`

Returns a `StructureTreeResponse` built by `GenomeProvider.build_structure_tree()`:

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

| Field | Meaning |
|-------|---------|
| `package` | Display label for the module (`"."` for root) |
| `files` | Sorted source files in the module |
| `files[].functions` | Standalone functions at file scope |
| `files[].classes` | Classes, abstract classes, and interfaces |
| `classes[].methods` | Methods nested under parent class via `qualified_name` prefix |
| `complexity` | McCabe cyclomatic complexity per class or codon |

Methods are attached to classes when `qualified_name` shares a prefix (e.g. `Worker.save` → class `Worker`). Standalone functions appear under `files[].functions`.

Module ids with slashes are path-encoded in the URL:

```
/genome/src/codegenome/serializers/structure
```

Returns **404** when the module has no files.

### McCabe complexity badge tiers

| Tier | Range | Colour |
|------|-------|--------|
| Low | 1–5 | Green (`--health-good`) |
| Medium | 6–10 | Amber (`--health-warn`) |
| High | 11+ | Red (`--health-bad`) |

Badges appear on class cards and on codon (function/method) pills. Missing complexity is omitted.

### WebSocket: `graph_delta` (structure room)

When viewing the structure map, the client subscribes:

```json
{ "action": "subscribe", "level": "structure", "module_id": "core" }
```

Server pushes the same module-filtered delta as the helix room:

```json
{
  "type": "graph_delta",
  "module_id": "core",
  "snapshot_id": 4,
  "added_nodes": ["symbol:core/main.py:new_fn"],
  "removed_nodes": [],
  "modified_nodes": [],
  "added_edges": [],
  "removed_edges": []
}
```

Unlike the helix (which re-fetches the full graph), the structure client:

1. Extracts affected file paths from symbol node ids (`symbol:{path}:{qualified_name}`).
2. Intersects with **currently visible** file cards in the DOM.
3. Re-fetches `GET /genome/{module_id}/structure` once.
4. **Patches only** the visible file cards — appending new codon pills without rebuilding the tree.

## Frontend files

| File | Role |
|------|------|
| `src/codegenome/assets/html/structure.js` | `StructureMap` — nested cards, pagination, `patchFromTree()` |
| `src/codegenome/assets/html/karyotype.html` | Structure section: toolbar, `#structure-root` container |
| `src/codegenome/assets/html/karyotype.css` | Package/file/class/codon styles, complexity badges, load-more button |
| `src/codegenome/assets/html/karyotype.js` | Level 3 drill-down, helix click handler, structure WS patching |

Assets are copied to `.genome/exports/` on export via `HtmlWriter` and `SnapshotExporter` (including `structure.js`).

## UI behaviour

### Prompt 5A — Structural map layout

1. User clicks a **gene** on the helix scroll area (maps scroll Y position to node index via `PITCH = 16`).
2. Client fetches `GET /genome/{module_id}/structure`.
3. `StructureMap` renders a **Package** card containing nested **File** cards.
4. Each file card lists **Class** cards (with kind label: class / abstract / interface) and standalone **function** codon pills.
5. Class cards contain **Method** codon pills.
6. McCabe complexity badges appear on every class card and codon pill.

DOM hierarchy:

```
.structure-package
  └── .structure-files
        └── .structure-file[data-file-path]
              ├── .structure-classes
              │     └── .structure-class[data-qualified-name]
              │           └── .structure-methods
              │                 └── .codon-pill[data-qualified-name]
              └── .structure-functions
                    └── .codon-pill[data-qualified-name]
```

If the clicked gene belongs to a file beyond the first page, enough file pages load automatically so that file is visible and highlighted.

### Prompt 5B — Semantic collapsing & live file updates

**Problem:** A module with 80+ files is unreadable if every file card is rendered at once.

**Strategy (semantic collapsing):**

1. Only the first **5** file cards are inserted into the DOM on initial load (`FILES_PAGE_SIZE = 5`).
2. An **Expand / Load Next 5 Files** button appends the next chunk.
3. The button label adapts when fewer than 5 files remain (e.g. "Load Next 3 Files").
4. File cards not yet loaded stay out of the DOM entirely — protecting memory and cognitive load.

**Live updates:**

1. Client subscribes to `level: "structure"` with the current `module_id`.
2. On `graph_delta`, affected symbol paths are derived from `added_nodes`, `modified_nodes`, and `removed_nodes`.
3. Only **visible** file cards (already in the DOM) are patched.
4. New functions/methods are appended as `.codon-pill` elements with a `codon-new` pulse animation.
5. The full structure tree is **not** re-rendered — existing cards and pagination state are preserved.

## How to run

### Static export (after analyze)

```bash
codegenome analyze
```

Open:

```
.genome/exports/karyotype.html
```

Navigate: community card → module card → helix view → **click a gene** → structure map.

### Live evolution

```bash
codegenome evolve --live
```

Open:

```
http://localhost:<http-port>/karyotype.html?live=1&ws=<ws-port>
```

Add a new function to a file whose card is already visible in the structure map — a new codon pill should appear without a full tree refresh.

## Key source locations

| Area | Path |
|------|------|
| Structure schemas | `src/codegenome/serializers/genome_schemas.py` → `StructureTreeResponse`, `ClassNode`, `MethodNode` |
| Structure builder | `src/codegenome/serializers/genome_provider.py` → `build_structure_tree()` |
| REST routes | `src/codegenome/genome_routes.py` → `handle_genome_structure_get()` |
| Live HTTP handler | `src/codegenome/live_session.py` |
| WebSocket rooms | `src/codegenome/live_server.py` (`structure` level) |
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

Re-export copies updated `structure.js`, `karyotype.js`, and related assets into `.genome/exports/`.

## Test coverage

- `test_structure_tree_nests_classes_and_methods` — methods nested under parent class in structure payload
- `test_filter_graph_delta_for_module` — module-scoped WebSocket deltas
- `test_broadcast_targets_karyotype_and_helix_rooms` — room routing by `module_id`
- `test_subscribe_structure_room_receives_graph_delta` — structure room receives filtered `graph_delta`

## Related pivot docs

| Doc | Topic |
|-----|-------|
| `pivot/session-4-helix-canvas-rendering.md` | Level 2 helix canvas and virtual rendering |
| `pivot/session-3-karyotype-frontend.md` | Level 0–1 karyotype grid and live patches |
| `pivot/api-layer-progressive-disclosure.md` | REST + WebSocket progressive disclosure design |
| `pivot/backend-data-shaping.md` | Nucleotide mapping and health aggregation |
| `goal/mapping.md` | Biological metaphor and semantic collapsing strategy (§4.D) |
