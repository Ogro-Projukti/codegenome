# Codegenome Developer Testing Guide

This guide provides comprehensive instructions for testing **Codegenome** (Watcher CLI) in development mode.

**Project Overview:** Codegenome is an open-source CLI tool for building and querying local codebase knowledge graphs. It uses tree-sitter for code parsing, stores metadata in SQLite, and exposes graph data through an MCP (Model Context Protocol) server.

---

## Table of Contents

1. [Environment Setup](#environment-setup)
2. [Installation for Development](#installation-for-development)
3. [Running Tests](#running-tests)
4. [Manual Testing Workflows](#manual-testing-workflows)
5. [Testing MCP Server](#testing-mcp-server)
6. [Debugging Tips](#debugging-tips)
7. [Common Issues](#common-issues)

---

## Environment Setup

### Prerequisites

- **Python 3.11+** (3.11, 3.12, or 3.13 supported)
- **Git** for version control
- **pip** for package management

### Verify Python Installation

```bash
python --version
# Output should be Python 3.11.x, 3.12.x, or 3.13.x
```

---

## Installation for Development

### 1. Clone the Repository

```bash
git clone https://github.com/Ogro-Projukti/codegenome.git
cd codegenome
```

### 2. Create and Activate Virtual Environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install in Editable Mode with Dev Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- **Core dependencies:** tree-sitter, networkx, watchdog, fastmcp, radon
- **Dev dependencies:** pytest, pytest-cov, ruff, pyinstaller

### 4. Verify Installation

```bash
# Check CLI availability
codegenome --help

# Or run as module
python -m codegenome --help
```

Expected output shows all available commands and flags.

---

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Tests with Coverage Report

```bash
pytest --cov=src/codegenome --cov-report=html
```

Coverage report is generated in `htmlcov/index.html`.

### Run Specific Test File

```bash
pytest tests/test_parser.py -v
pytest tests/test_builder.py -v
pytest tests/test_mcp_server.py -v
```

### Run Tests Matching a Pattern

```bash
# Tests for scanner functionality
pytest -k "scanner" -v

# Tests for timeline features
pytest -k "timeline" -v
```

### Run with Verbose Output

```bash
pytest -v              # Show each test name
pytest -vv             # Very verbose with full test output
pytest -v --tb=short   # Shorter traceback format
pytest -v --tb=long    # Full traceback on failures
```

### Run Tests in Parallel (faster)

```bash
pip install pytest-xdist
pytest -n auto  # Uses all available CPU cores
```

---

## Manual Testing Workflows

### Workflow 1: Build a Graph from a Repository

Test the core graph building functionality.

#### Step 1: Navigate to a Target Repository

```bash
cd /path/to/test/repository
```

Use an existing Python, JavaScript, or Go project (or test on codegenome itself).

#### Step 2: Build a Full Graph

```bash
codegenome --workspace . --build --full
```

Expected output:
- `.watcher/` directory created with:
  - `graph.json` — the extracted code graph
  - `watcher.db` — SQLite database with metadata
  - `build_log.txt` — build summary

#### Step 3: Verify Output

```bash
# Check .watcher directory was created
ls -la .watcher/

# View build log
cat .watcher/build_log.txt

# Check graph file size (should be > 100 bytes for non-empty repos)
ls -lh .watcher/graph.json
```

#### Step 4: Inspect Graph Content (Optional)

```bash
python
>>> import json
>>> with open('.watcher/graph.json') as f:
...     graph = json.load(f)
>>> print(f"Nodes: {len(graph.get('nodes', []))}")
>>> print(f"Edges: {len(graph.get('edges', []))}")
>>> exit()
```

---

### Workflow 2: Export in Multiple Formats

Test the export functionality.

#### Step 1: Build and Export

```bash
# From your test repository directory
codegenome --workspace . --build --export json markdown graphml cypher
```

#### Step 2: Verify Exports

```bash
# Check all export files exist
ls -la .watcher/

# Should see:
# - graph.json
# - graph.md
# - graph.graphml
# - graph.cypher
# - graph_html/ (directory with interactive viewer)
```

#### Step 3: View Markdown Export

```bash
cat .watcher/graph.md | head -50
```

#### Step 4: Test HTML Viewer

```bash
# Open in browser (path depends on OS)
# Windows:
start .watcher/graph_html/index.html

# macOS:
open .watcher/graph_html/index.html

# Linux:
xdg-open .watcher/graph_html/index.html
```

---

### Workflow 3: Watch Mode (Live Updates)

Test the file watcher and incremental rebuild.

#### Step 1: Start Watch Mode

```bash
# From your test repository
codegenome --workspace . --build --watch
```

Expected output:
```
[...] Starting watch mode...
[...] Watching for changes in: /path/to/repo
```

The process should stay running.

#### Step 2: Make File Changes (In Another Terminal)

```bash
# Open another terminal, navigate to the same repo
cd /path/to/test/repository

# Create or modify a file
echo "new_function = lambda x: x + 1" >> test_file.py
```

#### Step 3: Verify Incremental Update

Back in the original terminal, you should see:
```
[...] Detecting changes...
[...] Incremental rebuild: 1 files changed
[...] Graph updated
```

#### Step 4: Stop Watch Mode

```bash
# Press Ctrl+C in the watch mode terminal
```

---

### Workflow 4: Timeline Queries

Test timeline and change history functionality.

#### Step 1: Build with Timeline

```bash
# From your test repository
codegenome --workspace . --build --full
```

#### Step 2: Dump Timeline

```bash
codegenome --workspace . --dump-timeline
```

Expected output: JSON with timeline metadata, change events, and file churn statistics.

#### Step 3: Query Timeline Programmatically (Optional)

```bash
python
>>> from codegenome.timeline import TimelineDB
>>> db = TimelineDB('.watcher/watcher.db')
>>> timeline = db.get_timeline()
>>> print(f"Timeline snapshots: {len(timeline.get('snapshots', []))}")
>>> exit()
```

---

## Testing MCP Server

The MCP (Model Context Protocol) server allows integration with AI clients like Cursor and Claude.

### Workflow 1: Start MCP Server in HTTP Mode

#### Step 1: Build Graph First

```bash
# From your test repository
codegenome --workspace . --build
```

#### Step 2: Start MCP Server

```bash
# HTTP mode (default)
codegenome --workspace . --mcp
```

Expected output:
```
[...] Starting MCP server on http://127.0.0.1:8000
[...] Health check: /health
[...] Resources available at /resources
```

The server stays running.

#### Step 3: Test Health Endpoint (In Another Terminal)

```bash
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

#### Step 4: Query Resources

```bash
curl http://127.0.0.1:8000/resources
```

Returns available MCP resources (code symbols, relationships, etc.).

#### Step 5: Stop Server

```bash
# Press Ctrl+C in the MCP server terminal
```

---

### Workflow 2: MCP Server with Watch + Live Graph

Test real-time updates with MCP.

```bash
# Build with watch and MCP enabled
codegenome --workspace . --build --mcp --watch
```

Make file changes in another terminal (as in Workflow 3). The MCP server updates resources in real-time.

---

### Workflow 3: MCP Server with Stdio Transport (For Agents)

Test stdio mode for direct agent integration.

```bash
codegenome --workspace . --mcp --transport stdio
```

In this mode:
- Server reads JSON-RPC requests from stdin
- Server writes JSON-RPC responses to stdout
- Suitable for direct process integration with Cursor, Claude, etc.

---

## Code Quality Checks

### Linting with Ruff

```bash
# Check for linting issues
ruff check src tests

# Auto-fix issues
ruff check --fix src tests

# Format code
ruff format src tests
```

### Run Linting + Tests Together

```bash
ruff check src tests && pytest
```

---

## Debugging Tips

### Enable Debug Logging

Most modules support debug output via environment variables:

```bash
# Verbose debug output
CODEGENOME_DEBUG=1 codegenome --workspace . --build

# Or with Python module
CODEGENOME_DEBUG=1 python -m codegenome --workspace . --build
```

### Debug in Python REPL

```python
import sys
sys.path.insert(0, 'src')

from codegenome.builder import GraphBuilder
from pathlib import Path

# Build a graph programmatically
builder = GraphBuilder(workspace_dir=Path('.'))
result = builder.build_full()

# Inspect result
print(result)
```

### Inspect SQLite Database

```bash
# With sqlite3 CLI (if installed)
sqlite3 .watcher/watcher.db

# View tables
.tables

# Query symbols
SELECT * FROM symbols LIMIT 10;

# Query relationships
SELECT * FROM relationships LIMIT 10;

# Exit
.quit
```

Or in Python:

```python
import sqlite3

conn = sqlite3.connect('.watcher/watcher.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# Query symbols
cursor.execute("SELECT * FROM symbols LIMIT 5;")
for row in cursor.fetchall():
    print(row)

conn.close()
```

---

## Common Issues

### Issue 1: Virtual Environment Not Activated

**Symptom:** `codegenome: command not found` or `ModuleNotFoundError`

**Solution:**
```bash
# Make sure venv is activated
# Windows:
.venv\Scripts\activate

# macOS/Linux:
source .venv/bin/activate

# Verify prompt shows (.venv)
```

---

### Issue 2: "tree-sitter Not Found" or Language Binding Errors

**Symptom:** `ModuleNotFoundError: No module named 'tree_sitter_python'`

**Solution:**
```bash
# Reinstall dependencies
pip install --upgrade --force-reinstall tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript tree-sitter-go tree-sitter-rust
```

---

### Issue 3: ".watcher Directory Not Created"

**Symptom:** Build completes but no `.watcher/` directory

**Causes:**
- **Empty repository:** Ensure the target repo has source files in supported languages
- **Invalid workspace path:** Use absolute or relative paths, e.g., `.` or `/full/path/to/repo`

**Solution:**
```bash
# Test on codegenome itself
cd /path/to/codegenome
codegenome --workspace . --build --full

# Or test on a known repo
git clone https://github.com/torvalds/linux.git linux-test
cd linux-test
codegenome --workspace . --build  # May take time for large repo
```

---

### Issue 4: MCP Server Port Already in Use

**Symptom:** `Address already in use` on port 8000

**Solution:**
```bash
# Kill the existing process
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# macOS/Linux:
lsof -i :8000
kill -9 <PID>

# Or use a different port (if supported)
codegenome --workspace . --mcp --port 8001
```

---

### Issue 5: Tests Fail Due to Missing Language Grammars

**Symptom:** `ParseError: No grammar found for language`

**Solution:**
```bash
# Tree-sitter needs language grammars; reinstall from scratch
pip uninstall tree-sitter tree-sitter-{python,javascript,typescript,go,rust} -y
pip install -e ".[dev]"
pytest  # Try again
```

---

### Issue 6: Slow Build on Large Repositories

**Symptom:** Build takes > 5 minutes

**Workaround:**
```bash
# Use incremental builds instead of full
codegenome --workspace . --build  # Incremental (faster)

# Exclude large directories
# (Feature may be added in future; currently n/a)
```

---

## Quick Reference: Common Commands

```bash
# Development setup
python -m venv .venv
source .venv/bin/activate     # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Run tests
pytest                          # All tests
pytest -v                       # Verbose
pytest --cov=src/codegenome    # With coverage
pytest -k "parser"             # Specific pattern

# Code quality
ruff check src tests            # Lint
ruff format src tests           # Format

# Graph building
codegenome --workspace . --build            # Incremental
codegenome --workspace . --build --full     # Full rebuild
codegenome --workspace . --build --watch    # Live mode

# Exports
codegenome --workspace . --build --export json markdown graphml cypher

# Timeline
codegenome --workspace . --dump-timeline

# MCP server
codegenome --workspace . --mcp              # HTTP mode
codegenome --workspace . --mcp --watch      # With live updates
codegenome --workspace . --mcp --transport stdio  # Stdio for agents

# Help
codegenome --help
python -m codegenome --help
```

---

## Resources

- **CLI Reference:** See [docs/cli-reference.md](docs/cli-reference.md) for full command documentation
- **Installation Guide:** See [docs/installation.md](docs/installation.md)
- **MCP Integration:** See [docs/mcp-integration.md](docs/mcp-integration.md)
- **Main README:** See [README.md](README.md)

---

## Contributing Tips

When making changes to the codebase:

1. **Write tests first:** Use TDD approach where applicable
2. **Run full test suite:** `pytest -v` before committing
3. **Lint your code:** `ruff check --fix src tests`
4. **Test on multiple Python versions:** If possible, test on 3.11, 3.12, 3.13
5. **Document changes:** Update docstrings and relevant docs
6. **Test MCP integration:** If modifying MCP server, test with actual agents

---

**Happy testing!** 🚀

For issues or questions, refer to the project's GitHub issues or documentation.
