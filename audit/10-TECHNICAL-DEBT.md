# Technical debt

> **TL;DR:** Debt is concentrated in contract duplication, persistence lifecycle, quality automation, documentation drift, and a handful of high-responsibility components—not in a large backlog of inline TODOs. A short stabilization cycle can retire most high-interest debt before it compounds into compatibility obligations.

## Debt register

| ID | Debt | Evidence | Interest paid today | Priority |
|---|---|---|---|---|
| TD-01 | Dual Click and argparse CLIs | `src/codegenome/cli.py:14-280`; `src/codegenome/__main__.py:17-137`; warning `README.md:95-103` | duplicate behavior/docs/tests; divergent exports/options | P1 |
| TD-02 | Two incompatible dependency manifests, no lock | `pyproject.toml:26-53`; `requirements.txt:1-24` | installation-dependent features and advisories | P0 |
| TD-03 | Snapshot schema lacks multiedge identity/migrations | `src/codegenome/timeline.py:163-171`, `:821-827` | data loss and migration risk | P0 |
| TD-04 | No state retention/compaction | 648 snapshots/4.2 GB; `update-doc/memory-bounded-storage-current-capabilities.md:261-263` | disk growth, backup/startup burden | P1 |
| TD-05 | Bounded REST path loads full graph | `src/codegenome/graph_store.py:753-761`; routes `src/codegenome/genome_routes.py:61-80` | surprise memory spikes | P1 |
| TD-06 | Health score uses placeholder coverage | `src/codegenome/serializers/health_aggregator.py:49-61`, `:178-181` | misleading product signal | P1 |
| TD-07 | Seven lint violations | audit `ruff check`; locations below | dead imports and weak gate credibility | P2 |
| TD-08 | Documentation/config drift | CLI/MCP/parser/module map/version URLs | onboarding and support cost | P1 |
| TD-09 | Machine-specific Cursor MCP config | `.cursor/mcp.json:1-13` | fails outside original Windows checkout | P1 |
| TD-10 | Empty developer-testing guide | `DEVELOPER_TESTING.md` is zero bytes | contributor uncertainty | P2 |
| TD-11 | Concentrated TUI/store/serializer responsibilities | graph complexity/coupling heuristics | expensive changes, broad regression surface | P2 |
| TD-12 | Generated graph history polluted Git in past | Git churn shows removed `.watcher/graph.json` with ~162k changed lines | obscures meaningful history/blame | Closed behavior; preserve ignore policy |

## Lint debt

The audit’s `python -m ruff check src tests` reported seven `F401` errors:

- `_RebuildHandler` in `src/codegenome/core.py:38`;
- `error` and `ok` in `src/codegenome/mcp_server.py:25-27`;
- `go_type_kind` and `typescript_class_kind` in `src/codegenome/parser/languages/python.py:9-14`;
- `file_node_id` in `src/codegenome/serializers/genome_provider.py:8`;
- `analyze_mode_cli_args` in `src/codegenome/tui/command_dispatch.py:12`.

These are easy fixes, but the deeper debt is that the documented lint command (`CONTRIBUTING.md:137-147`) is not enforced by CI.

## Structural hotspots

Fallback CodeGenome metrics rank `GraphStore` and `GraphTimeline` at complexity 83, `GenomeProvider` 64, browser `StructureMap` 62, and `GraphClusterer` 60. Coupling is highest for `GenomeProvider` (CBO 13), and TUI has the strongest god-node/LCOM signal.

**Judgment:** Refactoring should follow behavior tests and stable contracts:

1. split storage primitives/migrations from `GraphTimeline` and query/presentation shaping from `GraphStore`;
2. separate genome indexing from payload serialization and health evaluation;
3. isolate TUI state, command dispatch, process control, and rendering;
4. keep exporter writers separate—the current protocol/coordinator design is already appropriate (`src/codegenome/exporter/__init__.py:1-32`).

**Confidence: medium.** Static graph scores reveal change concentration but do not prove a specific class split will improve outcomes.

## Documentation debt

| Document/config | Drift |
|---|---|
| `docs/cli-reference.md:69-77` | says modern MCP is stdio-only; code supports HTTP/port/LAN/bounded flags |
| `docs/cli-reference.md:138-146` | omits several MCP tools |
| `docs/cli-reference.md:99-102` | promises local-only evolve behavior contradicted by bind code |
| `CONTRIBUTING.md:79-104` | describes `parser.py`, now a package |
| `update-doc/memory-bounded-storage-current-capabilities.md:278-291` | references old monolithic intelligence/TUI paths |
| `goal/components_analysis.md:29-40` | overstates health and lazy-loading behavior |
| `pyproject.toml:55-59` | project URLs point to a different GitHub owner |
| `.cursor/mcp.json:1-13` | hard-coded local executable path |

## Debt repayment sequence

- **Stabilize contracts:** repair bind, snapshot identity, rules writes, and health provenance.
- **Make quality executable:** one dependency source, clean install, full CI, lint, coverage floor, audit.
- **Control state:** migrations, integrity checks, retention/compaction, backup/recovery.
- **Consolidate interfaces:** make `python -m codegenome` delegate to Click or publish a retirement schedule.
- **Refactor hotspots:** only after regression coverage protects current behavior.
- **Refresh knowledge:** update docs/URLs/config and add ADRs for durable decisions.
