# Glossary

> **TL;DR:** CodeGenome combines conventional static-analysis terms with a biological visualization vocabulary. This glossary distinguishes product metaphors from persisted graph entities and calls out terms whose current implementation differs from older planning documents.

| Term | Meaning in this repository | Evidence/clarification |
|---|---|---|
| CodeGenome | The package/product that builds and queries local code knowledge graphs | `README.md:8-33` |
| Genome | Entire analyzed repository and, in UI, the top-level module summary | Plan `goal/mapping.md:15`; route `src/codegenome/genome_routes.py:26-29` |
| Chromosome | Package/module or community shown in the karyotype | Original directory concept was loosened by Leiden clustering |
| Chromatid | Planned sub-module/unzipped strand level | Not a distinct current interface level; part of compressed hierarchy |
| Gene | A source file in the biological metaphor | Represented by a graph `file` node |
| Codon | Class/function logical block | Represented by parsed symbol nodes, not a separate storage table |
| Nucleotide | A/T/G/C/A*/G! semantic element derived from symbols/edges | Mappings at `src/codegenome/serializers/genome_provider.py:107-148` |
| A | Function or method | `GenomeProvider` counts symbol kinds function/method |
| A* | Abstract class/interface variant | `src/codegenome/serializers/genome_provider.py:141-144` |
| T | Concrete class | `src/codegenome/serializers/genome_provider.py:143-144` |
| G | Import relationship | planned at `goal/mapping.md:30` |
| G! | Import marked as participating in a circular relationship | health/nucleotide serializers |
| C | Call relationship | planned at `goal/mapping.md:31` |
| Karyotype | Top-level visualization of modules/communities and health/base composition | `GenomeProvider.build_summary` (`src/codegenome/serializers/genome_provider.py:77-101`) |
| Helix | Module-level relationship/nucleotide visualization | `GET /genome/{module_id}/graph` (`src/codegenome/genome_routes.py:32-42`) |
| Structure view | Hierarchical file/class/method presentation | `GET /genome/{module_id}/structure` (`src/codegenome/genome_routes.py:45-55`) |
| Node | Attributed graph entity such as file, symbol, import, or proxy | constructed in `src/codegenome/builder.py:137-282` |
| Edge | Directed typed relationship such as contains/imports/inherits/calls | same builder path; multiple edges per endpoints are valid in memory |
| Proxy node | Placeholder for a call/inheritance/import target not resolved to a concrete symbol/file | builder resolution logic |
| Community | Leiden-derived group of coupled file nodes | `src/codegenome/clusterer.py:87-105` |
| Bridge node | File connecting different detected communities | `src/codegenome/clusterer.py:148-177` |
| GDR | Global Dependency Registry; file-level provides/consumes data persisted per snapshot | `src/codegenome/gdr_store.py:12-56` |
| Snapshot | Stored graph version with label/kind/base/count metadata and node/edge rows | `src/codegenome/timeline.py:805-839` |
| Full snapshot | Complete analyzed graph state | used for cold/full analysis |
| Patch snapshot | Incremental state derived from a base snapshot | global metrics may be copied/stale until full analysis |
| Timeline | Snapshot history, node history, and structural diffs | `GraphTimeline` and MCP `get_timeline`/`get_changes` |
| Memory-bounded mode | Keeps little/no full graph resident and loads SQLite slices for queries | `src/codegenome/graph_store.py:734-830` |
| Working set | Bounded/LRU collection of files/subgraph held for incremental operation | current capability note `update-doc/memory-bounded-storage-current-capabilities.md:251-259` |
| Intelligence | Static graph-derived findings/metrics: dead code, cycles, entry points, god nodes, complexity, coupling, centrality, churn | MCP registrations `src/codegenome/mcp_tools/graph_tools.py:84-166` |
| CBO | Coupling Between Objects/classes signal | exposed by `get_coupling_metrics`; heuristic in this graph model |
| LCOM | Lack of Cohesion of Methods signal | used in god-node/coupling analysis; heuristic |
| God node | Highly connected/high-responsibility static-analysis candidate | review signal, not automatically a defect |
| Dead code | Symbol with no detected incoming/use path under analyzer rules | may include false positives, tests, callbacks, framework/public entry points |
| Churn | Architectural/file change rate across stored snapshots | MCP `get_churn` (`src/codegenome/mcp_tools/graph_tools.py:152-166`) |
| MCP | Model Context Protocol surface exposing graph tools over stdio or HTTP | `src/codegenome/mcp_server.py:84-197` |
| Progressive disclosure | Fetch/render top-level summary first and module details on demand | routes `src/codegenome/genome_routes.py:26-80`; server may still full-load graph |
| Surgical update | Re-analyze a localized changed scope rather than complete workspace | engine/watch flow; stored global metrics may remain from last full run |
| Health score | Equal-weight combination of coverage, no-cycle, no-zombie, and complexity factors | `src/codegenome/serializers/health_aggregator.py:36-43`, `:110-150`; absent coverage currently defaults to 0.85 |
| Live evolution | Watch files, update graph, serve browser assets, broadcast WebSocket deltas | `codegenome evolve`; live session/server modules |

Terms such as “entry point,” “dead code,” “complexity,” and “health” are analyzer outputs, not proofs. Public UI/API documentation should include methodology, snapshot/freshness, and confidence to prevent metaphor or metric names from overstating certainty.
