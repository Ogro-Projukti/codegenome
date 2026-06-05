# CLI reference

Codegenome ships two CLI interfaces:

| Interface | Invoke | Best for |
|-----------|--------|----------|
| **Modern CLI** | `codegenome <subcommand>` | Day-to-day use, TUI, exports, stdio MCP |
| **Legacy CLI** | `python -m codegenome --flags` | Watch mode, HTTP MCP, timeline queries, all export formats |

Both operate on a **workspace** (project root). By default that is the current directory (`.`). Graph data is stored under `<workspace>/.genome/`.

## Workspace artifacts

| Path | Purpose |
|------|---------|
| `.genome/codegenome.db` | Timeline snapshots (SQLite) |
| `.genome/graph.json` | Latest graph |
| `.genome/exports/` | HTML, Markdown, GraphML, etc. |
| `.genome/scan_cache.db` | Incremental scan cache |

Override the database with `--db-path` on the legacy CLI, or pass `--db-path` to `python -m codegenome.mcp_server`.

---

## Modern CLI (`codegenome`)

Install with `pip install codegenome`, then:

```bash
codegenome --help
```

### `analyze`

Build or incrementally update the knowledge graph.

```bash
codegenome analyze .
codegenome analyze /path/to/my-app
```

### `export`

Export the current graph. Requires a prior `analyze`.

```bash
codegenome export --format json --path .
codegenome export --format obsidian --path .
```

Supported formats in this subcommand: `json`, `html`, `cypher`, `obsidian`.

For `markdown`, `graphml`, and multi-format exports, use the [legacy CLI](#legacy-cli-python--m-codegenome).

### `evolve`

Run a live observer with a browser-based graph UI. Watches `.py` file changes and rebuilds incrementally.

```bash
codegenome evolve .
codegenome evolve --live .
codegenome evolve --live --lan .
```

With `--live`, a WebSocket server broadcasts graph updates. The UI is served at `http://localhost:8000/graph.html?live=1`.

With `--lan`, HTTP and WebSocket bind to all interfaces (`0.0.0.0`) so other devices on the same network can open the graph. The CLI prints a shareable LAN URL (for example `http://192.168.1.42:8000/graph.html?live=1`). Use `--live --lan` together for real-time updates on remote viewers.

### `mcp-start`

Start the MCP server over **stdio** for the given workspace.

```bash
codegenome mcp-start .
```

For HTTP MCP on port `7331`, use the [legacy CLI](#mcp-via-legacy-cli) or [standalone MCP server](mcp-integration.md#standalone-mcp-server).

### `rules`

Generate agent instruction files (Cursor rules, Copilot instructions, `AGENTS.md`, etc.).

```bash
codegenome rules .
codegenome rules --client cursor --client copilot --port 7331 .
codegenome rules --dry-run .
```

Clients: `cursor`, `copilot`, `windsurf`, `agents`, or `all` (default when omitted).

### `tui`

Launch the interactive terminal dashboard.

```bash
codegenome tui
```

From the TUI you can start live graph observation in two modes:

- **Live Evolve (Local)** — graph UI and WebSocket on localhost only
- **Live Evolve (LAN)** — exposes HTTP and WebSocket on the local network so other devices can view the graph
- **Quit** — stops any background processes and exits the TUI

---

## Legacy CLI (`python -m codegenome`)

The flag-based interface supports watch mode, HTTP MCP, timeline queries, metrics, and every export format.

```bash
python -m codegenome --help
```

### Build and export

```bash
# Incremental build
python -m codegenome --workspace . --build

# Full rebuild
python -m codegenome --workspace . --build --full

# Custom exports (default: json, html, markdown)
python -m codegenome --workspace . --build --export json markdown graphml cypher obsidian
```

Supported export formats: `json`, `html`, `markdown`, `graphml`, `cypher`, `obsidian`.

### Watch and live graph

```bash
# Debounced rebuild on file changes (default debounce: 30s)
python -m codegenome --workspace . --build --watch --watch-debounce 10

# Poll file/line totals and rebuild when they increase
python -m codegenome --workspace . --build --live-graph --live-graph-interval 60
```

### Metrics

```bash
python -m codegenome --workspace . --print-metrics
# {"file_count": 142, "line_count": 18450}
```

### MCP via legacy CLI

```bash
python -m codegenome --workspace . --build --mcp --watch
```

Starts HTTP MCP on `127.0.0.1:7331` after build. For stdio or a custom port, use `python -m codegenome.mcp_server`.

### Timeline queries

JSON is printed to stdout. Requires at least one prior build.

```bash
python -m codegenome --workspace . --dump-timeline
python -m codegenome --workspace . --dump-timeline --node-id "file:src/main.py"
python -m codegenome --workspace . --dump-changes --snapshot-from 1 --snapshot-to 3
python -m codegenome --workspace . --dump-churn --churn-limit 10
```

### Legacy flag reference

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

**Requires at least one of:** `--build`, `--watch`, `--live-graph` (unless using query or metrics-only flags).

---

## Related modules

| Command | Purpose |
|---------|---------|
| `python -m codegenome.mcp_server …` | Standalone MCP (stdio or custom HTTP port) |
| `python -m codegenome.installer …` | Write MCP entries into AI client configs |

See [MCP integration](mcp-integration.md) and [Installation](installation.md).

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (details on stderr) |

---

## Common workflows

### Quick local analysis

```bash
codegenome analyze .
codegenome export --format html --path .
codegenome tui
```

### CI graph build

```bash
python -m codegenome --workspace . --build --export json
```

### Local dev with Cursor (HTTP MCP)

Terminal 1:

```bash
python -m codegenome --workspace . --build --mcp --watch
```

Terminal 2:

```bash
python -m codegenome.installer \
  --db-path "$(pwd)/.genome/codegenome.db" \
  --client cursor \
  --transport http
codegenome rules --client cursor .
```

Restart Cursor after installing MCP config and rules.
