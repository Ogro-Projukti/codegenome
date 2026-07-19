# Planned versus actual implementation

> **TL;DR:** The core biological visualization concept, tree-sitter graph extraction, live updates, progressive views, virtual rendering, and semantic collapsing are substantially implemented. The product departed from the plan in hierarchy presentation, clustering algorithm, transport stack, memory behavior, and health-score truthfulness; several “implementation mapping” documents now overstate current behavior.

## Feature comparison

| Planned capability | Actual state | Evidence | Assessment |
|---|---|---|---|
| Strict six-level Genome → Chromosome → Chromatid → Gene → Codon → Nucleotide hierarchy | UI exposes Karyotype, Helix, and Structure views; lower concepts are embedded in payload/rendering rather than six distinct navigation levels | plan `goal/mapping.md:11-20`; serializers `src/codegenome/serializers/genome_provider.py:70-150` | Partially implemented/compressed |
| A/T/G/C plus G!/A* biological mapping | Explicit base-count and sequence mapping is implemented | planned `goal/mapping.md:24-36`; actual `src/codegenome/serializers/genome_provider.py:107-148` and `nucleotide_mapper.py` | Implemented; contrary to `goal/components_analysis.md:19`, strings are not merely abstracted away |
| Four-factor health score | Equal-weight coverage/cycles/zombies/complexity formula implemented | planned `goal/mapping.md:40-46`; actual `src/codegenome/serializers/health_aggregator.py:24-61`, `:110-150` | Implemented with a misleading default-coverage caveat |
| FastAPI + server-sent events | Custom `ThreadingTCPServer` plus WebSockets | planned `goal/mapping.md:44-46`; actual `src/codegenome/live_session.py:93-176`, `src/codegenome/live_server.py:33-116` | Deliberate replacement, docs partly acknowledge WebSockets |
| Fast-greedy communities for 100+ modules | Leiden runs whenever clustering graph has >1 connected node/edges | planned `goal/mapping.md:54-57`; actual `src/codegenome/clusterer.py:46-105` | Upgraded algorithm; threshold semantics changed |
| Strict lazy loading by endpoint | Browser payloads are separated, but bounded MCP genome routes load the complete graph for each request | planned `goal/mapping.md:59-64`; actual `src/codegenome/genome_routes.py:61-80`, `src/codegenome/graph_store.py:753-761` | Partially implemented |
| Helix virtual rendering window | Browser helix rendering limits visible work | plan `goal/mapping.md:68-71`; implementation `src/codegenome/assets/helix.js` | Implemented; performance target not benchmarked in audit |
| Structure view chunks files and loads more | Structure renderer implements paged/collapsed presentation | plan `goal/mapping.md:73-76`; implementation `src/codegenome/assets/structure.js` | Implemented |
| Real-time surgical evolution | watchdog paths can trigger incremental/surgical rebuild and WebSocket deltas | `src/codegenome/engine/watch_service.py`; `src/codegenome/live_server.py:48-116` | Implemented, under-tested |
| Memory-bounded large-repo service | SQLite partial loads, working-set controls, stored global metrics | `src/codegenome/graph_store.py:734-830`; current capability limits `update-doc/memory-bounded-storage-current-capabilities.md:247-263` | Implemented as opt-in with cold-build/full-genome caveats |

## Health-score truth gap

The plan says module health combines test coverage with three code-derived factors (`goal/mapping.md:40-46`). `GenomeProvider` accepts optional coverage but normal routes construct it without any coverage map (`src/codegenome/genome_routes.py:26-52`); the provider forwards that absence to `HealthAggregator` (`src/codegenome/serializers/genome_provider.py:70-75`). Missing coverage becomes `0.85` (`src/codegenome/serializers/health_aggregator.py:49-61`, `:178-181`) and contributes 25% of every score (`:36-43`, `:131-139`).

**Fact:** the displayed `test_coverage` field and aggregate health score ordinarily contain an assumed 85%, not measured coverage. **Judgment:** this is a semantic correctness defect because users are likely to interpret the field as repository evidence. **Confidence: high.** Either ingest actual coverage, remove that factor when absent and renormalize, or return `null`/`estimated: true` prominently.

## Document drift

- `goal/components_analysis.md:29-33` describes health in terms of centrality/bridges, but the actual health formula is coverage, cycles, likely dead symbols, and normalized complexity.
- `goal/components_analysis.md:40-41` implies memory-bounded API queries preserve strict lazy loading, while genome routes call full snapshot load.
- `update-doc/memory-bounded-storage-current-capabilities.md:278-291` references former monolithic `intelligence.py` and `tui.py` paths after those components became packages.
- `docs/cli-reference.md:69-77` omits modern HTTP MCP options present in `src/codegenome/cli.py:105-168`.
- `CONTRIBUTING.md:79-104` names `parser.py`, while parsing is now a package with language adapters.
- Version remains 0.1.4 (`pyproject.toml:7`; `src/codegenome/version.py:3`) despite a branch/release-plan narrative around a later patch and 16 post-main commits. No Git tag or GitHub release establishes a shipped version.

## History-based interpretation

Command evidence: the repository contains 73 commits over ten days (2026-05-28 to 2026-06-07); the audited branch is 16 commits ahead of `main`. Four pull requests (#2–#5) are merged, and PR [#6](https://github.com/Ogro-Projukti/codegenome/pull/6) remains open.

**Inference — confidence: medium:** rapid vertical feature delivery explains why implementation outran plans, tests, and reference documentation. The short history makes calendar-age “staleness” meaningless; risk is better measured by behavioral drift, ownership concentration, and missing quality gates.

## Decision record gaps

No ADR/RFC directory or explicit decision log was found. Important departures—Leiden over fast-greedy, WebSockets over SSE, dual CLI support, SQLite snapshot design, memory-bounded trade-offs, and AI-provider data egress—are scattered across planning and update notes. Convert these into short accepted decision records with context, alternatives, consequences, and compatibility expectations.
