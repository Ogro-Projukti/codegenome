# GDR Persistence and Live Watch Ignore Fix

This document describes two related updates: snapshot-scoped persistence for the Global Dependency Registry (GDR), and a fix for `codegenome evolve --live` ingesting virtualenv files under `env/`.

Design background for memory-bounded storage lives in [`memory-bounded-storage.md`](memory-bounded-storage.md). This release implements **Phase 1** (GDR persist/load) plus a live-mode bug fix.

## Summary

### GDR persistence

The in-memory **Global Dependency Registry** (cross-file `Provides` / `Consumes` index) is now saved to SQLite alongside each graph snapshot. On engine restart, the registry is restored from the latest snapshot instead of starting empty.

### Live watch ignore fix

The filesystem watcher used by `evolve --live` and `watch` now applies the same ignore rules as the workspace scanner. Changes under `env/`, `venv/`, `.genome/`, and other gitignored paths no longer trigger surgical graph updates.

---

## GDR persistence

### Problem

Previously:

- The GDR lived only in process memory (`GlobalDependencyRegistry` in `core.py`).
- SQLite stored full graph snapshots but not registry state.
- Restarting the engine or MCP server left the registry empty until the next full/incremental build.

### Solution

New module `src/codegenome/gdr_store.py` writes snapshot-scoped GDR tables into `codegenome.db`:

| Table | Purpose |
|-------|---------|
| `gdr_files` | Per-file `provides` / `consumes` JSON blobs |
| `gdr_provides` | FQN → provider file (reverse lookup) |
| `gdr_consumes` | FQN → consuming files (reverse lookup) |
| `schema_meta` | Timeline schema version (`timeline_schema_version = 2`) |

After every `build()` and `surgical_update()`, `CodeGenomeEngine` calls `GDRStore.persist_snapshot(snapshot_id, registry)`. On startup, if GDR rows exist for the latest snapshot, `_load_existing_registry()` hydrates the in-memory registry.

### API surface

`GDRStore` (via `timeline.gdr_store`):

| Method | Description |
|--------|-------------|
| `persist_snapshot(snapshot_id, registry)` | Write full GDR for a snapshot |
| `hydrate_registry(snapshot_id, file_paths=None)` | Rebuild in-memory registry; optional per-file partial load |
| `load_file(snapshot_id, file_path)` | Single-file provides/consumes |
| `get_provider(snapshot_id, fqn)` | O(1) provider lookup from disk |
| `get_dependents(snapshot_id, fqn)` | O(1) consumer lookup from disk |
| `resolve_change_scope(...)` | Compute minimal file set for a surgical update |
| `has_snapshot(snapshot_id)` | Whether GDR was persisted for that snapshot |

Exported types: `GDRFileEntry`, `ChangeScope`, `GDRStore` (also in `codegenome.__init__`).

### Migration behavior

| Scenario | Behavior |
|----------|----------|
| Existing DB, old snapshots | No GDR rows; `has_snapshot()` is false; registry empty until next build |
| New build after upgrade | GDR persisted for new snapshots automatically |
| Restart after build | Registry restored from latest snapshot |

No manual migration step is required. Run `codegenome analyze .` once after upgrading to populate GDR for the current graph.

### Example: change scope resolution

```python
from codegenome.timeline import GraphTimeline

timeline = GraphTimeline(".genome/codegenome.db")
store = timeline.gdr_store
scope = store.resolve_change_scope(
    snapshot_id=1,
    changed_files={"beta.py"},
    removed_fqns={"helper"},
)
# scope.dependents — files that consumed removed symbols
# scope.providers — files that provide symbols referenced by changed files
```

---

## Live watch ignore fix

### Problem

`codegenome evolve --live` registers a `watchdog` observer on the entire workspace. `SurgicalUpdateHandler` reacted to **any** `.py` file change and only skipped paths under `.genome/`.

The workspace **scanner** correctly ignored `env/` via `.gitignore`, but the **watcher did not**. Installing packages (e.g. `pip install pytest`) or other activity under `env/Lib/site-packages/` triggered surgical updates and polluted the live graph.

### Solution

1. **`CodeGenomeEngine.should_process_path(rel_path)`** — returns `False` for `.genome/` and gitignored paths (uses `scanner.ignore`).
2. **`SurgicalUpdateHandler`** and **`_RebuildHandler`** — call `should_process_path()` before processing events.
3. **`DEFAULT_IGNORE_PATTERNS`** in `gitignore.py` — now includes `env/` and `venv/` even when not listed in a project `.gitignore`.

### Cleaning a polluted graph

If the live graph already contains `env/` nodes:

```bash
codegenome analyze .
```

For a fully clean slate:

```bash
# optional: remove artifacts
rm -rf .genome
codegenome analyze .
```

Then restart live mode:

```bash
codegenome evolve --live
```

---

## Files touched

| Area | Files |
|------|-------|
| GDR store | `src/codegenome/gdr_store.py` *(new)* |
| Timeline | `src/codegenome/timeline.py` — `gdr_store` property, schema init |
| Engine | `src/codegenome/core.py` — persist/load GDR, `should_process_path()` |
| Gitignore | `src/codegenome/gitignore.py` — `env/`, `venv/` in defaults |
| Package exports | `src/codegenome/__init__.py` |
| Tests | `tests/test_gdr_store.py` *(new)*, `tests/test_watch_ignore.py` *(new)*, `tests/test_scanner.py` |
| Design spec | `update-doc/memory-bounded-storage.md` |

---

## Tests

```bash
pytest tests/test_gdr_store.py tests/test_watch_ignore.py -q
```

Coverage includes:

- GDR round-trip persist / hydrate
- Provider and dependent lookups
- Change-scope resolution
- Partial registry hydrate
- Engine restart loads persisted registry
- Default ignore patterns cover `env/` and `venv/`
- `should_process_path()` skips virtualenv and `.genome` paths

---

## Keeping the graph current

After pulling this update or changing source files:

```bash
codegenome analyze .
```

For live updates (with ignore rules applied):

```bash
codegenome evolve --live
```

---

## Partial graph loading and working set (Phase 2–3)

### New capabilities

| Component | Purpose |
|-----------|---------|
| `graph_node_files` table | File-path index for each node at snapshot time |
| `graph_loader.node_file_path()` | Resolve owning file from node ID / attrs |
| `GraphTimeline.load_file_subgraph()` | Load nodes/edges for specific files only |
| `GraphTimeline.load_neighborhood()` | Bounded BFS load for MCP-style queries |
| `GraphTimeline.record_snapshot_patch()` | New snapshot by patching changed files in SQL |
| `WorkingSetGraph` | LRU-bounded in-memory file working set |
| `CodeGenomeConfig.memory_bounded` | Opt-in bounded runtime |
| `evolve --memory-bounded` | Live mode with bounded RAM after initial build |

### Memory-bounded live evolve

```bash
codegenome evolve --live --memory-bounded --max-working-files 64
```

Flow:

1. Initial `build()` still scans the full workspace and writes a complete snapshot.
2. After build, the in-memory graph is **evicted**; only snapshot metadata and GDR remain loaded.
3. Each surgical update:
   - Resolves `ChangeScope` via persisted GDR
   - Loads only scope files into `WorkingSetGraph`
   - Applies `builder.update()` on the working set
   - Persists via `record_snapshot_patch()` (no full-graph RAM required for write)
   - Temporarily loads the full snapshot from disk for exports/analysis, then drops it again

### Usage example

```python
from codegenome.timeline import GraphTimeline

timeline = GraphTimeline(".genome/codegenome.db")
snapshots = timeline.list_snapshots()
snapshot_id = snapshots[-1].snapshot_id

alpha_only = timeline.load_file_subgraph(snapshot_id, {"src/alpha.py"})
neighbors = timeline.load_neighborhood(snapshot_id, "file:src/alpha.py", depth=2, max_nodes=100)
```

## Limitations and next steps

Implemented:

- [x] GDR SQLite schema and `GDRStore` (Phase 1)
- [x] Persist / restore GDR on engine startup
- [x] Live/watch handlers respect gitignore
- [x] File-scoped graph load and snapshot patching (Phase 2)
- [x] `WorkingSetGraph` + `evolve --memory-bounded` (Phase 3)

Not yet implemented:

- [ ] Bounded MCP `GraphStore` mode (queries still load full graph by default)
- [ ] Global analyses without temporary full-graph reload after surgical updates
- [ ] GDR deltas per snapshot (full copy per snapshot today)
- [ ] Memory-bounded incremental `watch` rebuild path (debounced full rebuild still loads everything)

See [`memory-bounded-storage.md`](memory-bounded-storage.md) for the full design spec.
