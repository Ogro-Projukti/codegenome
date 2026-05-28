# Watcher CLI

Open-source command-line tool for building, exporting, and querying **local codebase knowledge graphs**. Watcher scans your repository, extracts symbols and relationships with tree-sitter, stores timeline snapshots in SQLite, and exposes the graph to AI agents through MCP.

Use it headless in CI, on servers, or alongside any editor — no VS Code required.

## Features

- **Graph builds** — incremental or full rebuilds with `.genome/graph.json` output
- **Watch & live modes** — keep the graph fresh as files change
- **Exports** — JSON, HTML, Markdown, GraphML, Cypher, Obsidian
- **Timeline & churn** — snapshot diffs and change rankings from SQLite
- **MCP server** — HTTP or stdio transport for Cursor, Claude, Copilot, and other agents

## Quick start

### Install (editable dev)

```bash
git clone https://github.com/your-org/codegenome.git
cd codegenome
python -m venv .venv

# Windows
.venv\Scripts\activate
pip install -e ".[dev]"

# macOS / Linux
source .venv/bin/activate
pip install -e ".[dev]"
```

### Build your first graph

```bash
cd /path/to/your/project
codegenome --workspace . --build
```

Output is written to `.genome/` in the project you analyze (not in the codegenome install directory).

### Verify

```bash
codegenome --help
python -m codegenome --help
```

## Common commands

```bash
# Full rebuild
codegenome --workspace . --build --full

# Watch mode with MCP for local AI agents
codegenome --workspace . --build --mcp --watch

# Export selected formats
codegenome --workspace . --build --export json markdown graphml

# Timeline query (requires prior build)
codegenome --workspace . --dump-timeline

# Install MCP config for Cursor
python -m codegenome.installer --db-path "$(pwd)/.genome/watcher.db" --client cursor
```

See [docs/cli-reference.md](docs/cli-reference.md) for the full command reference.

## PyPI dev install

When you publish to TestPyPI or PyPI:

```bash
pip install build
python -m build   # builds wheel + sdist (run from repo root; do not use build.py — use PyPA build)

# Local test install from wheel
pip install dist/codegenome-0.1.0-py3-none-any.whl

# TestPyPI (replace with your index URL / credentials)
pip install --index-url https://test.pypi.org/simple/ codegenome
```

Optional standalone binary (PyInstaller):

```bash
python build_binary.py
```

## Repository layout

```
codegenome/
├── src/codegenome/       # Python package (CLI, engine, MCP)
│   ├── assets/            # Bundled HTML graph viewer assets
├── tests/                 # pytest suite
├── docs/                  # Standalone CLI documentation
├── extensions/            # Editor/agent integration templates (see README there)
├── pyproject.toml
└── README.md
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

Run the CLI as a module during development:

```bash
python -m codegenome --workspace . --build
```

## Relationship to Watcher VS Code

This repository is the **standalone open-source CLI package** (`codegenome` on PyPI, import name `codegenome`).

The Watcher VS Code extension in the main monorepo may bundle a frozen binary built from the same engine. Editor-specific UI, IPC, and extension packaging stay in the extension repo; headless automation and CI use this CLI.

## Documentation

| Doc | Description |
|-----|-------------|
| [CLI reference](docs/cli-reference.md) | Flags, workflows, troubleshooting |
| [Installation](docs/installation.md) | pip, venv, MCP setup |
| [MCP integration](docs/mcp-integration.md) | Server modes and client installer |
| [Extensions](extensions/README.md) | Cursor rules and Copilot templates |

## License

MIT — see [LICENSE](LICENSE).
