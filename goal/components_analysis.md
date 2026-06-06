# CodeGenome: Components Analysis & Implementation Mapping

This document analyzes the "new features" outlined in `mapping.md` (the biological architecture metaphor and scaling strategies) and maps them to their actual technical implementation in the current CodeGenome codebase.

## 1. The 6-Level Biological Hierarchy

| Biological Metaphor | Codebase Concept | Implementation Details |
| :--- | :--- | :--- |
| **Genome** | Entire Repository / Dependency Graph | Managed by the `GlobalDependencyRegistry` (`src/codegenome/registry.py`) and persisted via SQLite (`gdr_store.py`). Graph manipulation is done using `igraph` and `networkx` abstractions (`graph_api.py`, `graph_store.py`). |
| **Chromosome / Chromatid** | Packages / Clustered Communities | Instead of strictly mapping to top-level directories, `GraphClusterer` (`src/codegenome/clusterer.py`) uses the **Leiden community detection algorithm** (`leidenalg`) to dynamically cluster highly coupled modules into cohesive architectural groupings. |
| **Gene** | Single Source File | Represented as `file` nodes within the core graph structure. The `file_node_id` connects file paths to the broader dependency graph. |
| **Codon** | Logical Block (Classes, Functions) | Handled by `ParsedSymbol` in the parser (`src/codegenome/parser/types.py`). `count_complexity` (`parser/common.py`) accurately calculates the cyclomatic/McCabe complexity for each block. |
| **Nucleotide** | AST Node | Implemented via the `tree-sitter` parser wrapper (`src/codegenome/parser/common.py`). AST nodes are parsed to extract functions, classes, imports, and calls. |

---

## 2. Nucleotide Mapping (A/T/G/C Alphabet)

While the explicit strings "Adenine" or "Thymine" are abstracted away for the frontend, the backend fully implements the data extraction needed to color-code and classify these bases:

*   **A (Adenine / Functions):** Extracted by `append_symbol` in `parser/common.py` with `kind` set to `"function"` or `"method"`.
*   **T (Thymine / Classes):** Extracted by `append_symbol` with `kind` set to `"class"`.
*   **G (Guanine / Imports):** Captured as edges with `edge_type == "imports"` in the graph and verified through module resolution (`clusterer.py`).
*   **C (Cytosine / Calls):** Captured via `record_call` (`parser/common.py`) resulting in `ParsedCall` objects and `"calls"` edges in the graph.
*   **G! (Circular Imports):** Handled by graph cycle detection metrics (e.g., `coupling_metrics.py`).

---

## 3. Real-Time Evolution & Health Auditing

*   **Real-Time Watchdog:** Implemented via `WatchService` and coordinated by `LiveGraphMonitor` (`src/codegenome/live_graph_monitor.py`). It listens to file system changes and triggers `surgical_update` or rebuilds.
*   **Server-Sent Events (SSE) / WebSocket:** Rather than SSE, the codebase currently utilizes a robust **WebSocket server** (`src/codegenome/live_server.py`). The `LiveGraphServer` runs in a background thread and pushes live graph deltas (`broadcast_graph_delta`) directly to any connected visualization clients instantly.
*   **Health & Metrics:** Architectural health is computed using advanced metrics like `betweenness_centrality` and bridge node detection inside `clusterer.py`, rather than just simple McCabe averages. CodeGenome also exposes a `/health` HTTP endpoint via MCP routing (`mcp_tools/routes.py`).

---

## 4. Scaling Strategy for Massive Codebases

*   **Algorithmic Clustering (Karyotype Level):** `mapping.md` proposed `community_fastgreedy()`. The current implementation upgraded this to the **Leiden Algorithm** (`leidenalg.find_partition` in `clusterer.py`), which provides superior community clustering and guarantees well-connected communities.
*   **Strict Lazy-Loading (API Layer):** The underlying architecture handles this by chunking queries and utilizing a memory-bounded MCP setup that only loads subgraphs on demand (as dictated by the `memory-bounded` flag in MCP server startup).
*   **Virtual Rendering & Semantic Collapsing:** These are frontend rendering concepts. The backend accommodates this by serving community partitions (`community_id`) and avoiding sending the full node array when a client requests top-level structural data.
