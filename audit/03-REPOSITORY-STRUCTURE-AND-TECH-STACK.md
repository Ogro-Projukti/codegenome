# Repository structure and technology stack

> **TL;DR:** This is a Python 3.11+ package centered on tree-sitter, igraph/Leiden, SQLite, FastMCP/Starlette, Textual, and WebSockets, with small browser-side JavaScript/CSS assets. The repository is compact and navigable, but duplicate dependency/CLI paths, portable MCP configuration, and development documentation need consolidation.

## Tracked repository map

```text
codegenome/
├── .cursor/                  # project MCP config (currently machine-specific)
├── .github/workflows/        # compatibility CI
├── .vscode/                  # generic MCP config
├── assets/                   # README/project media
├── docs/                     # user CLI, TUI, MCP, release docs
├── extensions/templates/     # editor-agent rule templates
├── goal/                     # original product design documents
├── pivot/                    # visualization redesign notes
├── src/codegenome/
│   ├── engine/               # context, build/update/watch/process services
│   ├── exporter/             # six export writers and coordinator
│   ├── intelligence/         # structural and metric analyzers
│   ├── mcp_tools/            # MCP tools and custom routes
│   ├── parser/languages/     # Python, JS/TS, Go, Rust extractors
│   ├── serializers/          # genome/health/nucleotide payloads
│   ├── tui/                  # Textual screens, widgets, commands
│   ├── assets/               # browser JS/CSS
│   └── templates/            # interactive graph HTML template
├── tests/                    # 34 tracked test files
├── update-doc/               # implementation/capability notes
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── pyproject.toml
└── requirements.txt
```

Command evidence: `git ls-files` found 106 tracked files under `src`, 34 under `tests`, 11 under top-level `assets`, 8 under `update-doc`, 5 under `pivot`, and 4 under `docs`.

## Language and artifact inventory

| Artifact | Tracked count/size | Role |
|---|---:|---|
| Python | 131 files / 17,911 lines | package, tooling, tests |
| Browser JavaScript | 4 files / 2,058 lines | graph, karyotype, helix, structure views |
| Jinja HTML template | 1 file / 1,638 lines | standalone interactive graph exporter |
| CSS | 2 files / 960 lines | live/browser visualization |
| HTML | 1 file / 83 lines | live view shell |
| Markdown/config/assets | not treated as source LOC | documentation, policy, media |

Counts were produced from tracked files only; ignored local environments, caches, `dist/`, and the 4.2 GB `.genome` database were excluded.

## Runtime stack

| Concern | Technology | Evidence |
|---|---|---|
| Package/runtime | Python `>=3.11`; setuptools | `pyproject.toml:1-12` |
| Parsing | tree-sitter plus Python, JavaScript, TypeScript, Go, Rust grammar wheels | `pyproject.toml:26-38`; `src/codegenome/parser/__init__.py:42-80` |
| Graphs | python-igraph, NetworkX abstraction, Leiden community detection | `pyproject.toml:39-48`; `src/codegenome/clusterer.py:8-13`, `:87-99` |
| Persistence | Python SQLite, JSON attributes | `src/codegenome/timeline.py:805-839` |
| Agent/API | FastMCP, Starlette custom routes | `pyproject.toml:40`; `src/codegenome/mcp_server.py:84-197`; `src/codegenome/genome_routes.py:58-80` |
| Live updates | watchdog plus `websockets` | `pyproject.toml:39`, `:43`; `src/codegenome/live_server.py:33-116` |
| Terminal UI | Textual | `pyproject.toml:44`; `src/codegenome/tui/` |
| Browser UI | vanilla JS/CSS/HTML | `src/codegenome/assets/`; `src/codegenome/templates/graph.html.j2` |
| Validation/models | Pydantic | `pyproject.toml:49`; serializer models under `src/codegenome/serializers/` |

## Build, run, and test paths

| Purpose | Canonical command | Source |
|---|---|---|
| Install | `python -m pip install -e .` | `README.md:71-91` |
| Development install | `python -m pip install -e ".[dev]"` | `CONTRIBUTING.md:43-75` |
| Analyze | `codegenome analyze [PATH]` | `src/codegenome/cli.py:14-54` |
| Export | `codegenome export --format ...` | `src/codegenome/cli.py:57-102` |
| MCP | `codegenome mcp-start ...` | `src/codegenome/cli.py:105-168` |
| Live evolution | `codegenome evolve [PATH]` | `src/codegenome/cli.py:170-210` |
| Rules | `codegenome rules ...` | `src/codegenome/cli.py:213-273` |
| TUI | `codegenome tui` | `src/codegenome/cli.py:276-280` |
| Legacy CLI | `python -m codegenome` | `src/codegenome/__main__.py:17-137` |
| Tests/lint | `pytest`; `ruff check src tests` | `CONTRIBUTING.md:106-147` |

The package script points to the modern Click CLI (`pyproject.toml:61-62`), while `python -m` remains a separate argparse implementation. README warns against mixing the interfaces (`README.md:95-103`), confirming a deliberate but costly compatibility split.

## External services and data flows

- Git/GitHub is used for repository history and collaboration; no GitHub release or package-publish automation is present.
- Optional AI chat integrations support OpenAI, Gemini, Groq, and Ollama local/cloud (`src/codegenome/ai_chat.py:15-51`). These are runtime-configured, not required for analysis.
- No database server, queue, cache service, container platform, cloud deployment definition, analytics backend, or serverless runtime is tracked.
- FastMCP may operate over stdio or HTTP; live views use a separate local HTTP server and WebSocket server.

## Repository hygiene observations

- `.gitignore` covers environments, caches, coverage, build output, `.genome`, and `.env` (`.gitignore:1-27`).
- `.cursor/mcp.json:1-13` embeds an absolute developer-machine executable path, unlike the generic `.vscode/mcp.json`; this makes the tracked Cursor configuration non-portable.
- `DEVELOPER_TESTING.md` is empty, while test instructions live in `CONTRIBUTING.md`.
- `package-lock.json:1-6` declares no packages; it appears vestigial because browser assets have no Node build pipeline.
- `pyproject.toml:55-59` points project URLs at `codegenome-dev/codegenome`, while the audited remote is `Ogro-Projukti/codegenome`. **Confidence: high** from local Git remote plus GitHub repository metadata.
