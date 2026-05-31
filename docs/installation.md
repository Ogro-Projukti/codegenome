# Installation

Install **Codegenome** with pip into a virtual environment (recommended).

## Requirements

- Python **3.11+**
- **Git** (for development installs)
- A C compiler may be required on some platforms for `python-igraph` / `leidenalg`

## Production install (PyPI)

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install codegenome
```

Verify:

```bash
codegenome --help
python -c "import codegenome; print(codegenome.__version__)"
```

TestPyPI:

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ codegenome
```

## Editable install (development)

From this repository root:

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# macOS / Linux
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify the same way as above. For contribution workflow, tests, and linting, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## First graph build

Point Codegenome at **your project directory** (the repo you want to analyze):

```bash
cd ~/projects/my-app
codegenome analyze .
```

Codegenome writes artifacts under `<workspace>/.genome/`:

| Path | Purpose |
|------|---------|
| `.genome/graph.json` | Latest graph |
| `.genome/watcher.db` | Timeline snapshots (SQLite) |
| `.genome/exports/` | HTML, Markdown, GraphML, etc. |
| `.genome/scan_cache.db` | Incremental scan cache |

Export after building:

```bash
codegenome export --format json --path .
```

## MCP setup

Build the graph first (`codegenome analyze .`). Then choose a transport:

### HTTP (Cursor and most editor clients)

**Terminal 1** — build, watch, and start HTTP MCP on `127.0.0.1:7331`:

```bash
python -m codegenome --workspace . --build --mcp --watch
```

**Terminal 2** — write client config (one time):

```bash
python -m codegenome.installer \
  --db-path "$(pwd)/.genome/watcher.db" \
  --client cursor \
  --transport http \
  --host 127.0.0.1 \
  --port 7331
```

Health check:

```bash
curl http://127.0.0.1:7331/health
```

Restart your AI client after installing MCP config.

### Stdio (Claude Desktop and some CLI agents)

```bash
codegenome analyze .
codegenome mcp-start .
```

Or run the standalone server module:

```bash
python -m codegenome.mcp_server \
  --db-path ./.genome/watcher.db \
  --transport stdio
```

See [MCP integration](mcp-integration.md) for environment variables, supported clients, and agent rules.

## Optional: standalone binary

To build a PyInstaller binary named `watcher` in `dist/` (requires the `dev` extra):

```bash
python build_cli.py
```

This is optional. The default PyPI entry point is the `codegenome` command.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `codegenome: command not found` | Activate your venv or reinstall with `pip install codegenome` |
| `No graph found` on export/MCP | Run `codegenome analyze .` first |
| `igraph` build fails | Install platform build tools; on Windows, install MSVC Build Tools |
| Empty timeline dumps | Run `python -m codegenome --workspace . --build` first |
| Port 7331 in use | Stop the other MCP instance or pass `--port` to `mcp_server` |
| Mixed CLI errors | Use subcommands (`codegenome analyze`) or legacy flags (`python -m codegenome --build`), not both in one invocation |

## Next steps

| Doc | Description |
|-----|-------------|
| [CLI reference](cli-reference.md) | Subcommands, legacy flags, workflows |
| [MCP integration](mcp-integration.md) | Server modes, installer, tools |
| [Extensions](../extensions/README.md) | Cursor rules and Copilot templates |
