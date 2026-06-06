# Modularity and SRP Refactor

This document describes the architectural refactor that split several god objects into focused packages and services. The goal was to improve modularity, testability, and single-responsibility layering without breaking the public CLI or library APIs.

## Summary

| Priority | Change | Outcome |
|----------|--------|---------|
| P0 | Split `CodeGenomeEngine` into services | `engine/` package; thin coordinator in `core.py` |
| P0 | Decompose TUI + service API | `tui/` package; `CodeGenomeService` replaces subprocess CLI for analyze/export/rules |
| P1 | Split `GraphIntelligence` into analyzers | `intelligence/` package; facade preserves public API |
| P1 | Separate GraphStore from GraphTimeline | `McpAnalysisProvider`, `SnapshotExporter` |
| P2 | Format-specific exporters | `exporter/` package with `FormatWriter` protocol |
| P2 | Extract `evolve` into `LiveSession` | `live_session.py`; slim `cli.py` command |
| P3 | Per-language parser modules | `parser/` package with `languages/` extractors |
| P3 | MCP tool modules + registry | `mcp_tools/` package; slim `create_server` |

All **159** tests pass after the refactor.

---

## P0 — Engine services

### Problem

`CodeGenomeEngine` in `core.py` was an orchestration hub: scanning, building, persistence, exports, filesystem watch, and MCP process startup lived in one class with high coupling (CBO) and low cohesion (LCOM).

### Solution

New package `src/codegenome/engine/`:

| Module | Responsibility |
|--------|----------------|
| `types.py` | `CodeGenomeConfig`, `BuildResult`, progress types |
| `context.py` | `EngineContext` — shared mutable state for services |
| `scan_service.py` | Workspace scan and source parsing |
| `build_service.py` | Graph build, incremental rebuild, surgical updates |
| `persistence_service.py` | Snapshot, GDR, and metrics persistence |
| `export_service.py` | Graph artifact export |
| `watch_service.py` | Filesystem watch handlers and watch loop |
| `mcp_process.py` | MCP server subprocess lifecycle |

`CodeGenomeEngine` in `core.py` is now a thin facade that delegates to these services. Backward-compatible `@property` accessors expose internal context fields for existing callers.

### Usage

```python
from codegenome.core import CodeGenomeEngine, CodeGenomeConfig

engine = CodeGenomeEngine(CodeGenomeConfig(workspace=Path(".")))
result = engine.build(full=False)
engine.close()
```

---

## P0 — TUI decomposition and service API

### Problem

`CodeGenomeTUI` mixed UI layout, CSS, memory-mode settings, subprocess management, and CLI orchestration. Analyze, export, and rules ran as subprocess `codegenome` invocations instead of in-process calls.

### Solution

| Module | Responsibility |
|--------|----------------|
| `tui/app.py` | Main `CodeGenomeTUI` application |
| `tui/constants.py` | Page and channel constants |
| `tui/memory.py` | Memory-mode settings and CLI flag helpers |
| `tui/process.py` | `SubprocessController` for MCP/evolve subprocesses |
| `tui/styles.py` | Textual CSS |
| `tui/widgets.py` | Custom widgets (`ReadOnlyRichLog`) |
| `service.py` | `CodeGenomeService` — in-process facade for analyze, export, rules |

The TUI uses `CodeGenomeService` for analyze, export, and rules (Textual thread workers). MCP and evolve remain subprocess-based where process isolation is required.

`codegenome/tui.py` was removed; `tui/__init__.py` re-exports the public API.

---

## P1 — Intelligence analyzers

### Problem

`GraphIntelligence` was a single module (~complexity 102, LCOM ~40) performing dead-code detection, cycles, entry points, god nodes, rankings, and coupling in one class.

### Solution

New package `src/codegenome/intelligence/`:

| Module | Responsibility |
|--------|----------------|
| `report.py` | `IntelligenceReport`, serialization helpers |
| `classifier.py` | `NodeClassifier` — entry points, generated/vendor, API surface |
| `projections.py` | `FileGraphProjector` — file-level graph projections |
| `context.py` | `AnalysisContext` — shared state for analyzers |
| `structural.py` | Dead code, cycles, entry points, orphan modules |
| `rankings.py` | God nodes, complexity, churn rankings |
| `coupling.py` | CBO/LCOM coupling analyzer |
| `engine.py` | `GraphIntelligence` facade |

Public imports from `codegenome.intelligence` are unchanged.

---

## P1 — GraphStore vs GraphTimeline layering

### Problem

- `GraphTimeline` handled HTML/JSON export via `GraphExporter`, mixing persistence with presentation.
- `GraphStore` (MCP query layer) embedded logic for choosing precomputed metrics vs live analysis.

### Solution

| Module | Responsibility |
|--------|----------------|
| `snapshot_exporter.py` | `SnapshotExporter` — JSON/HTML export from SQLite |
| `mcp_analysis.py` | `McpAnalysisProvider` — bounded vs full analysis source |

`GraphTimeline` exposes its SQLite `connection` and delegates `export_snapshot_json` / `export_snapshot_html` to `SnapshotExporter`. `GraphStore.get_*` analysis methods delegate to `McpAnalysisProvider`.

---

## P2 — Format-specific exporters

### Problem

`exporter.py` was a monolith (LCOM ~163) with JSON, HTML, GraphML, Cypher, Markdown, and Obsidian logic in one `GraphExporter` class.

### Solution

New package `src/codegenome/exporter/`:

| Module | Responsibility |
|--------|----------------|
| `statistics.py` | `GraphStatistics`, `SUPPORTED_FORMATS` |
| `context.py` | `ExportContext` — shared graph/report/workspace |
| `base.py` | `FormatWriter` protocol |
| `json_writer.py` | Atomic JSON write (Windows-friendly replace) |
| `html_writer.py` | Interactive vis-network HTML |
| `graphml_writer.py` | NetworkX GraphML |
| `cypher_writer.py` | Neo4j Cypher statements |
| `markdown_writer.py` | Jinja report template |
| `obsidian_writer.py` | Obsidian vault with interlinked notes |
| `coordinator.py` | `GraphExporter` — delegates to writers |

`codegenome.exporter` re-exports `GraphExporter`, `GraphStatistics`, and `SUPPORTED_FORMATS`. Existing imports continue to work.

Unused `COMMUNITY_PALETTE` was removed from the Python exporter package (the HTML viewer keeps its own palette in `assets/html/graph-viewer.js`).

---

## P2 — LiveSession

### Problem

The `codegenome evolve` command in `cli.py` was a ~160-line function mixing initial build, WebSocket broadcast, HTTP/AI-chat server, browser launch, filesystem watch, and teardown.

### Solution

New module `src/codegenome/live_session.py`:

| Type | Responsibility |
|------|----------------|
| `LiveSessionConfig` | Workspace, live/LAN, memory-bounded, ports |
| `LiveSession` | Full session lifecycle (`serve()`, `stop()`) |
| `build_ai_request_handler()` | HTTP handler for graph viewer + AI endpoints |

The `evolve` CLI command is now a thin adapter:

```python
session = LiveSession(LiveSessionConfig(...), emit=click.echo)
session.serve()
```

---

## P3 — Per-language parser modules

### Problem

`parser.py` (~850 lines) combined dataclasses, AST helpers, grammar loading, and per-language extractors for Python, JS/TS, Go, and Rust.

### Solution

New package `src/codegenome/parser/`:

| Module | Responsibility |
|--------|----------------|
| `types.py` | `ParsedSymbol`, `ParsedImport`, `ParseResult`, etc. |
| `common.py` | Line numbers, complexity, docstrings, call recording |
| `languages/python.py` | Python extractor |
| `languages/javascript.py` | JS/TS/TSX extractor |
| `languages/go.py` | Go extractor |
| `languages/rust.py` | Rust extractor |
| `__init__.py` | `SourceParser`, grammar loading, extractor registry |

Public imports (`SourceParser`, `ParseResult`, `ParsedSymbol`, …) are unchanged. `_build_language` remains on the package for tree-sitter API compatibility tests.

---

## P3 — MCP tool modules

### Problem

`mcp_server.py` `create_server()` registered ~15 tools inline with a large `guarded_tool` decorator, middleware, and custom routes in one function.

### Solution

| Module | Responsibility |
|--------|----------------|
| `mcp_runtime.py` | `ok`/`error` envelopes, `log_event`, context vars |
| `mcp_tools/guard.py` | `build_guarded_tool` decorator |
| `mcp_tools/middleware.py` | `ClientContextMiddleware` |
| `mcp_tools/routes.py` | `/health`, `/mcp/activity` |
| `mcp_tools/graph_tools.py` | `register_graph_tools` |

`create_server` is now ~10 lines:

```python
guarded_tool = build_guarded_tool(service, tracker)
register_routes(mcp, service, tracker)
register_graph_tools(mcp, service, guarded_tool)
return mcp
```

`mcp_server.py` still exports `GraphService`, `ServerConfig`, `create_server`, `ok`, `error`, and `main` for tests and CLI.

---

## Files removed

| Former path | Replaced by |
|-------------|-------------|
| `src/codegenome/exporter.py` | `src/codegenome/exporter/` |
| `src/codegenome/parser.py` | `src/codegenome/parser/` |
| `src/codegenome/tui.py` | `src/codegenome/tui/` |
| `src/codegenome/intelligence.py` | `src/codegenome/intelligence/` |

---

## Backward compatibility

| Import / API | Status |
|--------------|--------|
| `from codegenome.exporter import GraphExporter, SUPPORTED_FORMATS` | Unchanged |
| `from codegenome.parser import SourceParser, ParseResult` | Unchanged |
| `from codegenome.intelligence import GraphIntelligence` | Unchanged |
| `from codegenome.tui import main` | Unchanged |
| `from codegenome.mcp_server import create_server, ok, error` | Unchanged |
| `codegenome evolve`, `analyze`, `export`, `mcp-start` CLI | Unchanged behavior |

---

## Tests

```bash
pytest -q
```

Expected: **159 passed**.

MCP-specific coverage:

```bash
pytest tests/test_mcp_server.py tests/test_mcp_server_load.py -q
```

Parser coverage:

```bash
pytest tests/test_parser.py -q
```

---

## Keeping the graph current

After pulling this refactor, refresh the knowledge graph:

```bash
codegenome analyze .
```

For MCP in the editor, use memory-bounded mode:

```bash
codegenome mcp-start --path . --memory-bounded
```

Or in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "codegenome": {
      "command": "codegenome",
      "args": ["mcp-start", "--path", "${workspaceFolder}", "--memory-bounded"]
    }
  }
}
```

---

## Package map (post-refactor)

```
src/codegenome/
├── core.py                 # CodeGenomeEngine facade
├── service.py              # CodeGenomeService (TUI/CLI library API)
├── live_session.py         # evolve session lifecycle
├── snapshot_exporter.py    # SQLite → JSON/HTML
├── mcp_analysis.py         # MCP analysis source selection
├── mcp_runtime.py          # MCP envelopes and context
├── mcp_server.py           # Server config, GraphService, main
├── engine/                 # Build/scan/persist/export/watch
├── exporter/               # Format writers + GraphExporter
├── intelligence/           # Per-concern analyzers
├── parser/                 # SourceParser + language extractors
├── tui/                    # Textual dashboard
└── mcp_tools/              # Tool registration, guard, routes
```
