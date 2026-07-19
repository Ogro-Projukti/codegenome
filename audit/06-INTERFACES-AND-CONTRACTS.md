# Interfaces and contracts

> **TL;DR:** CodeGenome exposes a modern Click CLI, a legacy module CLI, an in-process Python service, six export formats, 15 MCP tools, custom REST endpoints, WebSocket subscriptions, and optional AI-provider calls. Several contracts are under-documented or inconsistent, and the network-facing surfaces lack the validation/authentication expected for non-loopback use.

## Command-line interfaces

| Interface | Commands/options | Contract source | Notes |
|---|---|---|---|
| Installed `codegenome` | `analyze`, `export`, `mcp-start`, `evolve`, `rules`, `tui` | script `pyproject.toml:61-62`; handlers `src/codegenome/cli.py:14-280` | Supported modern surface |
| `python -m codegenome` | legacy argparse flags and multi-format workflow | `src/codegenome/__main__.py:17-137` | Separate semantics; README warns not to mix (`README.md:95-103`) |
| PyInstaller helper | local CLI executable build | `build_cli.py` | No automated release/signing pipeline |

Modern `mcp-start` supports stdio and HTTP, port/LAN, memory-bounded, query caps, and full-analysis-on-demand options (`src/codegenome/cli.py:105-168`). `docs/cli-reference.md:69-77` still says the modern command is stdio-only, so documentation is not a trustworthy complete contract.

## Python service API

`CodeGenomeService` offers one-shot `analyze`, `export`, and `rules` operations and deliberately leaves long-lived servers to dedicated runners (`src/codegenome/service.py:1-94`). `CodeGenome` provides the broader facade and lifecycle around engine services (`src/codegenome/core.py:1-39`, `:214-220`).

**Judgment:** This split is reasonable, but the package does not publish an explicit stability/versioning policy for Python APIs. Until one exists, internal module imports should be considered provisional.

## Export contracts

| Format | Writer | Output shape |
|---|---|---|
| JSON | `JsonWriter` | graph and intelligence document |
| HTML | `HtmlWriter` | standalone interactive visualization |
| GraphML | `GraphmlWriter` | graph interchange |
| Cypher | `CypherWriter` | graph database statements |
| Markdown | `MarkdownWriter` | report |
| Obsidian | `ObsidianWriter` | vault/directory |

The public coordinator exposes all six (`src/codegenome/exporter/coordinator.py:51-117`; package declaration `src/codegenome/exporter/__init__.py:1-32`). The modern CLI advertises only Obsidian/HTML/Cypher/JSON (`src/codegenome/cli.py:57-102`), while legacy paths can export all formats. This is either intentional product narrowing or contract drift; it is not documented as such. **Confidence: medium.**

## MCP tool contract

All tools are wrapped with timing/activity/error-envelope behavior (`src/codegenome/mcp_tools/graph_tools.py:10-21`). The registered tools are:

| Category | Tools |
|---|---|
| Discovery/query | `get_graph`, `query_graph`, `get_node`, `get_neighbors`, `search_nodes` |
| Evolution | `get_changes`, `get_timeline`, `get_churn` |
| Structure | `get_dead_code`, `get_entry_points`, `get_god_nodes`, `get_circular_deps` |
| Metrics | `get_betweenness_centrality`, `get_complexity`, `get_coupling_metrics` |

Signatures and defaults are authoritative at `src/codegenome/mcp_tools/graph_tools.py:24-176`. The public CLI reference lists only a subset (`docs/cli-reference.md:138-146`), omitting at least `query_graph`, `get_node`, coupling, and betweenness.

In bounded mode, targeted neighborhood/file queries load subgraphs on demand (`src/codegenome/graph_store.py:763-830`). Global analyzers read snapshot metrics and can be stale after patch builds until a full analysis (`update-doc/memory-bounded-storage-current-capabilities.md:251-259`). This freshness property belongs in every global-tool response or public contract.

## HTTP/REST routes

| Server | Method/path | Purpose | Access control |
|---|---|---|---|
| MCP | `GET /health` | process/store status; includes database path | None at application layer (`src/codegenome/mcp_tools/routes.py:24-37`) |
| MCP | `GET /mcp/activity` | recent tool activity | None (`src/codegenome/mcp_tools/routes.py:39-55`) |
| MCP | `GET /genome` | top-level module summaries | None (`src/codegenome/genome_routes.py:64-68`) |
| MCP | `GET /genome/{module_id}/graph` | helix/module graph | None (`src/codegenome/genome_routes.py:70-74`) |
| MCP | `GET /genome/{module_id}/structure` | structure tree | None (`src/codegenome/genome_routes.py:76-80`) |
| Live | graph/static routes plus `GET /ai/settings` | visualization and AI configuration state | None (`src/codegenome/live_session.py:93-176`) |
| Live | `POST /ai/models`, `POST /ai/chat` | provider discovery/chat | None; body length trusts `Content-Length` |

Genome endpoints are progressive at the browser contract level (`src/codegenome/genome_routes.py:26-55`), but every MCP genome request calls `graph_for_genome`, which loads the full snapshot in bounded mode (`src/codegenome/graph_store.py:753-761`). The endpoint payload is lazy; server memory use is not.

## WebSocket contract

`LiveGraphServer` accepts clients and supports karyotype, helix, and structure subscriptions, then broadcasts graph deltas (`src/codegenome/live_server.py:33-116`). No application authentication, origin allowlist, message-size setting, per-client rate limit, or subscription schema model is visible in that boundary.

**Judgment:** Loopback-only operation could make a minimal contract acceptable for development, but the live HTTP bind defect and `--lan` mode make those missing controls security requirements.

## AI provider contract

Supported provider definitions cover OpenAI, Gemini, Groq, and Ollama local/cloud (`src/codegenome/ai_chat.py:15-51`). Chat requests include local graph-derived context (`src/codegenome/ai_chat.py:191-220`), provider responses/errors cross the local/external trust boundary, and Gemini authentication is included in the request URL (`src/codegenome/ai_chat.py:145-157`).

Required contract improvements:

1. show a clear data-egress disclosure before first remote-provider use;
2. redact credentials and upstream bodies from errors/logs;
3. use header-based credentials where supported;
4. impose request/response/time/rate limits;
5. describe retention policies as provider-dependent, with links to current provider terms rather than hard-coded claims.

## Compatibility and error semantics

- API payloads use Pydantic models in serializers, which is a strong base (`src/codegenome/serializers/genome_schemas.py`).
- MCP uses guarded error envelopes, while live REST uses ad hoc JSON and status codes; a shared error schema is absent.
- No OpenAPI document, protocol version field, deprecation policy, or exported JSON schema is tracked.
- Graph metric outputs should carry analyzer/snapshot version and freshness, especially because fallback heuristics can label configuration/test nodes unexpectedly.
