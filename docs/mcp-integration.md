# MCP integration

Codegenome exposes your project's knowledge graph to AI coding assistants through a **local MCP server**. The default HTTP endpoint is `127.0.0.1:7331`.

Build the graph before connecting clients:

```bash
codegenome analyze .
```

## Quick setup (HTTP + watch)

Best for Cursor, Copilot (VS Code), and other HTTP-based clients.

```bash
# Terminal 1: build + MCP + watch
python -m codegenome --workspace . --build --mcp --watch

# Terminal 2: install client config
python -m codegenome.installer \
  --db-path "$(pwd)/.genome/codegenome.db" \
  --client cursor \
  --transport http \
  --host 127.0.0.1 \
  --port 7331

# Optional: generate agent rules in the workspace
codegenome rules --client cursor --port 7331 .
```

Restart your AI client after installation.

## Stdio setup

Best for Claude Desktop and agents that spawn an MCP subprocess.

```bash
codegenome analyze .
codegenome mcp-start .
```

Or configure clients to run the module directly:

```bash
python -m codegenome.mcp_server \
  --db-path ./.genome/codegenome.db \
  --transport stdio
```

Use `python -m codegenome.installer --transport stdio` when writing client config for stdio mode.

## Standalone MCP server

```bash
python -m codegenome.mcp_server --help

# HTTP
python -m codegenome.mcp_server \
  --db-path ./.genome/codegenome.db \
  --host 127.0.0.1 \
  --port 7331 \
  --transport http

# Stdio
python -m codegenome.mcp_server \
  --db-path ./.genome/codegenome.db \
  --transport stdio
```

## MCP config installer

```bash
python -m codegenome.installer --help
```

| Flag | Description |
|------|-------------|
| `--db-path PATH` | Absolute path to `.genome/codegenome.db` |
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

Always use **absolute paths** for `--db-path`.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CODEGENOME_MCP_DB_PATH` | `test.db` | Database path |
| `CODEGENOME_MCP_HOST` | `127.0.0.1` | HTTP bind host |
| `CODEGENOME_MCP_PORT` | `7331` | HTTP bind port |
| `CODEGENOME_MCP_TRANSPORT` | `http` | `http` or `stdio` |
| `CODEGENOME_MCP_TIMEOUT` | `30` | Tool timeout (seconds) |
| `CODEGENOME_MCP_LOG_LEVEL` | `INFO` | Log level |

## Health check

```bash
curl http://127.0.0.1:7331/health
curl http://127.0.0.1:7331/mcp/activity
```

## AI rules (Cursor / Copilot / AGENTS.md)

Generate rules with the CLI:

```bash
codegenome rules --client all --port 7331 .
```

Templates also live in [`extensions/templates/`](../extensions/templates/). See [Extensions README](../extensions/README.md).

Manual Cursor rule install:

```bash
mkdir -p .cursor/rules
sed 's/{{MCP_PORT}}/7331/g' extensions/templates/codegenome-knowledge-graph.mdc \
  > .cursor/rules/codegenome-knowledge-graph.mdc
```

On Windows PowerShell, copy the template and replace `{{MCP_PORT}}` with `7331` manually or use your editor's find-and-replace.

## MCP tools (summary)

Agents can call tools such as:

- `search_nodes` — find symbols by name or path
- `get_neighbors` — imports, callers, callees
- `get_entry_points`, `get_dead_code`, `get_circular_deps`, `get_god_nodes`
- `get_complexity`, `get_churn`
- `get_graph`, `get_timeline`, `get_changes`

Build the graph before expecting rich tool results:

```bash
codegenome analyze .
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused | Run HTTP MCP (`python -m codegenome --mcp --build --watch`) or `mcp_server`; ensure the graph was built |
| Port 7331 in use | Stop the other instance or run `mcp_server --port 7332` and update client config |
| Empty tool results | Run `codegenome analyze .` first; confirm `.genome/codegenome.db` exists |
| Client not using MCP | Restart the client after `installer`; verify the config file path |
| Stdio vs HTTP mismatch | Match `--transport` in `installer` with how the server is started |

See also [CLI reference](cli-reference.md) and [Installation](installation.md).
