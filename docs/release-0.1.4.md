# Release 0.1.4

## Highlights

- **LAN live graph** — share the evolving graph with devices on the same network
- **Ignore rules** — scans respect `.gitignore` and `.genomeignore`
- **TUI** — workspace info view and buttons for local/LAN live evolve
- **Live graph AI chat** — ask questions about your architecture from the browser UI (OpenAI, Gemini, Groq, Ollama, Ollama Cloud)
- **MCP improvements** — `query_graph` tool, live snapshot refresh, HTTP/stdio transport via `mcp-start`

## CLI

```bash
# LAN live graph
codegenome evolve --live --lan .

# MCP over HTTP (for editors that connect via URL)
codegenome mcp-start . --transport http --port 7331

# Generate agent rules
codegenome rules --client all .

# TUI
codegenome tui
```

## Upgrade

```bash
pip install --upgrade codegenome
python -c "import codegenome; print(codegenome.__version__)"
# Expected: 0.1.4
```

## Pre-release verification

| Check | Status |
|-------|--------|
| Tests (`pytest`) | 99 passed |
| Version in `src/codegenome/version.py` (the package metadata source) | `0.1.4` |
| Changelog updated | Yes |

## Publishing checklist

- [x] Remaining features merged
- [x] Tests pass (`pytest`)
- [x] Version bumped in `src/codegenome/version.py`
- [x] Changelog and release notes updated
- [ ] Tag `v0.1.4` and create GitHub Release
- [ ] Publish to PyPI

## GitHub Release body (copy/paste)

```markdown
## What's new in 0.1.4

### Live graph & TUI
- Share live graph updates on your LAN with `codegenome evolve --live --lan`
- TUI workspace info page and one-click local/LAN live evolve controls
- In-browser AI chat on the live graph UI (OpenAI, Gemini, Groq, Ollama, Ollama Cloud)

### Scanning
- Git-aware ignore rules via `.gitignore` and `.genomeignore`

### MCP
- New `query_graph` tool for filtering nodes by type, path, or symbol kind
- `codegenome mcp-start --transport http|stdio --port 7331`
- Server auto-refreshes to the latest snapshot before serving tool calls

### Upgrade
pip install --upgrade codegenome
```
