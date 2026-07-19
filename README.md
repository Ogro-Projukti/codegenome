<div align="center">
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/header.png" alt="Codegenome Header" width="100%" />

  <br />

  <h1>Codegenome</h1>

  <p>
    <strong>Turn your codebase into a living knowledge graph.</strong> An MCP server using tree-sitter to stream high-fidelity architectural context to Cursor and Claude.
  </p>

  <p>
    <a href="https://codegenome.pages.dev/"><img src="https://img.shields.io/badge/docs-website-blue?style=flat-square" alt="Documentation"></a>
    <a href="https://pypi.org/project/codegenome/"><img src="https://img.shields.io/badge/pypi-codegenome-blue?style=flat-square&logo=pypi&logoColor=white" alt="PyPI"></a>
    <a href="https://github.com/Ogro-Projukti/codegenome/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License"></a>
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

### 🖥️ Rich Terminal User Interface (TUI)
Interact with your codebase's architecture and timeline effortlessly through our built-in terminal UI. Explore connections and insights without ever leaving your terminal. **For the best and most intuitive user experience (UX), we highly recommend using the TUI.**

To launch the TUI, simply run:
```bash
codegenome tui
```

<div align="center">
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/new-v_014/tui-view-1-wp-set.png" alt="TUI Workspace Settings" width="48%" />
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/new-v_014/tui-view-2-wp-info.png" alt="TUI Workspace Info" width="48%" />
  <br />
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/new-v_014/tui-main-panel.png" alt="TUI Main Panel" width="48%" />
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/new-v_014/tui-config.png" alt="TUI Configuration" width="48%" />
</div>

### ⚡ Live Graph Visualization & Watch Mode
Keep your codebase intelligence fresh in real-time. As you write code, Codegenome watches your workspace and automatically updates the graph, so your agents and queries are never out of sync.

<div align="center">
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/new-v_014/ai-chat-live-graph.png" alt="AI Chat Live Graph" width="80%" />
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

Use `codegenome export --format <name>` for `json`, `html`, `markdown`, `graphml`, `cypher`, and `obsidian`. Repeat `--format` to export more than one format.

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

# Share the live graph with other devices on your LAN (v0.1.4+)
codegenome evolve --live --lan .
```

> **Note**: For detailed CLI reference, installation guides, and MCP setup, see our comprehensive [Documentation](#-documentation).

## 🛠️ Troubleshooting

### 1. "No graph found" or Missing Database
**Symptom:** When attempting to run the MCP server (`codegenome mcp-start`) or export the graph (`codegenome export`), you receive an error that no graph was found or `.genome/codegenome.db` does not exist.
**Solution:** Codegenome needs to build its initial knowledge graph database before it can be served or exported. Always run `codegenome analyze .` in your workspace first to generate the graph.

### 2. "unrecognized arguments" CLI Error
**Symptom:** Older instructions use removed top-level flags such as `--workspace` or `--build`.
**Solution:** Use the unified subcommands (`codegenome analyze .`, `codegenome mcp-start`, `codegenome timeline`, or `codegenome tui`). `python -m codegenome` exposes the same interface. See the migration table in the CLI reference.

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| 📖 [CLI reference](docs/cli-reference.md) | Unified commands, options, and migration table |
| ⚙️ [Installation](docs/installation.md) | pip, venv, MCP setup |
| 🔌 [MCP integration](docs/mcp-integration.md) | Server modes and client installer |
| 📦 [Release guide](docs/releasing.md) | TestPyPI, PyPI Trusted Publishing, versioning |
| ⚖️ [License compliance](docs/license-compliance.md) | GPL dependency review and release gate |
| ✅ [Phase 2 readiness](docs/phase-2-readiness.md) | Packaging checklist and remaining owner gates |
| 🧩 [Extensions](extensions/README.md) | Cursor rules and Copilot templates |
| 🤝 [Contributing](CONTRIBUTING.md) | Development setup, tests, pull requests |

## ⚖️ License

Codegenome's original source is licensed under the **[MIT License](https://github.com/Ogro-Projukti/codegenome/blob/main/LICENSE)**. Required graph dependencies include GPL-licensed igraph and Leiden; distributors should read the [license compliance review](docs/license-compliance.md).

<div align="center">
  <br />
  <img src="https://raw.githubusercontent.com/Ogro-Projukti/codegenome/main/assets/logo.png" alt="Codegenome Logo" width="100" />
</div>
