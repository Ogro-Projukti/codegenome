# Changelog

All notable changes to Codegenome are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-06-01

### Added

- **LAN live graph sharing** — `codegenome evolve --live --lan` binds HTTP and WebSocket to `0.0.0.0` so other devices on the same network can open the live graph. The CLI prints a shareable LAN URL (for example `http://192.168.1.42:8000/graph.html?live=1`).
- **Git-aware file filtering** — the scanner respects workspace `.gitignore` and `.genomeignore` files, including nested ignore files in subdirectories, negation rules (`!pattern`), and anchored patterns.
- **TUI workspace info page** — after setting a workspace, the TUI shows tracked folders, file extensions, and discovered `.gitignore` files before you run analyze or evolve.
- **TUI live-evolve controls** — buttons for **Live Evolve (Local)**, **Live Evolve (LAN)**, and **Quit** to start or stop background processes from the dashboard.
- **Live graph AI chat** — the HTML graph UI includes an in-browser chat panel backed by OpenAI, Google Gemini, Groq, Ollama (local), and Ollama Cloud. API keys are stored under `.genome/ai-chat.json` and never echoed back to the browser.
- **Graph context profiles for AI chat** — selectable context sizes (`minimal`, `small`, `medium`, `full`, `max`) control how much neighborhood data is sent with each prompt.
- **MCP `query_graph` tool** — filter graph nodes by type, file path prefix, or symbol kind.
- **`codegenome mcp-start --transport` and `--port`** — start the MCP server over stdio (default) or HTTP from the modern CLI and TUI.
- **`pathspec` dependency** — powers gitignore-compatible pattern matching.

### Changed

- Default ignore list always excludes `.git/`, `.venv/`, `node_modules/`, `__pycache__/`, `*.pyc`, `.genome/`, and `.genomeignore` in addition to workspace ignore files.
- MCP server refreshes the latest timeline snapshot before tool reads so agents always see current graph data after `analyze` or live evolve.
- Agent instruction templates (`codegenome rules`) now direct agents to use native MCP tools instead of raw HTTP/curl calls.

### Fixed

- MCP tool handlers return richer graph intelligence data (dead code, entry points, complexity, churn) with improved filtering for generated assets and public API symbols.
- Agent rules no longer reference misleading HTTP endpoints that caused agents to `curl` the server instead of using MCP transport.

### Documentation

- CLI reference covers `--lan`, TUI live modes, ignore-rule behavior, and MCP transport options.
- README quick start includes the LAN evolve example.
- Release notes and upgrade instructions in `docs/release-0.1.4.md`.

[0.1.4]: https://github.com/Ogro-Projukti/codegenome/releases/tag/v0.1.4
