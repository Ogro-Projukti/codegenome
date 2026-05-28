# CodeGenome — Graph Build Audit & Cleanup Plan

Date: 2026-05-28

Purpose
- Produce a focused audit for graph-building, auto-evolve, and graph-driven analysis. Align cleanup tasks with project_identity.md and next_move.md so the package can prioritize a python-igraph-based, incremental, event-driven graph engine.

High-level findings
- Core, required components:
  - src/codegenome/parser.py — tree-sitter parsers: REQUIRED (primary source extraction).
  - src/codegenome/builder.py — graph construction: REQUIRED, currently NetworkX-centric; must migrate to igraph or wrap behind an abstraction.
  - src/codegenome/clusterer.py — clustering (leidenalg + igraph conversion): REQUIRED; consolidate to igraph-native (remove networkx intermediary).
  - src/codegenome/graph_store.py — persistence/timeline: REQUIRED; ensure store supports incremental snapshots and igraph-compatible serialization.
  - src/codegenome/timeline.py — timeline/churn analysis: REQUIRED; currently assumes networkx in places — migrate.
  - src/codegenome/watcher.py & live_graph_monitor.py — event-driven/watchdog pipeline: REQUIRED (real-time incremental builds).
  - src/codegenome/mcp_server.py & installer.py & mcp_activity.py — MCP integration: REQUIRED for agent integration, but can be optional in packaging via extras.
  - src/codegenome/exporter.py — export formats: REQUIRED surface, but should work from igraph or via an adapter.
  - tests/ — many tests assume NetworkX; REQUIRED to update to igraph or adapter tests.

- Risk/technical debt
  - NetworkX is used widely (builder, exporter, timeline, intelligence, graph_store). Next_move mandates removal to avoid memory blowups; current codebase mixes networkx and igraph with conversion helpers — risky and expensive.
  - python-igraph + leidenalg are native C-backed and preferred for large graphs, but platform packaging and wheel availability must be verified.
  - Export and tests currently depend on NetworkX APIs; blind removal will break behavior and CI.

- Candidates to postpone or make optional
  - Packaging helpers for PyInstaller/build.py — postpone until core migration completes.
  - Non-essential export formats or heavy optional integrations (GraphML/Cypher plugins) can be moved to optional extras.

Recommended migration strategy (staged)
1. Introduce a thin Graph API abstraction (src/codegenome/graph_api.py):
   - Provide the minimal API surface currently consumed across codebase (add_node, add_edge, nodes, edges, attributes, SCC, degree, neighbors, to_serializable()).
   - Implement an igraph-backed implementation and a NetworkX compatibility adapter for parity tests.

2. Add unit/integration tests that assert parity between current NetworkX output and igraph adapter on small graphs (SCCs, degree, export shapes).

3. Migrate builder.py to use Graph API (backed by igraph) while keeping behavior identical (graph.json output unchanged for same inputs).

4. Migrate clusterer.py to igraph-native calls; remove networkx_to_igraph conversion helper; use leidenalg directly on igraph objects.

5. Update exporter.py, timeline.py, graph_store.py, and intelligence.py to consume Graph API objects (or igraph directly once parity verified).

6. Run full test suite and fix regressions. Keep networkx available in dev extras only (e.g., [compat]) until tests and consumers fully migrated.

7. Remove networkx from core dependencies and pyproject; update README and docs describing installation extras for legacy exports.

8. Profile memory and performance on medium and large sample repos; iterate on lazy-loading and subgraph contraction strategies described in next_move.md.

Concrete checklist (files to change)
- High priority: src/codegenome/builder.py, src/codegenome/clusterer.py, src/codegenome/graph_store.py, src/codegenome/timeline.py, src/codegenome/exporter.py
- Medium: src/codegenome/intelligence.py, src/codegenome/watcher.py (ensure watcher integrates with new Graph API), tests/*
- Low/postpone: build.py, packaging scripts, optional exporters, docs updates

Dependency & packaging notes
- Keep: tree-sitter family (parsers), watchdog, fastmcp (MCP), python-igraph, leidenalg
- Move to optional extras: networkx (compat/export), pyinstaller, heavy export plugins
- Ensure python-igraph binary wheels are available or document build steps for platforms where they are not.

Testing & validation
- Add smoke tests that build a small repo graph and verify parity with existing outputs.
- Add memory/regression tests for larger repos to ensure igraph migration reduces peak memory usage.

Immediate next moves (recommended order)
1. Add src/codegenome/graph_api.py and tests asserting parity for core graph ops.
2. Refactor builder.py to use Graph API.
3. Run tests and fix breaking changes.
4. Migrate clusterer and exporter; remove networkx from core deps.

Notes
- next_move.md and project_identity.md already prescribe igraph-first and event-driven incremental pipelines — the above plan operationalizes those mandates while keeping a safe compatibility path.

If this looks good, next action can be: implement graph_api.py skeleton and convert builder.py to use it (I can perform those edits and run tests).