# Phase 0 Release-Blocker Verification Ledger

Audit date: 2026-07-20

Baseline: `689a01f`

Audit branch: `critical-update` (working tree based on `8e513b3`)

Release decision: **provisional pass on Windows; Linux and macOS CI evidence pending**

This ledger records executed evidence. A platform is never marked passing from source
inspection alone. The historical fallback snapshot's metadata target is **10,507 edges**;
the retained workspace database no longer contains that snapshot. Its current latest
snapshot is 648 with 8,085 metadata edges and exactly 8,085 `graph_edges` rows. BUG-02 is
therefore judged on exact cardinality preservation, not on forcing a changed repository
back to a historical graph size.

## Release gates

| Gate | Required invariant | Windows 11 | Ubuntu CI | macOS CI | Disposition |
|---|---|---:|---:|---:|---|
| SEC-01 network boundary | Defaults bind `127.0.0.1`; unauthenticated secondary-interface `POST /ai/chat` is refused or returns 401 | PASS | Pending | Pending | Await matrix |
| BUG-02 multiedge persistence | Two byte-identical edges produce two rows and reload as two edges | PASS | Pending | Pending | Await matrix |
| BUG-03 managed rules | Manual text survives and generated block updates in place | PASS | Pending | Pending | Await matrix |
| SEC-02 supply chain | Clean `pip install .`; `pip-audit` finds zero known vulnerabilities | PASS | Pending | N/A (audit job runs on Ubuntu) | Await CI audit |
| Full suite and async integrity | Every discovered test passes, including `test_live_server.py` async tests | 221/221 PASS | Pending | Pending | Await matrix |
| Blocking lint | `python -m ruff check src tests` exits zero | PASS | Pending | N/A (quality job runs on Ubuntu) | Await CI quality |
| Doctor | Loopback defaults, SQLite health/schema/count, and duplicate-edge probe pass | PASS | CLI smoke pending | CLI smoke pending | Await matrix |

## Windows execution record

| Time (Asia/Dhaka) | Protocol | Command or probe | Observed result | Status |
|---|---|---|---|---:|
| 2026-07-20 | SEC-01 source/runtime bind | Start `LiveSession(LiveSessionConfig(http_port=0))`; inspect `server_address` | Bound `127.0.0.1:55837` | PASS |
| 2026-07-20 | SEC-01 secondary interface | Unauthenticated HTTP `POST /ai/chat` to `192.168.0.112:55837` | `ConnectionRefusedError`, WinError 10061 | PASS |
| 2026-07-20 | BUG-02 exact duplicate round trip | Create two `a.py -> b.py` call edges with identical attributes; record and reload via `GraphTimeline` | input=2, SQLite rows=2, unique edge keys=2, reloaded=2 | PASS |
| 2026-07-20 | BUG-02 real database | `codegenome doctor --path .` | snapshot 648 metadata=8,085, rows=8,085; primary key includes `edge_key` | PASS |
| 2026-07-20 | BUG-03 CLI preservation | Write manual `AGENTS.md`; run `codegenome rules` at ports 7331 then 9000 | Manual text preserved; one marker pair; 9000 present; stale 7331 absent | PASS |
| 2026-07-20 | SEC-02 runtime install | Fresh Python 3.12 venv; `python -m pip install .`; install and run `pip-audit==2.10.1` | No known vulnerabilities found | PASS |
| 2026-07-20 | SEC-02 constrained dev install | In the clean venv, `python -m pip install -r requirements.txt`; rerun `pip-audit` | FastMCP 3.4.4, MCP 1.28.1, pytest 9.0.3, pytest-asyncio 1.4.0; no known vulnerabilities found | PASS |
| 2026-07-20 | SQLite physical health | Read-only `PRAGMA quick_check` through `codegenome doctor --path .` | `ok` on 4.2 GB `.genome/codegenome.db` | PASS |
| 2026-07-20 | Blocking lint | `python -m ruff check src tests` | All checks passed | PASS |
| 2026-07-20 | Complete tests | `python -m pytest -q` | 221 passed in 23.91 s | PASS |

Windows execution host: Windows 11 build 26200, CPython 3.14.3. The clean dependency
audit used CPython 3.12. The requested “196-test suite” count was stale: the audited tree
discovered 221 tests after adding the doctor and secondary-interface regressions.

## Protocol findings

| ID | Empirical finding | Code control | Retirement evidence |
|---|---|---|---|
| SEC-01 | A non-LAN session binds explicit loopback, never the empty-string wildcard. A LAN-interface request to the same port was refused. | Central `resolve_bind_host()` control; remote MCP requires explicit HTTP opt-in | Runtime probe plus network regression tests |
| BUG-02 | Parallel edges, including identical attributes, receive occurrence-aware SHA-256 keys and survive full/patch persistence. | `graph_edges` primary key is `(snapshot_id, source_id, target_id, edge_key)` | Two-edge probe, three-edge regression, schema migration test, and real row-count parity |
| BUG-03 | Generated rules occupy one marker-delimited managed block; manual text remains outside it. Updates are atomic and backed up. | `write_rule()`, `_render_rule()`, `_atomic_write()`, malformed-marker refusal | Two CLI generations plus idempotence, backup, malformed marker, and front-matter tests |
| SEC-02 | Runtime requirements are declared in `pyproject.toml`; `requirements.txt` delegates to `.[dev]`; security-sensitive resolutions live in `constraints.txt`. Every direct dependency has an upper bound. | FastMCP 3.4.4, MCP 1.28.1, pytest 9.0.3 constraint floor/pins; clean-install CI audit | Two zero-vulnerability Windows audits; Ubuntu audit pending |

## Architectural standards

| Standard | Evidence | Result |
|---|---|---:|
| No ML/data-loading glue debt | CodeGenome snapshot 648 reports `GraphClusterer` CBO=1. Clustering accepts an in-memory `Graph`; file ownership loading remains in `graph_loader.py`; persistence remains in `timeline.py`/engine services. | PASS |
| `src/` package layout | `pyproject.toml` sets `package-dir = {"" = "src"}` and package discovery `where = ["src"]`; wheel smoke runs outside the source tree in CI. | PASS |
| Async integrity | `pytest-asyncio>=1.3,<2` is in the canonical `dev` extra; all marked async tests in `test_live_server.py` pass within the complete suite. | PASS |
| Graph freshness during audit | Memory-bounded MCP served snapshot 648 with 5,756 nodes and 8,085 edges. | PASS |

## Cross-platform CI evidence

Workflow: `.github/workflows/compatibility.yml`

Run: **pending first workflow-dispatch run of this audit change set**

| Job | Required coverage | Run result |
|---|---|---:|
| Full tests / Ubuntu / Python 3.11 and 3.13 | Complete `pytest -q`, CLI and doctor help smoke | Pending |
| Full tests / macOS / Python 3.11 and 3.13 | Complete `pytest -q`, CLI and doctor help smoke | Pending |
| Full tests / Windows / Python 3.11 and 3.13 | Complete `pytest -q`, CLI and doctor help smoke | Pending |
| Dependency vulnerability audit | Clean Ubuntu `pip install .` followed by `pip-audit` | Pending |
| Lint, coverage, and package build | Blocking Ruff, complete coverage run, wheel/sdist validation and external wheel smoke | Pending |

## Architect's note to the engineer

Ohm, Plate, Sykosch, and Meier's 2020 study,
[“Backstabber's Knife Collection: A Review of Open Source Software Supply Chain Attacks”](https://doi.org/10.1007/978-3-030-52683-2_2),
analyzed 174 malicious packages distributed through npm, PyPI, and RubyGems. For this
release, unbounded dependency resolution is therefore treated as an active threat vector,
not a cosmetic packaging concern. Bounds, constrained security-sensitive resolutions,
clean-environment installation, and a blocking vulnerability audit are release controls.

Likewise, a failed multiedge round trip is a stop-ship defect. Collapsing parallel calls
silently changes architectural facts; downstream agents would receive architectural
hallucinations rather than a faithful repository model.

## Release rule

Production PyPI publication is permitted only when every applicable cell in the release
gate and CI tables is PASS. A failed or skipped BUG-02 invariant, any reachable
unauthenticated secondary-interface AI route, any known audited vulnerability, or a
non-green OS test leg blocks release.
