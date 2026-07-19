# CLI reference

CodeGenome has one Click command group. The installed console script and module
entry point are equivalent:

```bash
codegenome --help
python -m codegenome --help
```

Both forms operate on a workspace, defaulting to the current directory. Runtime
data lives under `<workspace>/.genome/` unless a command accepts `--db-path`.

## Commands

| Command | Purpose |
|---|---|
| `analyze` | Build or update a graph; optionally watch, serve MCP, or export multiple formats |
| `export` | Export an existing graph in one or more formats |
| `evolve` | Observe changes continuously and optionally serve the live web UI |
| `mcp-start` | Serve the graph over stdio or HTTP |
| `install-mcp` | Write MCP entries into supported client configuration files |
| `metrics` | Print workspace file and line totals as JSON |
| `timeline` | Print snapshot or node history as JSON |
| `changes` | Print a delta between two snapshots as JSON |
| `churn` | Print repository or file churn as JSON |
| `db-maintain` | Prune snapshots and optionally compact SQLite |
| `rules` | Generate CodeGenome-managed agent instruction sections |
| `tui` | Launch the Textual dashboard |

Set global logging before the command, for example
`codegenome --log-level DEBUG analyze .`.

## Analyze

```bash
# Incremental build with the default JSON export
codegenome analyze .

# Full rebuild and several export formats
codegenome analyze --full \
  --format json --format html --format markdown --format graphml .

# Memory-bounded watch mode
codegenome analyze --memory-bounded --max-working-files 64 \
  --watch --watch-debounce 10 .

# Build, start loopback HTTP MCP, and watch
codegenome analyze --mcp --watch .
```

Analysis retains the newest 100 snapshots by default. Change that with
`--retain-snapshots` and optionally add `--retention-days`.

Supported exports are `json`, `html`, `markdown`, `graphml`, `cypher`, and
`obsidian`. Repeat `--format` to select more than one.

## Export

Run `analyze` first, then export any supported set:

```bash
codegenome export --path . --format html
codegenome export --path . --format graphml --format obsidian
```

## Live observation

```bash
codegenome evolve .
codegenome evolve --live .
codegenome evolve --live --lan .
codegenome evolve --live --memory-bounded --retain-snapshots 100 .
```

Without `--lan`, services bind to loopback. `--lan` requires `--live`, binds to
all interfaces, and should be used only on a trusted network because the live
graph and AI routes do not authenticate clients.

## MCP server and client configuration

```bash
# Stdio (default)
codegenome mcp-start --path .

# Memory-bounded loopback HTTP
codegenome mcp-start --path . --transport http --port 7331 --memory-bounded

# Preview a Cursor HTTP configuration
codegenome install-mcp --client cursor --transport http --dry-run .

# Install a stdio configuration
codegenome install-mcp --client claude --transport stdio .
```

HTTP binds to `127.0.0.1` unless `--lan` is supplied. Client values are
`claude`, `cursor`, `codex`, `gemini`, `aider`, `windsurf`, and `copilot`.

## Metrics and timeline queries

All query output is JSON and errors are written to stderr.

```bash
codegenome metrics .
codegenome timeline --path .
codegenome timeline --path . --node-id "file:src/main.py"
codegenome changes --path . --snapshot-from 1 --snapshot-to 3
codegenome churn --path . --limit 10
codegenome churn --path . --file src/main.py
```

Use `--db-path /absolute/path/codegenome.db` on `timeline`, `changes`, `churn`,
`export`, or `mcp-start` when the database is outside the workspace default.

## Database maintenance

```bash
codegenome db-maintain --path . --retain-snapshots 100
codegenome db-maintain --path . --retain-snapshots 50 --max-age-days 30 --compact
```

The newest snapshot is protected. `--compact` runs SQLite `VACUUM`; schedule it
when no long-running CodeGenome service is using the database.

## Agent rules and TUI

```bash
codegenome rules --client cursor --client copilot --port 7331 .
codegenome rules --dry-run .
codegenome tui
```

Rule generation updates only a CodeGenome-managed section and backs up an
existing file before changing it.

## Migration from the alpha flag interface

The parallel argparse front door was removed in 0.2.0. Use these replacements:

| Removed invocation | Unified command |
|---|---|
| `--workspace PATH --build` | `analyze PATH` |
| `--build --full` | `analyze --full PATH` |
| `--build --export FMT ...` | repeated `analyze --format FMT PATH` |
| `--build --watch` | `analyze --watch PATH` |
| `--print-metrics` | `metrics PATH` |
| `--dump-timeline` | `timeline --path PATH` |
| `--dump-changes --snapshot-from A --snapshot-to B` | `changes --path PATH --snapshot-from A --snapshot-to B` |
| `--dump-churn` | `churn --path PATH` |
| `python -m codegenome.installer ...` | `install-mcp ...` |
| `python -m codegenome.mcp_server ...` | `mcp-start ...` |

Do not mix removed top-level flags with subcommands. `python -m codegenome` now
uses the same commands and options as the console script.
