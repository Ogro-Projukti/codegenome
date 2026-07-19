# Risk register and recommendations

> **TL;DR:** The risk profile is dominated by five near-term items: unintended network exposure, graph data loss, destructive file generation, vulnerable/inconsistent dependencies, and weak release gates. Addressing those in a focused stabilization milestone materially lowers security, correctness, and adoption risk before further feature work.

## Risk scale

- **Impact:** Low, Medium, High, Critical consequence if realized.
- **Likelihood:** Low, Medium, High based on current code and ordinary use.
- **Priority:** P0 blocks a trusted release; P1 belongs in the next stabilization milestone; P2 is planned hardening; P3 is monitor/document.
- Facts and command evidence are detailed in the linked audit reports; prioritization is engineering judgment.

## Register

| ID | Risk | Impact | Likelihood | Priority | Evidence/owner area | Mitigation and exit criterion |
|---|---|---:|---:|---:|---|---|
| R-01 | Default live server reachable beyond localhost | High | High | P0 | [`12-SECURITY-REVIEW.md`](./12-SECURITY-REVIEW.md), live runtime | explicit loopback bind; LAN opt-in + auth/origin/limits; cross-platform socket test |
| R-02 | Snapshot graph loses parallel edges | High | High | P0 | [`05-DATA-MODEL-AND-DATA-FLOW.md`](./05-DATA-MODEL-AND-DATA-FLOW.md), persistence | edge identity migration; current-state rebuild; exact round-trip invariant passes |
| R-03 | Rules command destroys user policy/instructions | High | Medium–high | P0 | [`09-BUGS-AND-FAILURE-MODES.md`](./09-BUGS-AND-FAILURE-MODES.md), CLI/rules | managed markers + atomic backup/diff; preservation/idempotency tests |
| R-04 | Install path selects vulnerable/incompatible dependencies | High | High | P0 | [`07-DEPENDENCIES.md`](./07-DEPENDENCIES.md), packaging | one source + lock/constraints; safe versions; audit is clean or exceptions documented |
| R-05 | CI permits regressions/releases without core validation | High | High | P1 | [`11-TESTING-AND-QUALITY.md`](./11-TESTING-AND-QUALITY.md), maintainers | branch-required full matrix suite, Ruff, coverage, build, audit |
| R-06 | Health score misleads users with synthetic 85% coverage | Medium–high | High | P1 | [`08-PLANNED-VS-ACTUAL.md`](./08-PLANNED-VS-ACTUAL.md), serialization/product | real nullable/provenanced coverage; API/UI labels; tests |
| R-07 | SQLite state grows until disk/backup failure | High | Medium–high | P1 | 648 snapshots/4.2 GB; persistence/operations | retention/compaction dry run, transactional backup, budget alerts |
| R-08 | Memory-bounded genome endpoints trigger full-load spikes | High | Medium | P1 | `src/codegenome/graph_store.py:753-761`, API/store | true summary/module SQL projection; peak-RSS acceptance test |
| R-09 | AI keys/context leak through disk, URLs, clients, or provider calls | High | Medium | P1 | [`12-SECURITY-REVIEW.md`](./12-SECURITY-REVIEW.md), AI/live | keychain, header auth, redaction, explicit egress consent, route auth |
| R-10 | Stale global metrics appear current after patch updates | Medium | High | P1 | `update-doc/memory-bounded-storage-current-capabilities.md:251-259`, store/UI | freshness metadata/warnings; scheduled/full refresh policy |
| R-11 | No migration/integrity framework strands old state | High | Medium | P1 | [`05-DATA-MODEL-AND-DATA-FLOW.md`](./05-DATA-MODEL-AND-DATA-FLOW.md), persistence | versioned migrations, foreign keys, backups, upgrade/downgrade tests |
| R-12 | GPL dependency obligations conflict with intended distribution | High | Medium | P1 | [`07-DEPENDENCIES.md`](./07-DEPENDENCIES.md), release/legal | recorded counsel/maintainer decision, notices/source/distribution plan |
| R-13 | Dual CLI and documentation drift break users | Medium | High | P2 | [`06-INTERFACES-AND-CONTRACTS.md`](./06-INTERFACES-AND-CONTRACTS.md), CLI/docs | delegate/retire legacy CLI; generated command/tool reference; compatibility tests |
| R-14 | TUI/store/serializer concentration slows safe change | Medium | Medium | P2 | [`10-TECHNICAL-DEBT.md`](./10-TECHNICAL-DEBT.md), architecture | characterize with tests; extract contracts/state boundaries incrementally |
| R-15 | Weak local operational visibility delays diagnosis | Medium | Medium | P2 | [`13-CICD-OPERATIONS-AND-OBSERVABILITY.md`](./13-CICD-OPERATIONS-AND-OBSERVABILITY.md) | doctor command, size/freshness/runtime metrics, redacted logs/runbook |
| R-16 | Static-analysis false positives erode trust | Medium | Medium | P2 | graph cycle/dead-code review | confidence/reason fields, framework/public/test classifications, evaluation corpus |
| R-17 | Machine-specific config blocks onboarding | Low–medium | High | P2 | `.cursor/mcp.json:1-13` | portable command config validated on clean checkout |
| R-18 | No formal release provenance/rollback | High | Low–medium until release | P2 | no tags/releases/publish workflow | protected signed tags, artifacts/SBOM/checksums, rollback rehearsal |

## Stabilization roadmap

### Phase 0 — release blockers

1. Fix live bind and add boundary controls/tests.
2. Redesign/migrate edge persistence, rebuild the current snapshot, and compare exact graph invariants.
3. Land a non-destructive rules ownership model.
4. Reconcile dependencies, include `pytest-asyncio`, select fixed versions, and document license decision.

Exit: P0 tests are in CI; full suite/lint/audit/package build are green from a clean environment.

### Phase 1 — trustworthy operation

1. Add schema migrations, foreign-key enforcement/integrity checks, backup and retention.
2. Make genome endpoints genuinely bounded and benchmark cold/steady memory.
3. Correct health coverage semantics and global-metric freshness labels.
4. Secure AI credential/egress behavior and all LAN modes.
5. Protect `main` and establish version/tag/release metadata.

Exit: large-repo load test meets a written memory/disk budget; state migration/recovery is rehearsed; network threat-model tests pass.

### Phase 2 — maintainability and adoption

1. Consolidate the legacy CLI and generate user docs from command/tool definitions where practical.
2. Refactor TUI/GraphStore/GenomeProvider behind characterized contracts.
3. Improve analysis precision/confidence reporting with an evaluation corpus.
4. Add operational metrics/runbooks and reproducible signed releases.

Exit: documentation matches released behavior; ownership and support paths are explicit; quality trends improve without feature regressions.

## Recommendation scorecard

| Recommendation | Impact | Effort | Why now |
|---|---:|---:|---|
| Loopback + auth/origin/limits | Very high | Low–medium | direct default exposure |
| Multiedge schema migration | Very high | Medium–high | current stored truth is lossy |
| Managed rules sections | High | Medium | prevents user-data loss |
| Dependency source/lock/upgrades | High | Medium | known advisories and install divergence |
| Full required CI | High | Medium | makes every other remediation durable |
| Honest health/freshness metadata | High | Low–medium | restores trust in core product signals |
| Retention/migrations/doctor | High | Medium–high | current 4.2 GB state proves operational need |
| True bounded genome projections | High | Medium | protects stated large-repo value proposition |
| CLI/docs consolidation | Medium | Medium | lowers recurring compatibility/support cost |
| Hotspot refactoring | Medium | Medium–high | valuable after behavior is protected |

## Ownership and review cadence

The repository has no declared CODEOWNERS, and history is overwhelmingly concentrated in one author. Do not assign names from this audit; maintainers should nominate accountable owners for persistence, network/security, packaging/release, analysis correctness, UI, and documentation.

Review P0/P1 risks on every stabilization PR and before any release. Review P2/P3 monthly or at milestone boundaries, and reopen any accepted risk when its likelihood changes—for example, when LAN deployment, hosted service, or packaged binary distribution becomes a supported product mode.
