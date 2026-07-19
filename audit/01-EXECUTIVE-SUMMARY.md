# Executive summary

> **TL;DR:** CodeGenome has a coherent analysis pipeline, broad language parsing, a useful MCP/query surface, and a passing 196-test suite in a suitably provisioned environment. Release readiness is nevertheless blocked by an all-interface default live-server bind, lossy persistence of parallel graph edges, destructive rules generation, vulnerable/inconsistent dependency specifications, and incomplete CI coverage.

## Audit opinion

**Judgment:** The repository is an ambitious, functional pre-1.0 engineering product, but it should not be treated as production-hardened yet. The highest-value work is correctness and boundary hardening—not adding another visualization or analyzer.

**Confidence: high.** This opinion combines source inspection, a current CodeGenome graph snapshot, SQLite inspection, Git/GitHub history, and local execution evidence recorded in [`_progress.md`](./_progress.md).

## Health snapshot

| Dimension | Assessment | Evidence |
|---|---|---|
| Product architecture | Healthy foundation | Scanner → parser → graph → intelligence → timeline/export → TUI/MCP/live consumers is explicitly orchestrated in `src/codegenome/engine/build_service.py:22-103`. |
| Functional tests | Good locally, weakly enforced | 196 tests pass with the available async plugin; CI runs only `tests/test_parser.py` plus two smoke checks (`.github/workflows/compatibility.yml:29-41`). |
| Correctness | Release blocker | Timeline storage collapses same-source/same-target edges (`src/codegenome/timeline.py:163-171`, `src/codegenome/timeline.py:821-827`); the audit reproduced data loss. |
| Security | Release blocker | Non-LAN live mode passes an empty host (`src/codegenome/live_session.py:266-272`), which Python binds to all interfaces; live routes are unauthenticated (`src/codegenome/live_session.py:93-176`). |
| Dependency hygiene | Needs immediate work | `pyproject.toml:26-53` and `requirements.txt:1-24` describe different environments; the requirements resolution produced 11 advisory records. |
| Maintainability | Mixed | Core boundaries are modular, but graph metrics flag `GraphStore`, `GenomeProvider`, and TUI concentration; Ruff reports seven errors. |
| Operations | Immature | No documented deployment, rollback, release automation, alerting, or dependency-update automation; only a compatibility workflow is tracked. |
| Documentation | Substantial but drifting | README and CLI docs are useful, while parser layout, MCP flags/tools, version/test counts, and local-only claims lag implementation. |

## Top five risks

1. **High — live service is exposed beyond localhost by default.** The console intent is loopback (`src/codegenome/live_session.py:211-213`), but server construction uses `""` when `--lan` is false (`src/codegenome/live_session.py:266-272`). Unauthenticated AI settings/model/chat and graph endpoints are then reachable on local network interfaces.
2. **High — persisted snapshots are not graph-faithful.** Snapshot metadata records 10,507 edges while the latest relational edge table holds 8,085; parallel calls/imports are collapsed by a `(snapshot_id, source_id, target_id)` primary key (`src/codegenome/timeline.py:821-827`).
3. **High — dependency specifications resolve known vulnerabilities.** The isolated `requirements.txt` audit found affected FastMCP, MCP, and pytest versions; several fixes require relaxing FastMCP `<3` and updating MCP/pytest. See [`07-DEPENDENCIES.md`](./07-DEPENDENCIES.md).
4. **High — rules generation can overwrite user-owned instruction files.** `write_rule` unconditionally writes the whole target (`src/codegenome/rules.py:87-95`); open PR [#6](https://github.com/Ogro-Projukti/codegenome/pull/6) independently identifies the same destructive behavior.
5. **Medium — governance and CI provide limited release protection.** `main` has no detected protection/ruleset, there are no tags/releases, and CI does not run the full suite, Ruff, coverage, packaging, or security checks.

## Recommended action sequence

| Priority | Action | Impact | Effort |
|---|---|---:|---:|
| P0 | Bind live HTTP explicitly to `127.0.0.1`; add authentication/origin/body-size controls before LAN exposure | Very high | Low–medium |
| P0 | Give timeline edges stable identities and migrate/rebuild snapshots; add multiedge round-trip tests | Very high | Medium–high |
| P0 | Merge/adapt marker-based non-destructive rule updates and add preservation tests | High | Medium |
| P1 | Reconcile dependency manifests/lock policy; upgrade vulnerable resolutions; review GPL distribution obligations | High | Medium |
| P1 | Make one full, cross-platform CI quality gate: full tests, Ruff, coverage floor, build, dependency audit | High | Medium |
| P2 | Replace synthetic 85% coverage in health scores or clearly label it as estimated (`src/codegenome/serializers/health_aggregator.py:49-61`, `:178-181`) | Medium | Low–medium |
| P2 | Add snapshot retention/compaction and refresh stale docs/config | Medium | Medium |

## Positive foundations to preserve

- Parser dispatch supports Python, JavaScript/JSX/MJS/CJS, TypeScript/TSX, Go, and Rust (`src/codegenome/parser/__init__.py:42-80`).
- The engine separates workspace context, build orchestration, persistence, intelligence, serialization, and delivery surfaces (`src/codegenome/engine/context.py:19-75`, `src/codegenome/engine/build_service.py:22-103`).
- MCP exposes 15 bounded query/intelligence tools (`src/codegenome/mcp_tools/graph_tools.py:24-176`), and memory-bounded queries load neighborhoods/file slices on demand (`src/codegenome/graph_store.py:763-830`).
- Git history shows rapid modularization and feature delivery over 73 commits; the current full suite is fast enough (~14 seconds) to enforce on every change.

## Scope caveat

This is a repository audit, not a penetration test, legal opinion, production load test, or deployed-environment review. No production configuration, real credentials, runtime traffic, artifact signature, or disaster-recovery exercise was available, so related conclusions are labeled as gaps rather than facts about an unseen deployment.
