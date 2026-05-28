# MCP integration

Watcher exposes your project's knowledge graph to AI coding assistants through a **local MCP server** on `127.0.0.1:7331` (HTTP by default).

## Quick setup

```bash
# Terminal 1: build + MCP + watch
watcher --workspace . --build --mcp --watch

# Terminal 2: install client config
python -m codegenome.installer \
  --db-path "$(pwd)/.watcher/watcher.db" \
  --client cursor \
  --transport http \
  --host 127.0.0.1 \
  --port 7331
```

Restart your AI client after installation.

## Standalone MCP server

```bash
python -m codegenome.mcp_server --help

# HTTP
python -m codegenome.mcp_server \
  --db-path ./.watcher/watcher.db \
  --host 127.0.0.1 \
  --port 7331 \
  --transport http

# Stdio (Claude Desktop, some CLI agents)
python -m codegenome.mcp_server \
  --db-path ./.watcher/watcher.db \
  --transport stdio
```

## MCP config installer

```bash
python -m codegenome.installer --help
```

| Flag | Description |
|------|-------------|
| `--db-path PATH` | Absolute path to `.watcher/watcher.db` |
| `--python PATH` | Python executable for stdio transport |
| `--transport stdio\|http` | Config transport mode |
| `--host HOST` | HTTP host in config |
| `--port PORT` | HTTP port in config |
| `--client KEY` | Limit to one client (repeatable) |
| `--dry-run` | Print paths only |

**Clients:** `claude`, `cursor`, `codex`, `gemini`, `aider`, `windsurf`, `copilot`.

| Client | Config file |
|--------|-------------|
| Cursor | `~/.cursor/mcp.json` |
| Copilot (VS Code) | `.vscode/mcp.json` (workspace) |
| Claude Desktop | OS-specific Claude config |
| Codex | `~/.codex/mcp.json` |
| Gemini | `~/.gemini/mcp.json` |
| Aider | `~/.aider/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |

Use **absolute paths** for `--db-path`.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WATCHER_MCP_DB_PATH` | `test.db` | Database path |
| `WATCHER_MCP_HOST` | `127.0.0.1` | HTTP bind host |
| `WATCHER_MCP_PORT` | `7331` | HTTP bind port |
| `WATCHER_MCP_TRANSPORT` | `http` | `http` or `stdio` |
| `WATCHER_MCP_TIMEOUT` | `30` | Tool timeout (seconds) |
| `WATCHER_MCP_LOG_LEVEL` | `INFO` | Log level |

## Health check

```bash
curl http://127.0.0.1:7331/health
curl http://127.0.0.1:7331/mcp/activity
```

## AI rules (Cursor / Copilot)

Templates live in [`extensions/templates/`](../extensions/templates/). See [Extensions README](../extensions/README.md).

Manual Cursor rule install:

```bash
mkdir -p .cursor/rules
sed 's/{{MCP_PORT}}/7331/g' extensions/templates/watcher-knowledge-graph.mdc \
  > .cursor/rules/watcher-knowledge-graph.mdc
```

## MCP tools (summary)

Agents can call tools such as:

- `search_nodes` — find symbols by name or path
- `get_neighbors` — imports, callers, callees
- `get_entry_points`, `get_dead_code`, `get_circular_deps`, `get_god_nodes`
- `get_complexity`, `get_churn`
- `get_graph`, `get_timeline`, `get_changes`

Build the graph before expecting rich tool results:

```bash
watcher --workspace . --build
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused | Run `watcher --mcp` or `mcp_server`; ensure graph was built |
| Port 7331 in use | Stop other instance or `mcp_server --port 7332` |
| Empty tool results | Run `--build` first; check `.watcher/watcher.db` exists |
| Client not using MCP | Restart client after `installer`; verify config path |
