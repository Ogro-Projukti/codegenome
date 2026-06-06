Here is the full documentation for the CodeGenome architecture, incorporating both the foundational biological metaphor and the strategies for handling real-time rendering of massive codebases.

# CodeGenome: Real-Time Codebase Auditing Architecture

## Overview

CodeGenome is a visualization and auditing architecture that maps abstract syntax trees (AST) and dependency graphs into a navigable, biological metaphor. It allows developers and architects to assess codebase health, coupling, and complexity in real-time by treating code as living DNA.

---

## 1. The 6-Level Biological Hierarchy

The architecture progressively discloses information through a strict 6-level hierarchy:

1. **Genome (Entire Repository):** Represented by the `GlobalDependencyRegistry` (powered by `igraph`). Visualized as a Karyotype showing all packages/modules.
2. **Chromosome (Top-Level Package):** A single directory (e.g., `my_package/`). Visual length is proportional to total gene count. Banding colors show aggregate composition.
3. **Chromatid (Sub-module):** A sub-directory. Visualized when a chromosome "unzips" into two strands, revealing cohesion and coupling distances.
4. **Gene (Single File):** A single `.py` or source file. Represented as a rotating segment on the DNA helix. Sized by Lines of Code (LOC) and colored by its dominant base.
5. **Codon (Logical Block):** A class with its methods, or a standalone function with its internal calls. Evaluated for McCabe complexity.
6. **Nucleotide (AST Node):** The foundational block extracted via `tree-sitter`.

---

## 2. Nucleotide Mapping (The A/T/G/C Alphabet)

AST nodes are mapped directly to DNA bases to reveal the structural nature of a file at a glance:

* **A (Adenine / Purple):** Function Definitions (`def`, `async def`). Represents pure logic.
* **T (Thymine / Teal):** Class Definitions (`class`). Represents object-oriented structures. (Pairs with A, revealing the OOP-to-functional ratio).
* **G (Guanine / Coral):** Import Statements. Represents external coupling and dependencies.
* **C (Cytosine / Blue):** Function Calls. Represents execution flow and cross-module connections.

### Extended Base Variants (Epigenetics)

* **G! (Circular Import):** A critical health alert triggered when `igraph` detects a dependency cycle.
* **A* / T* (Decorated/Abstract): Used to denote framework-heavy functions (e.g., routes) or abstract base classes.

---

## 3. Real-Time Evolution & Health Auditing

The system evaluates codebase health dynamically without requiring manual re-scans.

* **Health Score (0.0 – 1.0):** A weighted metric calculated per module combining test coverage, circular dependency rates, zombie nodes (isolated in `igraph`), and average McCabe complexity.
* **Real-Time Backend:** A file-system `watchdog` runs alongside a FastAPI server.
* **Server-Sent Events (SSE):** When a file is saved, the backend updates the AST and dependency graph, recalculates the health score, and pushes a ping to the browser to animate and update the UI instantly.

---

## 4. Scaling Strategy for Massive Codebases

To support repositories with tens of thousands of files and millions of AST nodes, the architecture employs aggressive progressive disclosure and rendering optimizations.

### A. Algorithmic Clustering (Karyotype Level)

* **Problem:** Rendering 500 individual package chromosomes simultaneously is visually overwhelming.
* **Strategy:** For repositories with 100+ modules, the system uses `igraph`'s `community_fastgreedy()` community detection algorithm. Highly coupled modules are grouped into "Community Chromosomes." Clicking a community zooms the Karyotype into the individual modules within that cluster.

### B. Strict Lazy-Loading (API Layer)

* **Problem:** Fetching the entire AST history of a massive repo on startup crashes the browser.
* **Strategy:** Strict endpoint isolation.
* Initial load fetches only the lightweight `GET /genome` (file counts, health scores).
* `GET /genome/{module_id}/graph` (Helix data) and `GET /genome/{module_id}/structure` (Structural data) are *only* fired when the user explicitly clicks a chromosome or gene.



### C. Virtual Rendering Window (Helix Level)

* **Problem:** A 3D HTML5 Canvas rendering 5,000 floating A/T/G/C nodes for a core module will drop frame rates drastically.
* **Strategy:** The helix implements a virtual rendering window. The canvas only calculates coordinates and draws the specific sequence of base pairs that fit inside the user's current scroll viewport. Elements are recycled as the user scrolls, maintaining 30+ FPS.

### D. Semantic Collapsing (Structural Map Level)

* **Problem:** Unpacking a module with 80 files creates an unreadable, infinitely wide UI.
* **Strategy:** Files are chunked logically (e.g., groups of 5). The UI displays a subset of file cards with an "Expand / Load Next 5 Files" action button, protecting DOM memory and user cognitive load.

---

Would you like to start drafting the actual JSON schemas for those API endpoints (`/genome`, `/genome/{id}/graph`) next to lock in the data contract?