# Changelog

## [0.1.4] - 2026-05-31

### Added

- LAN live graph sharing via `codegenome evolve --live --lan`
- Git-aware scanning (`.gitignore`, `.genomeignore`, nested rules)
- TUI workspace info page and Live Evolve (Local / LAN) controls

### Changed

- Scanner skips default paths (`.git/`, `.venv/`, `node_modules/`, etc.) plus workspace ignore files

### Fixed

- **MCP Server**: Added `--transport` and `--port` options to `codegenome mcp-start` (and TUI) so that it can be explicitly started in HTTP mode instead of defaulting to `stdio`.
- **AI Rules**: Removed misleading HTTP endpoints from `.cursorrules` and other agent instructions that caused agents to mistakenly `curl` the server. Instructions now properly tell agents to use the native MCP integration tools.
