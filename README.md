<div align="center">
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/header.png" alt="Codegenome Header" width="100%" />

  <br />

  <h1>Codegenome</h1>

  <p>
    <strong>Turn your codebase into a living knowledge graph.</strong> An MCP server using tree-sitter to stream high-fidelity architectural context to Cursor and Claude.<br>
    🌍 <strong>Website:</strong> <a href="https://codegenome.pages.dev/">codegenome.pages.dev</a>
  </p>

  <p>
    <a href="https://github.com/Ogro-Projukti/codegenome/actions"><img src="https://img.shields.io/github/actions/workflow/status/Ogro-Projukti/codegenome/main.yml?style=flat-square" alt="Build Status"></a>
    <a href="https://pypi.org/project/codegenome/"><img src="https://img.shields.io/pypi/v/codegenome?style=flat-square" alt="PyPI Version"></a>
    <a href="https://github.com/Ogro-Projukti/codegenome/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Ogro-Projukti/codegenome?style=flat-square" alt="License"></a>
  </p>
</div>


## 🌐 The Connectome of Code: Mapping the Digital Brain

Your codebase isn't a static document—it's an evolving digital brain. Standard context tools dump flat, truncated text files into your LLM window, causing massive token bloat and architectural hallucinations. 

**Codegenome treats code like a living connectome.** By running localized, incremental `tree-sitter` passes and tracking changes in SQLite, it monitors your repository's structural neuroplasticity in real time—without dragging down system performance.

### ⚡ Watch your connectome grow as your agent codes
As your AI agent (**Cursor, Claude Desktop, or custom MCP clients**) generates new modules, refactors functions, or shifts dependencies, Codegenome maps out those structural relationships instantly. It exposes high-fidelity intelligence directly to your editor via the **Model Context Protocol (MCP)**, allowing AI agents to reason about your entire system architecture with surgical precision. Use it headless in CI, on servers, or locally—no complex IDE wrappers required.


## ✨ What Codegenome Can Do

### 🧠 Codebase Intelligence & Graph Building
Codegenome deeply understands your code. It parses your source files, incrementally builds a knowledge graph, and outputs structured intelligence. Whether you're querying for dependencies or analyzing churn, Codegenome provides the structural truth of your codebase.

### ⚡ Live Graph Visualization & Watch Mode
Keep your codebase intelligence fresh in real-time. As you write code, Codegenome watches your workspace and automatically updates the graph, so your agents and queries are never out of sync.

<div align="center">
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/live-graph-1.png" alt="Live Graph Visualization" width="48%" />
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/live-graph-2.png" alt="Live Graph Detail" width="48%" />
</div>

### 🖥️ Rich Terminal User Interface (TUI)
Interact with your codebase's architecture and timeline effortlessly through our built-in terminal UI. Explore connections and insights without ever leaving your terminal. **For the best and most intuitive user experience (UX), we highly recommend using the TUI.**

To launch the TUI, simply run:
```bash
codegenome tui
```

<div align="center">
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/tui.png" alt="Codegenome TUI" width="80%" />
</div>

### 🤖 Seamless AI Agent Integration via MCP
Codegenome doesn't just build graphs; it acts as an intelligence server for your AI agents (Cursor, Claude, Copilot, etc.). Via HTTP or stdio transport, it serves as a high-fidelity context provider.

### 📤 Versatile Exports
Need your graph in a different format? Codegenome seamlessly exports to:
- **JSON**
- **HTML & Markdown**
- **GraphML**
- **Cypher** (for Neo4j)
- **Obsidian** (for personal knowledge bases)

Use `codegenome export --format <name>` for `json`, `html`, `cypher`, and `obsidian`. Additional formats are available through the [legacy CLI](docs/cli-reference.md#legacy-cli-python--m-codegenome).

## 🚀 Quick Start

Get up and running in seconds.

```bash
# Install via pip
pip install codegenome

# Build your first graph in any project directory
cd /path/to/your/project
codegenome analyze .

# Export your graph
codegenome export --format obsidian --path .

# Run in watch mode with live graph web UI
codegenome evolve --live .
```

> **Note**: For detailed CLI reference, installation guides, and MCP setup, see our comprehensive [Documentation](#-documentation).

## 🛠️ Troubleshooting

### 1. "No graph found" or Missing Database
**Symptom:** When attempting to run the MCP server (`codegenome mcp-start`) or export the graph (`codegenome export`), you receive an error that no graph was found or `.genome/watcher.db` does not exist.
**Solution:** Codegenome needs to build its initial knowledge graph database before it can be served or exported. Always run `codegenome analyze .` in your workspace first to generate the graph.

### 2. "unrecognized arguments" CLI Error
**Symptom:** You try to run commands and receive an `unrecognized arguments` error (e.g., mixing `--workspace` flags with `export` subcommands).
**Solution:** The unified CLI (`codegenome`) uses modern subcommands (e.g., `codegenome analyze .`, `codegenome mcp-start`, `codegenome tui`). If you are following older documentation that uses flags like `--workspace . --build`, you must invoke the Python module directly using `python -m codegenome --workspace . --build`. Avoid mixing the modular subcommands with the legacy flag-based CLI.

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| 📖 [CLI reference](docs/cli-reference.md) | Subcommands, legacy flags, workflows |
| ⚙️ [Installation](docs/installation.md) | pip, venv, MCP setup |
| 🔌 [MCP integration](docs/mcp-integration.md) | Server modes and client installer |
| 🧩 [Extensions](extensions/README.md) | Cursor rules and Copilot templates |
| 🤝 [Contributing](CONTRIBUTING.md) | Development setup, tests, pull requests |

## ⚖️ License

Codegenome is open-source software licensed under the **[MIT License](https://github.com/Ogro-Projukti/codegenome/blob/main/LICENSE)**.

<div align="center">
  <br />
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/logo.png" alt="Codegenome Logo" width="100" />
</div>
