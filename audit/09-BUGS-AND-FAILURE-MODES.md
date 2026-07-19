# Bugs and failure modes

> **TL;DR:** Three defects have direct reproduction or independent corroboration: default live HTTP exposure, parallel-edge loss during snapshot persistence, and destructive rules-file overwrite. Additional correctness failures include a declared development environment that cannot run async tests and health scores that present assumed coverage as measured data.

## Confirmed defects

### BUG-01 — non-LAN live mode binds all interfaces

| Field | Detail |
|---|---|
| Severity | High |
| Evidence | Intended bind host is `127.0.0.1` unless LAN is requested (`src/codegenome/live_session.py:211-213`), but HTTP construction passes `""` when LAN is false (`src/codegenome/live_session.py:266-272`). |
| Reproduction | An ephemeral `ThreadingTCPServer(("", 0), ...)` reported `0.0.0.0` on the audit host. |
| Impact | Unauthenticated graph/static/AI routes can be reachable from local network interfaces; documentation’s local-only promise is false (`docs/cli-reference.md:99-102`). |
| Root cause | `listen_host` reverses the safe default instead of using `self.bind_host`. |
| Fix/test | Always bind `self.bind_host`; assert `server_address` is loopback by default and wildcard only with explicit LAN consent. |

### BUG-02 — timeline persistence discards parallel edges

| Field | Detail |
|---|---|
| Severity | High |
| Evidence | Metadata counts every edge (`src/codegenome/timeline.py:143-150`), persistence dictionary keeps one edge per `(source,target)` (`:163-171`), and schema key has no edge identity (`:821-827`). |
| Reproduction | Two distinct `calls` edges `a → b` round-tripped as one; metadata stayed at two. Current snapshot metadata/export has 10,507 edge instances, database rows have 8,085. |
| Impact | Historical/bounded graphs lose call/import multiplicity and attributes, invalidating counts/diffs and possibly metrics. |
| Root cause | A simple-graph relational key was used for a multigraph model. |
| Fix/test | Migrate to stable edge keys; test exact node/edge/attribute invariants across full, patch, load, export, and diff. |

### BUG-03 — rules generation overwrites user content

| Field | Detail |
|---|---|
| Severity | High |
| Evidence | `write_rule` calls unconditional `path.write_text` (`src/codegenome/rules.py:87-95`); target generation includes files such as `AGENTS.md` (`src/codegenome/rules.py:30-66`, `:118-119`). |
| Corroboration | Open PR [#6](https://github.com/Ogro-Projukti/codegenome/pull/6) describes preserving user content with managed markers; no checks are attached. |
| Impact | User instructions and repository policy can be silently destroyed. |
| Root cause | Generated content has no ownership boundary, merge markers, backup, or conflict policy. |
| Fix/test | Use bounded managed sections, atomic writes, backup/diff preview, idempotency and preservation tests. |

### BUG-04 — documented development setup cannot execute full suite

| Field | Detail |
|---|---|
| Severity | Medium |
| Evidence | `pyproject.toml:52-53` declares pytest/coverage/Ruff/PyInstaller but not `pytest-asyncio`; async tests use `pytest.mark.asyncio` at `tests/test_live_server.py:39`, `:56`, `:102`. |
| Reproduction | Project environment: 193 passed/3 failed with unknown-mark/no-async-plugin errors; system environment with plugin: 196 passed. |
| Impact | A contributor following `CONTRIBUTING.md:43-75` can get a red suite before changing code. |
| Fix/test | Add a compatible `pytest-asyncio` bound and run a clean-environment CI install from declared extras. |

### BUG-05 — health API reports synthetic coverage as fact

| Field | Detail |
|---|---|
| Severity | Medium |
| Evidence | Normal route construction supplies no coverage (`src/codegenome/genome_routes.py:26-52`); `GenomeProvider` forwards `None` (`src/codegenome/serializers/genome_provider.py:70-75`); missing coverage becomes 0.85 (`src/codegenome/serializers/health_aggregator.py:49-61`, `:178-181`). |
| Impact | `test_coverage` and aggregate health look evidence-based but are estimated, biasing every module score. |
| Root cause | Placeholder value escaped into the public model without provenance. |
| Fix/test | Use nullable coverage and factor renormalization, or wire real coverage and include provenance/timestamp. |

## Failure modes and suspected defects

| ID | Failure mode | Status/confidence | Evidence and validation needed |
|---|---|---|---|
| FM-01 | Genome endpoints defeat bounded memory on large snapshots | Confirmed code path; runtime impact unmeasured, confidence high | `graph_for_genome` loads full snapshot (`src/codegenome/graph_store.py:753-761`) for routes (`src/codegenome/genome_routes.py:61-80`). Add peak-memory/load tests. |
| FM-02 | Patch results serve stale global intelligence as current | Documented limitation, confidence high | Metrics are copied until full analysis (`update-doc/memory-bounded-storage-current-capabilities.md:251-259`). Add freshness fields/warnings. |
| FM-03 | SQLite growth exhausts local storage | Observed trend, future timing uncertain, confidence medium | 648 snapshots/4.2 GB; no retention mechanism found; GDR is copied per snapshot (`update-doc/memory-bounded-storage-current-capabilities.md:261-263`). Load-test and define budgets. |
| FM-04 | Disabled foreign keys allow orphaned derived rows | Control gap, no orphan proven, confidence medium | `PRAGMA foreign_keys=0`; schemas declare relationships. Enable in tests and check current integrity before migration. |
| FM-05 | Invalid AI config silently resets behavior | Confirmed fallback, user-impact uncertain | Invalid JSON returns `{}` (`src/codegenome/ai_chat.py:609-616`). Surface a recoverable warning and preserve corrupt file for diagnosis. |
| FM-06 | Graph cycle/dead-code reports create false positives | Observed heuristic limitation, confidence high | Snapshot flags `mcp_analysis.py ↔ graph_store.py`, but imports are type-check/local exception imports (`src/codegenome/mcp_analysis.py:17-18`, `:39-52`); dead list includes tests/helpers. Improve classification and confidence output. |

## Error-handling observations

- Live HTTP parsing trusts `Content-Length` and reads that body without an application maximum (`src/codegenome/live_session.py:173-176`). A large/slow body can consume memory or worker time.
- AI config permission hardening ignores `OSError` (`src/codegenome/ai_chat.py:619-628`); on Windows, `chmod(0600)` alone is not a reliable user-only ACL guarantee.
- Provider error parsing can propagate upstream body details (`src/codegenome/ai_chat.py:482-502`); sanitize for secrets/PII before returning to browser logs.
- Most watcher/build exceptions are logged rather than silently ignored. No broad production `TODO`/`FIXME` backlog was found in the targeted scan.

## Regression-test priorities

1. Loopback/wildcard binding and LAN opt-in integration test.
2. Multiedge full/patch snapshot round-trip property tests.
3. Existing-file rules preservation, idempotency, rollback, and interrupted-write tests.
4. Clean Python 3.11/3.12/3.13 environment installation followed by all tests.
5. Health-score missing/real/stale coverage provenance tests.
6. Large snapshot memory ceiling and database retention tests.
