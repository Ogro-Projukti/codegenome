# Testing and quality

> **TL;DR:** The full suite is fast and passes 196 tests when `pytest-asyncio` is available, but the declared development extras omit that plugin and CI executes only one test module. Coverage is 69% overall with critical network/rules/CLI paths at 0%, and the documented Ruff check currently fails seven times.

## Test results

| Environment/check | Result | Interpretation |
|---|---|---|
| System Python full suite | 196 passed in the audit run | Functional baseline passes with available plugins |
| Project `env` full suite | 193 passed, 3 failed | Failures are async-runner configuration, not observed assertions |
| Coverage suite | 196 passed; 69% | 7,246 statements; 2,263 missed |
| Ruff | 7 `F401` errors | Quality command is not green |
| `pip check` | no broken requirements | Existing environment dependency metadata is internally consistent |

The three environment failures correspond to `pytest.mark.asyncio` tests (`tests/test_live_server.py:39`, `:56`, `:102`). The development extra lacks `pytest-asyncio` (`pyproject.toml:52-53`), so the failure is reproducible from declared tooling.

## Coverage profile

| Area | Audit coverage | Risk interpretation |
|---|---:|---|
| Total package | 69% | Reasonable alpha baseline, not a release gate |
| Scanner | 91% | Strong core coverage |
| GDR store | 95% | Strong persistence helper coverage |
| Core facade | 84% | Good |
| Builder | 86% | Good |
| Timeline | 80% | Appears good, but misses multiedge invariant |
| GraphStore | 59% | Risky for bounded/query contracts |
| Live server | 57% | Partial WebSocket coverage |
| Watch service | 28% | Weak real-time failure coverage |
| Engine process | 26% | Weak lifecycle/process coverage |
| TUI application | 20% | Weak interaction/state coverage |
| CLI, `__main__`, installer, rules, live session | 0% | Directly overlaps confirmed defects and release interfaces |

Coverage percentages are from the 2026-07-20 command in [`_progress.md`](./_progress.md). Line coverage does not establish behavioral adequacy: timeline reached 80% while still failing a central multigraph round-trip invariant.

## Test-suite composition

There are 34 tracked test files. Tests cover parser languages, graph API/building, clustering/intelligence, timeline/GDR/metrics, MCP store/server behaviors, serializers, live server, evolution, exports, and TUI helpers. The current suite has no enforced coverage floor, no mutation/property testing, and no documented flaky-test/retry policy.

High-value missing scenarios:

- parallel same-endpoint edges across storage/full/patch/diff;
- real socket address assertions for local/LAN servers;
- existing user content during rules generation;
- clean-install execution from every supported dependency definition;
- large-repository memory/database budgets;
- malformed/oversized HTTP and WebSocket messages;
- real versus absent coverage provenance in health payloads;
- CLI option parity and end-to-end command failures;
- AI provider error redaction and local/remote egress consent.

## CI quality gate

The only workflow runs on pushes to `main` and pull requests across Ubuntu/macOS and Python 3.11–3.13 (`.github/workflows/compatibility.yml:1-28`). It installs the package plus pytest, then runs only `tests/test_parser.py -q`, a CLI help command, and an import smoke test (`:29-41`).

Gaps:

- no complete test suite;
- no Windows job despite tracked Windows-specific MCP config and Windows-sensitive advisories;
- no development-extra installation check;
- no Ruff/format/type gate;
- no coverage report/floor;
- no wheel/sdist or PyInstaller artifact build/test;
- no dependency/SBOM/secret audit;
- no test result/coverage artifact publication.

## Recommended test pyramid

1. **Every PR, ~minutes:** clean install, full 196+ tests, Ruff, package build, coverage floor initially at 69% with ratchet-only increases.
2. **Matrix PR/nightly:** Python 3.11–3.13 on Linux/macOS/Windows; minimum and locked-latest dependencies.
3. **Targeted integration:** sockets, HTTP/WS, MCP stdio/HTTP, file watcher, rules filesystem, SQLite migration/retention.
4. **Property/invariant:** graph adapter and persistence round trips, deterministic IDs, patch/full equivalence.
5. **Security/release:** `pip-audit`, secret scan, SBOM, artifact install/smoke/signing.

## Quality policy recommendation

Define a branch-required workflow and do not raise the numeric coverage target by excluding difficult modules. First add tests around confirmed defects, then ratchet toward 80% package coverage while requiring 90%+ on newly changed code. Keep heuristic graph metrics advisory; make tests, lint, schema invariants, and package builds blocking.
