# Developer onboarding

> **TL;DR:** A contributor can understand and run CodeGenome quickly from README and CONTRIBUTING, but the declared development extras are missing the async test plugin and several tracked references/configurations are stale. The path below is the audit-verified workflow, with the current caveats made explicit.

## First 30 minutes

Prerequisites are Python 3.11–3.13 and Git; a C compiler may be needed if graph/parser wheels are unavailable (`CONTRIBUTING.md:35-42`). Python 3.14 is not currently listed in package classifiers (`pyproject.toml:19-22`).

```powershell
git clone https://github.com/Ogro-Projukti/codegenome.git
Set-Location codegenome
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install pytest-asyncio  # temporary: missing from dev extras at audited commit
python -m pytest -q
python -m ruff check src tests
codegenome --help
```

Expected at the audited commit:

- tests: 196 pass when `pytest-asyncio` is present;
- Ruff: seven existing `F401` failures, listed in [`10-TECHNICAL-DEBT.md`](./10-TECHNICAL-DEBT.md);
- no application service or external API is needed for ordinary unit tests.

The documented editable-install/test/lint flow is in `CONTRIBUTING.md:43-75` and `:106-147`. Until dependency metadata is fixed, treat the explicit async-plugin step and the known lint baseline above as temporary deviations, not desired long-term instructions.

## Understand the code in this order

1. Product intent and modes: `README.md:8-103`.
2. Thin public facade and component ownership: `src/codegenome/core.py:1-39`, `src/codegenome/engine/context.py:19-75`.
3. Full pipeline: `src/codegenome/engine/build_service.py:22-103`.
4. Graph creation: `src/codegenome/scanner.py`, `src/codegenome/parser/`, `src/codegenome/builder.py`.
5. Persistence/query: `src/codegenome/timeline.py`, `src/codegenome/graph_store.py`.
6. Interfaces: `src/codegenome/cli.py`, `src/codegenome/mcp_tools/`, `src/codegenome/live_session.py`.
7. Visual metaphor: `src/codegenome/serializers/` and browser assets.

Use [`02-ARCHITECTURE-OVERVIEW.md`](./02-ARCHITECTURE-OVERVIEW.md) and [`04-MODULE-AND-COMPONENT-CATALOG.md`](./04-MODULE-AND-COMPONENT-CATALOG.md) as maps rather than reading every file.

## Safe local usage

```powershell
# Build/refresh this repository's graph.
codegenome analyze --memory-bounded .

# Start memory-bounded MCP over stdio for an editor.
codegenome mcp-start --path . --memory-bounded

# Run the TUI.
codegenome tui
```

The README’s quick start is at `README.md:71-91`. Do not mix the installed Click command with legacy `python -m codegenome` flags (`README.md:95-103`).

For live visualization, bind only to loopback until BUG-01 is fixed. The audited code accidentally wildcard-binds the live HTTP server even without LAN mode (`src/codegenome/live_session.py:266-272`); rely on an OS firewall or avoid starting it on an untrusted network.

## MCP setup

The preferred portable project configuration is conceptually:

```json
{
  "mcpServers": {
    "codegenome": {
      "command": "codegenome",
      "args": ["mcp-start", "--path", "${workspaceFolder}", "--memory-bounded"]
    }
  }
}
```

The tracked `.cursor/mcp.json:1-13` instead hard-codes another developer’s Windows path; replace it locally or fix the tracked file in a dedicated change. Do not launch duplicate unbounded MCP processes for the same workspace.

## Development workflow

- Create a focused branch, add behavior tests first for defects, and keep commits narrow; project conventions are at `CONTRIBUTING.md:176-223`.
- Run full tests and Ruff locally, not only parser tests.
- If modifying persistence, verify old/new schema paths, `PRAGMA integrity_check`, and node/edge round-trip invariants.
- If modifying network code, test loopback/LAN addresses, authentication/origin controls, and body/message limits on all supported operating systems.
- If modifying public commands or MCP tools, update CLI/MCP docs and include compatibility notes.
- After code changes, run a full `codegenome analyze` to refresh global snapshot metrics; patch builds can retain stale metrics (`update-doc/memory-bounded-storage-current-capabilities.md:251-259`).

## Packaging and deployment caveats

- There is no supported production deployment/runbook in the repository.
- `build_cli.py` is a local PyInstaller helper, not a signed/reproducible release pipeline.
- There are no tags or GitHub releases at the audited baseline.
- Project URL metadata is stale (`pyproject.toml:55-59`).
- GPL graph dependencies require a distribution-license review before shipping bundled artifacts; see [`07-DEPENDENCIES.md`](./07-DEPENDENCIES.md).

## Troubleshooting

| Symptom | Likely cause/action |
|---|---|
| Three async tests fail or marks are unknown | install `pytest-asyncio`; then fix `pyproject.toml` in the product |
| MCP graph is empty/unbounded unexpectedly | rerun full analysis and ensure one memory-bounded server points to this workspace |
| Global intelligence looks stale after watch update | run `codegenome analyze --memory-bounded .` |
| `.genome` consumes gigabytes | no retention exists yet; back up before manual state removal/rebuild |
| Cursor MCP executable not found | tracked config contains a machine-specific path |
| Rules command would target an existing instructions file | do not run without a backup until marker-based preservation lands |

`DEVELOPER_TESTING.md` is empty at this commit; use CONTRIBUTING plus this audit until it is replaced with verified instructions.
