# Architectural Design Document: Scalable Codebase Graph Analyzer
## Executive Summary & System Decisions Log

This document compiles the architectural decisions, structural paradigms, and technical strategies agreed upon for scaling a codebase graph analysis tool. The primary objective is to transition from a monolithic, high-memory graph structure to a distributed, incremental, and language-agnostic architecture capable of handling enterprise-scale codebases efficiently.

---

## 1. Core Architecture & Technology Stack Upgrades

### The Problem
The initial implementation used `NetworkX` alongside `python-igraph` and `leidenalg`. For large codebases, `NetworkX` incurred a catastrophic memory footprint due to its internal storage design (nested Python dictionaries) and massive CPU overhead during serialization/deserialization between libraries.

### Decisions Made
1. **Complete Removal of NetworkX:** Standardize 100% of graph computation on `python-igraph`. 
   * **Reasoning:** `python-igraph` executes core graph operations (Strongly Connected Components, Cycle Detection, Degree Analysis, and Reachability) natively in C, providing a 10x–100x performance boost and severe memory reductions.
2. **Algorithmic Specialization:**
   * **Leiden Community Detection:** Runs on high-level macro-graphs or clean subgraphs to map logical architectures.
   * **Cycle Detection:** Avoid global execution of heavy algorithms (e.g., Tarjan's/Johnson's) across the entire codebase. Instead, calculate **Strongly Connected Components (SCCs)** first, treat them as single mega-nodes, and isolate deep cycle queries exclusively *within* problematic SCC clusters.
   * **Reachability Analysis:** Shift away from complete transitive closure computation to localized checks or landmark-based routing approximations where appropriate.

---

## 2. Structural Paradigm: Hierarchical Graph Decomposition

### The Problem
For a worst-case modular codebase containing layers of nesting:
$$\text{Modules (m)} \rightarrow \text{Submodules (sm)} \rightarrow \text{Files (f)} \rightarrow \text{Classes (c)} \rightarrow \text{Nested Classes (nc)} \rightarrow \text{Functions (fn)} \rightarrow \text{Local Functions (lfn)}$$
Loading a single flat graph representing line-by-line syntax relationships stalls UI rendering pipelines and breaches memory safety limits.

### Decisions Made
1. **Divide-and-Conquer Clustered Graphs:** Deconstruct the system into a tree of isolated graphs.
2. **Bottom-Up Graph Synthesis:** * **Leaf-Level (Micro-Graphs):** Create tiny, micro-graphs for independent submodules containing local files, classes, and execution flows.
   * **Macro-Level (Parent Graph):** Collapse entire submodule subgraphs into single "Meta-Nodes" using structural aggregation techniques (e.g., igraph's `contract_vertices()`). Edges between these meta-nodes represent cross-boundary imports, weighted by the cumulative frequency of interactions.
3. **Lazy-Loading Top-Down UI Pipeline:**
   * The user interface initially renders only the highest level Parent Graph (representing primary modules).
   * Detailed child graphs are **lazy-loaded via dedicated API endpoints** (`GET /graph/module_A`) only when a developer explicitly selects a module to explore, eliminating WebGL/Canvas rendering lags.

-

## 3. Incremental Rebuild & Event-Driven Parsing

### The Problem
Re-parsing thousands of unmodified files whenever a single line of code changes is highly inefficient. However, traditional polling methods using standard directory iterations (`os.walk`) thrash disk I/O, spike CPU consumption, and fall behind when processing vast numbers of files.

### Decisions Made
1. **Event-Driven Codebase Observer:** Replace time-interval folder-polling with an asynchronous background thread powered by the **`watchdog`** library.
   * **Reasoning:** Hooks directly into native OS kernel event sub-systems (`inotify` on Linux, `FSEvents` on macOS, `ReadDirectoryChangesW` on Windows) to capture instant, lightweight file-save notifications (e.g., `FileModifiedEvent`).
2. **Surgical Patching Pipeline:**
   * Upon notification, locate the explicit submodule boundary containing the altered file.
   * Clear old internal nodes and attributes associated with that single file path.
   * Re-parse *only* the modified file and merge the updated nodes/edges directly back into the cached submodule subgraph.
   * Re-run analytics suites (SCC, Cycles, Degree) locally within the altered module scope.



## 4. Cross-Submodule Dependency Management

### The Problem
When a file is modified locally, calculating how outside modules are affected (incoming dependencies) typically requires scanning the entire system, breaking the isolated submodule paradigm.

### Decisions Made
1. **Global Dependency Registry:** Implement a centralized, lightweight lookup schema (in-memory or SQLite-backed) tracing the usage of all exported definitions.
2. **Interface Contract Mapping:** Track structural definitions ("Provides") alongside external requirements ("Consumes").
3. **Proxy Node System:**
   * Submodules retain self-containment by using **Proxy/Stub Nodes** to represent points of contact with external targets.
   * If a critical symbol (e.g., `login_user()`) is deleted or renamed inside `Submodule_A`, the graph system queries the Registry, locates all dependent Proxy Nodes across foreign graphs, and marks their internal state as `is_broken = True`.
   * **Orphan and Reachability algorithms** catch these flags instantly to flag architectural breaking-changes in the UI without re-evaluating external AST structures.

```python
# System Design Pattern: Centralized Lookups
DEPENDENCY_REGISTRY = {
    "FQN_IDENTIFIER": {
        "defined_in": "origin/file_path.py",
        "consumed_by": ["dependent/file_path_1.py", "dependent/file_path_2.py"]
    }
}

```


## 5. Language-Agnostic Normalization Engine

### The Problem

Hardcoding unique semantic behaviors for every programming language's Abstract Syntax Tree (AST) causes engineering bloat and scales poorly.

### Decisions Made

1. **Standardized Parser Backend via Tree-sitter:** Deploy **Tree-sitter** for code parsing. It parses source files into structural concrete trees using fast C-grammars and offers lightning-fast incremental updates.
2. **Declarative Pattern Queries:** Utilize Tree-sitter S-expression queries to isolate syntax targets (Classes, Functions, Imports) uniformly across files.
3. **Universal Normalization Layer (Adapter Interface):** Create an adapter system to translate concrete syntax patterns into a standardized **Universal Schema / Common Intermediate Representation (IR)** before handing elements over to the graph engine.
4. **Fully Qualified Name (FQN) Resolution:** The adapter translates varying path behaviors (relative imports, package-level structures, text inclusions) into a uniform project namespace format (`PROJECT//root/submodule/file/symbol`) to align cleanly with the Global Dependency Registry.


## 6. MVP Implementation Strategy

1. **Target Environment:** Focus initial development on **Python** and structurally similar targets (e.g., Mojo, GDScript).
2. **Python Normalizer Focus:** Use Python's explicit import nuances (`import X`, `from Y import Z`, `from . import local`, and package definitions via `__init__.py`) as a rigorous testing suite to validate path resolution engines.
3. **Pipeline Construction Ordering:**
* **Milestone 1:** Build the backend storage topology using `python-igraph` supporting nested graph hierarchies.
* **Milestone 2:** Implement the centralized memory-based Global Dependency Registry.
* **Milestone 3:** Develop the Tree-sitter query extractor for Python to emit the Universal Schema.
* **Milestone 4:** Tie components together via the `watchdog` kernel event listener to realize automated, real-time graph patching.