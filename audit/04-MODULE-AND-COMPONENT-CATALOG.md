# Module and component catalog

> **TL;DR:** The source tree is organized around a thin facade, explicit engine services, graph/parsing primitives, persistence and intelligence subsystems, and several delivery adapters. Ownership is clear at directory level, but `GraphStore`, serialization/health calculation, and TUI coordination deserve decomposition and sharper contracts.

## Core and engine

| Component | Responsibility | Key dependencies/consumers | Assessment |
|---|---|---|---|
| `core.py` / `CodeGenome` | Public facade and lifecycle | engine context/build/export/watch services | Thin and appropriate; closes resources at `src/codegenome/core.py:214-220` |
| `engine/context.py` | Resolve workspace paths and compose shared components | scanner, parser, builder, timeline | Central dependency root (`src/codegenome/engine/context.py:19-75`) |
| `engine/build_service.py` | Full/incremental analysis orchestration | all analysis and persistence stages | Cohesive orchestration but high fan-out (`src/codegenome/engine/build_service.py:22-103`) |
| `engine/export_service.py` | Select export formats/paths | exporter package | Delivery adapter |
| `engine/watch_service.py` | Watch files and trigger rebuilds | watchdog, build service | Low coverage (28% in audit run) |
| `engine/process.py` | Process/runtime coordination | live/TUI paths | Low coverage (26%) |
| `service.py` | Small in-process analyze/export/rules API | `CodeGenome`, rule generator | Explicitly excludes long-lived servers (`src/codegenome/service.py:1-94`) |

## Analysis model

| Component | Responsibility | Contract/evidence | Risk/notes |
|---|---|---|---|
| `scanner.py` | Ignore-aware file enumeration, hashing, scan cache | cache schema `src/codegenome/scanner.py:70-96`; scan `:204-292` | Good test coverage (91%) |
| `parser/` | Language selection and semantic extraction | extensions/grammars `src/codegenome/parser/__init__.py:42-80`; parse `:93-190` | CI tests only this subsystem |
| `builder.py` | Turn parsed units into attributed graph nodes/edges | deterministic IDs `src/codegenome/builder.py:14-36`; build/update `:49-126` | Proxy nodes preserve unresolved references |
| `graph_api.py` | Common graph protocol and NetworkX/igraph implementations | default creation ends at `src/codegenome/graph_api.py:479` | Multiedge semantics must be tested across adapters/storage |
| `clusterer.py` | File-level communities, bridges, centrality | Leiden invocation `src/codegenome/clusterer.py:87-105` | Algorithm differs from original fast-greedy plan |

## Intelligence

| Area | Purpose | Examples |
|---|---|---|
| Structural analysis | Entry points, cycles, likely dead code | `src/codegenome/intelligence/structural.py` |
| Metrics | Complexity, coupling/CBO/LCOM, centrality, churn | `src/codegenome/intelligence/metrics.py` and related analyzers |
| Projections | Build file/class projections from symbol graph | `src/codegenome/intelligence/projections.py` |
| Context/reporting | Shared analysis context and aggregate report | `src/codegenome/intelligence/context.py`; package exports |
| MCP adapter | Convert store/snapshot results to tool responses | `src/codegenome/mcp_analysis.py` |

CodeGenome snapshot evidence: 93 communities and 28 bridges were found. Highest complexity signals were `GraphStore` and `GraphTimeline` (83 each), `GenomeProvider` (64), browser `StructureMap` (62), and `GraphClusterer` (60). **Confidence: medium:** these values are analyzer-defined relative signals, not standard cyclomatic-complexity measurements.

## Persistence and state

| Component | Responsibility | Notable behavior |
|---|---|---|
| `timeline.py` / `GraphTimeline` | Snapshot metadata, nodes, edges, diffs, history | Full and patch snapshots; current edge key collapses parallel edges |
| `graph_store.py` / `GraphStore` | MCP-oriented query facade over current snapshot | Bounded neighborhood/file loads; global metrics read precomputed snapshot data |
| `gdr_store.py` | File-level provides/consumes dependency records | Schema v3; rows copied per snapshot (`src/codegenome/gdr_store.py:12-56`) |
| `snapshot_metrics.py` | Persist global metric documents | Schema v1 (`src/codegenome/snapshot_metrics.py:13-26`) |
| `mcp_activity.py` | Tool event timing/status/argument summaries | Persistent local audit/health data (`src/codegenome/mcp_activity.py:16-35`, `:81-104`) |

## Serialization and visualization

| Component | Responsibility | Notes |
|---|---|---|
| `serializers/genome_provider.py` | Build top-level module, helix, and structure payloads | Aggregates base counts and health; graph metric flags complexity/coupling |
| `serializers/nucleotide_mapper.py` | Map symbols/edges/calls to A/A*/T/G/G!/C semantics | Implements the product metaphor |
| `serializers/health_aggregator.py` | Four-factor module health score | Equal weights; missing coverage defaults to 0.85 (`:36-61`, `:178-181`) |
| `genome_routes.py` | REST adapters for progressive views | Three GET routes (`src/codegenome/genome_routes.py:26-80`) |
| `live_session.py` | Static HTTP and AI endpoints; server coordination | Security-critical boundary with default-bind defect |
| `live_server.py` | WebSocket subscriptions and change broadcasts | Karyotype/helix/structure subscriptions (`src/codegenome/live_server.py:48-116`) |
| Browser assets | Render graph/karyotype/helix/structure without a framework | Four tracked JS files and two CSS files |

## Delivery and integration

| Component | Responsibility | Surface |
|---|---|---|
| `cli.py` | Supported Click command group | `analyze`, `export`, `mcp-start`, `evolve`, `rules`, `tui` |
| `__main__.py` | Legacy argparse entry | historical flags and all-format export path |
| `mcp_server.py` | FastMCP creation, transport and security flags | stdio/HTTP, loopback by default (`src/codegenome/mcp_server.py:84-197`) |
| `mcp_tools/graph_tools.py` | Register 15 graph/intelligence tools | complete list at `src/codegenome/mcp_tools/graph_tools.py:24-176` |
| `mcp_tools/routes.py` | Health, activity, genome custom routes | exposes DB path/activity details (`src/codegenome/mcp_tools/routes.py:24-57`) |
| `exporter/` | Six independent writers behind `GraphExporter` | formats declared at `src/codegenome/exporter/__init__.py:1-32` |
| `rules.py` | Generate agent/editor rule files | currently overwrites target files (`src/codegenome/rules.py:87-95`) |
| `tui/` | Interactive Textual application | broadest cohesion/god-node warning in snapshot |

## Coupling hotspots

The fallback graph’s highest class coupling signal is `GenomeProvider` (CBO 13), followed by intelligence/core/build/export/timeline classes. TUI has the strongest LCOM/god-node signal, and `GraphStore` combines persistence, bounded loading, query shaping, and metric dispatch.

**Judgment:** Prioritize contract extraction around snapshot loading, genome serialization, and TUI command/state coordination before splitting small, cohesive parsers or exporters. **Confidence: medium**, because static coupling should guide code review, not dictate refactoring on its own.
