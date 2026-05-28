# Installation

Install **Watcher CLI** with pip into a virtual environment (recommended).

## Requirements

- Python **3.11+**
- A C compiler may be required on some platforms for `python-igraph` / `leidenalg`

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

Verify:

```bash
watcher --help
python -c "import codegenome; print(codegenome.__version__)"
```

## Production install (PyPI)

Once published:

```bash
pip install codegenome
```

TestPyPI:

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ codegenome
```

## First graph build

Point Watcher at **your project directory** (the repo you want to analyze):

```bash
cd ~/projects/my-app
watcher --workspace . --build
```

Artifacts:

| Path | Purpose |
|------|---------|
| `.genome/graph.json` | Latest graph |
| `.genome/watcher.db` | Timeline snapshots |
| `.genome/exports/` | HTML, Markdown, etc. |

## MCP setup

**Terminal 1** — build + HTTP MCP:

```bash
watcher --workspace . --build --mcp --watch
```

**Terminal 2** — write client config (one time):

```bash
python -m codegenome.installer \
  --db-path "$(pwd)/.genome/watcher.db" \
  --client cursor \
  --transport http
```

Health check:

```bash
curl http://127.0.0.1:7331/health
```

Standalone MCP server (custom port or stdio):

```bash
python -m codegenome.mcp_server \
  --db-path ./.genome/watcher.db \
  --transport stdio
```

See [MCP integration](mcp-integration.md) for environment variables and client list.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `watcher: command not found` | Activate venv or use `python -m codegenome` |
| `igraph` build fails | Install build tools; on Windows try `pip install python-igraph` with MSVC Build Tools |
| Empty timeline dumps | Run `watcher --workspace . --build` first |
| Port 7331 in use | Stop other Watcher instance or use `--port` on `mcp_server` |
