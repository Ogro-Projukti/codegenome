# CLI reference

The **Watcher CLI** (`watcher` or `python -m codegenome`) builds and exports knowledge graphs, runs watch/live modes, scaffolds projects, queries timeline data, and starts the MCP server.

## How to invoke

| Method | When to use |
|--------|-------------|
| `watcher …` | After `pip install codegenome` or editable install |
| `python -m codegenome …` | Development or when the script is not on PATH |
| `python -m codegenome.mcp_server …` | Standalone MCP (stdio or custom HTTP port) |
| `python -m codegenome.installer …` | Write MCP entries into AI client configs |

```bash
watcher --help
```

---

## Workspace

Almost every command needs a project root (default: `.`):

```bash
watcher --workspace /path/to/my-app --build
```

The engine writes under `<workspace>/.genome/`:

| Path | Purpose |
|------|---------|
| `.genome/watcher.db` | Timeline snapshots (SQLite) |
| `.genome/graph.json` | Latest graph |
| `.genome/exports/` | HTML, Markdown, GraphML, etc. |
| `.genome/scan_cache.db` | Incremental scan cache |

Override the database with `--db-path` for timeline queries or MCP.

---

## Build & export

```bash
# Incremental build
watcher --workspace . --build

# Full rebuild
watcher --workspace . --build --full

# Custom exports (default: json, html, markdown)
watcher --workspace . --build --export json markdown graphml cypher obsidian
```

Supported formats: `json`, `html`, `markdown`, `graphml`, `cypher`, `obsidian`.

---

## Watch & live graph

```bash
# Debounced rebuild on file changes (default debounce: 30s)
watcher --workspace . --build --watch --watch-debounce 10

# Poll file/line totals and rebuild when they increase
watcher --workspace . --build --live-graph --live-graph-interval 60
```

---

## Metrics

```bash
watcher --workspace . --print-metrics
# {"file_count": 142, "line_count": 18450}
```

---

## MCP via main CLI

```bash
watcher --workspace . --build --mcp --watch
```

Starts HTTP MCP on `127.0.0.1:7331` after build. For stdio or a custom port, use `python -m codegenome.mcp_server`.

---

## Timeline queries

JSON to stdout; requires at least one prior build.

```bash
watcher --workspace . --dump-timeline
watcher --workspace . --dump-timeline --node-id "file:src/main.py"
watcher --workspace . --dump-changes --snapshot-from 1 --snapshot-to 3
watcher --workspace . --dump-churn --churn-limit 10
```

---

## Flag reference

| Flag | Description |
|------|-------------|
| `--workspace PATH` | Project root (default: `.`) |
| `--build` | Run graph build |
| `--full` | Force full rebuild |
| `--watch` | Debounced incremental rebuild |
| `--watch-debounce SECONDS` | Debounce interval (default: 30) |
| `--live-graph` | Rebuild when file/line totals increase |
| `--live-graph-interval SECONDS` | Poll interval (default: 30) |
| `--print-metrics` | Print file/line JSON and exit |
| `--export FMT …` | Export formats after build |
| `--db-path PATH` | Timeline DB path |
| `--mcp` | Start HTTP MCP after build |
| `--log-level LEVEL` | `DEBUG` … `ERROR` |
| `--dump-timeline` | Dump timeline JSON |
| `--dump-changes` | Snapshot diff (needs `--snapshot-from/to`) |
| `--dump-churn` | Churn rankings |
| `--node-id ID` | Filter `--dump-timeline` |
| `--snapshot-from ID` | Start snapshot |
| `--snapshot-to ID` | End snapshot |
| `--churn-file PATH` | Filter churn to one file |
| `--churn-limit N` | Max churn rows (default: 25) |

**Requires at least one of:** `--build`, `--watch`, `--live-graph` (unless using query/scaffold/metrics-only flags).

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (stderr) |

---

## Common workflows

### CI graph build

```bash
watcher --workspace . --build --export json
```

### Local dev + Cursor MCP

Terminal 1:

```bash
watcher --workspace . --build --mcp --watch
```

Terminal 2:

```bash
python -m codegenome.installer --db-path "$(pwd)/.genome/watcher.db" --client cursor
```

See [MCP integration](mcp-integration.md) and [Installation](installation.md).
