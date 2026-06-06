# Patch Summary for branch `v.0.1.5---patch`

## Commits
* 75e3a4e - Rebrand Watcher to CodeGenome and update configs (Md. Fatin Shadab Turja)
* efa56ca - patch (Md. Fatin Shadab Turja)

## Changed Files
```text
 .cursor/mcp.json                                   | 10 +++++++
 ...ge-graph.mdc => codegenome-knowledge-graph.mdc} |  2 +-
 .github/copilot-instructions.md                    |  2 +-
 .gitignore                                         |  4 +--
 .vscode/cline_mcp_settings.json                    | 10 +++++++
 .vscode/mcp.json                                   | 10 +++++++
 .windsurfrules                                     |  2 +-
 AGENTS.md                                          |  2 +-
 CONTRIBUTING.md                                    |  4 +--
 CURSOR_MCP_SETUP.md                                | 33 ++++++++++++++++++++++
 README.md                                          |  2 +-
 build_cli.py                                       |  6 ++--
 docs/cli-reference.md                              |  4 +--
 docs/installation.md                               |  8 +++---
 docs/mcp-integration.md                            | 28 +++++++++---------
 extensions/README.md                               |  8 +++---
 extensions/templates/claude-instructions.md        |  2 +-
 ...ge-graph.mdc => codegenome-knowledge-graph.mdc} |  2 +-
 extensions/templates/copilot-instructions.md       |  2 +-
 pyproject.toml                                     | 10 +++----
 src/codegenome/__init__.py                         |  6 ++--
 src/codegenome/__main__.py                         | 18 ++++++------
 src/codegenome/ai_chat.py                          |  2 +-
 src/codegenome/assets/html/graph-viewer.js         |  4 +--
 src/codegenome/builder.py                          |  2 +-
 src/codegenome/cli.py                              | 22 +++++++--------
 src/codegenome/clusterer.py                        |  2 +-
 src/codegenome/{watcher.py => core.py}             | 30 ++++++++++----------
 src/codegenome/exporter.py                         | 10 +++----
 src/codegenome/graph_store.py                      |  4 +--
 src/codegenome/installer.py                        | 12 ++++----
 src/codegenome/intelligence.py                     |  4 +--
 src/codegenome/live_graph_monitor.py               |  8 +++---
 src/codegenome/mcp_server.py                       | 18 ++++++------
 src/codegenome/parser.py                           |  4 +--
 src/codegenome/rules.py                            |  4 +--
 src/codegenome/templates/graph.html.j2             |  2 +-
 src/codegenome/templates/rules/cursor-rules.mdc    |  2 +-
 .../templates/rules/markdown-instructions.md       |  2 +-
 src/codegenome/timeline.py                         |  2 +-
 test2.py                                           | 13 +++++++++
 tests/test_mcp_server.py                           |  2 +-
 42 files changed, 200 insertions(+), 124 deletions(-)

```

## Diff
```diff
diff --git a/.cursor/mcp.json b/.cursor/mcp.json
new file mode 100644
index 0000000..82adbbd
--- /dev/null
+++ b/.cursor/mcp.json
@@ -0,0 +1,10 @@
+{
+  "mcpServers": {
+    "codegenome": {
+      "command": "codegenome",
+      "args": [
+        "mcp-start"
+      ]
+    }
+  }
+}
diff --git a/.cursor/rules/watcher-knowledge-graph.mdc b/.cursor/rules/codegenome-knowledge-graph.mdc
similarity index 92%
rename from .cursor/rules/watcher-knowledge-graph.mdc
rename to .cursor/rules/codegenome-knowledge-graph.mdc
index 42b7600..76b5bd3 100644
--- a/.cursor/rules/watcher-knowledge-graph.mdc
+++ b/.cursor/rules/codegenome-knowledge-graph.mdc
@@ -9,7 +9,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:7331/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/.github/copilot-instructions.md b/.github/copilot-instructions.md
index b512202..5e4ae97 100644
--- a/.github/copilot-instructions.md
+++ b/.github/copilot-instructions.md
@@ -4,7 +4,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:7331/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/.gitignore b/.gitignore
index f924f6f..6d1d34c 100644
--- a/.gitignore
+++ b/.gitignore
@@ -12,9 +12,9 @@ dist/
 build/
 *.spec
 
-# Watcher runtime artifacts
+# CodeGenome runtime artifacts
 .genome/
-watcher.db
+codegenome.db
 
 # OS / IDE
 .DS_Store
diff --git a/.vscode/cline_mcp_settings.json b/.vscode/cline_mcp_settings.json
new file mode 100644
index 0000000..82adbbd
--- /dev/null
+++ b/.vscode/cline_mcp_settings.json
@@ -0,0 +1,10 @@
+{
+  "mcpServers": {
+    "codegenome": {
+      "command": "codegenome",
+      "args": [
+        "mcp-start"
+      ]
+    }
+  }
+}
diff --git a/.vscode/mcp.json b/.vscode/mcp.json
new file mode 100644
index 0000000..82adbbd
--- /dev/null
+++ b/.vscode/mcp.json
@@ -0,0 +1,10 @@
+{
+  "mcpServers": {
+    "codegenome": {
+      "command": "codegenome",
+      "args": [
+        "mcp-start"
+      ]
+    }
+  }
+}
diff --git a/.windsurfrules b/.windsurfrules
index b512202..5e4ae97 100644
--- a/.windsurfrules
+++ b/.windsurfrules
@@ -4,7 +4,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:7331/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/AGENTS.md b/AGENTS.md
index b512202..5e4ae97 100644
--- a/AGENTS.md
+++ b/AGENTS.md
@@ -4,7 +4,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:7331/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/CONTRIBUTING.md b/CONTRIBUTING.md
index 7a1a6eb..32ae667 100644
--- a/CONTRIBUTING.md
+++ b/CONTRIBUTING.md
@@ -165,7 +165,7 @@ Graph artifacts are written under `.genome/` in the analyzed workspace. See [doc
 
 ### Optional: standalone binary
 
-To build a PyInstaller binary (named `watcher` in `dist/`):
+To build a PyInstaller binary (named `codegenome` in `dist/`):
 
 ```bash
 python build_cli.py
@@ -235,7 +235,7 @@ For MCP or client integration problems, also note which client (Cursor, Claude D
 
 ## Documentation
 
-When updating user-facing docs, use **`codegenome`** as the primary CLI name. Document legacy flag-based usage as `python -m codegenome --…`. The on-disk database file remains `.genome/watcher.db`.
+When updating user-facing docs, use **`codegenome`** as the primary CLI name. Document legacy flag-based usage as `python -m codegenome --…`. The on-disk database file remains `.genome/codegenome.db`.
 
 | Document | Purpose |
 |----------|---------|
diff --git a/CURSOR_MCP_SETUP.md b/CURSOR_MCP_SETUP.md
new file mode 100644
index 0000000..19b0180
--- /dev/null
+++ b/CURSOR_MCP_SETUP.md
@@ -0,0 +1,33 @@
+# CodeGenome Cursor MCP Setup
+
+This project uses **CodeGenome** to provide an architectural knowledge graph that helps Cursor understand the codebase deeply.
+
+## Prerequisites
+
+1. Ensure `codegenome` is installed in your environment:
+   ```bash
+   pip install codegenome
+   ```
+2. You must generate the initial knowledge graph so that the `codegenome.db` exists. Run:
+   ```bash
+   codegenome analyze
+   ```
+   *Note: This repository is already configured to ignore `.genome/codegenome.db` in `.gitignore`.*
+
+## Cursor MCP Integration
+
+Cursor automatically reads the `.cursor/mcp.json` file in this repository. The configuration points to the `codegenome mcp-start` command. 
+
+Once Cursor connects to the MCP server, it will generate the necessary tool configurations under `.cursor/mcps/` automatically at runtime.
+
+### Troubleshooting
+
+- **Server Not Starting?** If Cursor cannot find the `codegenome` command, you may need to update the `command` field in `.cursor/mcp.json` to point to the absolute path of your `codegenome` executable (e.g., inside your virtual environment, like `.venv/bin/codegenome` or `.venv/Scripts/codegenome.exe`), or run Cursor from an activated terminal.
+- **Tools Missing?** Ensure that `.genome/codegenome.db` has been created by running `codegenome analyze`.
+
+## Continuous Updates
+
+To keep the CodeGenome knowledge graph updated automatically as you edit files, run the live codegenome in the background:
+```bash
+codegenome evolve --live
+```
diff --git a/README.md b/README.md
index e562be8..b53e59d 100644
--- a/README.md
+++ b/README.md
@@ -92,7 +92,7 @@ codegenome evolve --live --lan .
 ## 🛠️ Troubleshooting
 
 ### 1. "No graph found" or Missing Database
-**Symptom:** When attempting to run the MCP server (`codegenome mcp-start`) or export the graph (`codegenome export`), you receive an error that no graph was found or `.genome/watcher.db` does not exist.
+**Symptom:** When attempting to run the MCP server (`codegenome mcp-start`) or export the graph (`codegenome export`), you receive an error that no graph was found or `.genome/codegenome.db` does not exist.
 **Solution:** Codegenome needs to build its initial knowledge graph database before it can be served or exported. Always run `codegenome analyze .` in your workspace first to generate the graph.
 
 ### 2. "unrecognized arguments" CLI Error
diff --git a/build_cli.py b/build_cli.py
index dd99e63..9ac60b6 100644
--- a/build_cli.py
+++ b/build_cli.py
@@ -1,5 +1,5 @@
 #!/usr/bin/env python3
-"""Build a standalone watcher CLI binary with PyInstaller."""
+"""Build a standalone codegenome CLI binary with PyInstaller."""
 
 from __future__ import annotations
 
@@ -16,7 +16,7 @@ DIST = ROOT / "dist"
 BUILD = ROOT / "build"
 SPEC = ROOT / "codegenome.spec"
 
-BINARY_NAME = "watcher"
+BINARY_NAME = "codegenome"
 
 HIDDEN_IMPORTS = [
     "codegenome",
@@ -187,7 +187,7 @@ def build(*, clean: bool = True) -> Path:
 
 
 def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
-    parser = argparse.ArgumentParser(description="Build watcher standalone binary")
+    parser = argparse.ArgumentParser(description="Build codegenome standalone binary")
     parser.add_argument(
         "--no-clean",
         action="store_true",
diff --git a/docs/cli-reference.md b/docs/cli-reference.md
index 56a7c9f..7a31eab 100644
--- a/docs/cli-reference.md
+++ b/docs/cli-reference.md
@@ -13,7 +13,7 @@ Both operate on a **workspace** (project root). By default that is the current d
 
 | Path | Purpose |
 |------|---------|
-| `.genome/watcher.db` | Timeline snapshots (SQLite) |
+| `.genome/codegenome.db` | Timeline snapshots (SQLite) |
 | `.genome/graph.json` | Latest graph |
 | `.genome/exports/` | HTML, Markdown, GraphML, etc. |
 | `.genome/scan_cache.db` | Incremental scan cache |
@@ -240,7 +240,7 @@ Terminal 2:
 
 ```bash
 python -m codegenome.installer \
-  --db-path "$(pwd)/.genome/watcher.db" \
+  --db-path "$(pwd)/.genome/codegenome.db" \
   --client cursor \
   --transport http
 codegenome rules --client cursor .
diff --git a/docs/installation.md b/docs/installation.md
index a697da8..adfe7f1 100644
--- a/docs/installation.md
+++ b/docs/installation.md
@@ -67,7 +67,7 @@ Codegenome writes artifacts under `<workspace>/.genome/`:
 | Path | Purpose |
 |------|---------|
 | `.genome/graph.json` | Latest graph |
-| `.genome/watcher.db` | Timeline snapshots (SQLite) |
+| `.genome/codegenome.db` | Timeline snapshots (SQLite) |
 | `.genome/exports/` | HTML, Markdown, GraphML, etc. |
 | `.genome/scan_cache.db` | Incremental scan cache |
 
@@ -93,7 +93,7 @@ python -m codegenome --workspace . --build --mcp --watch
 
 ```bash
 python -m codegenome.installer \
-  --db-path "$(pwd)/.genome/watcher.db" \
+  --db-path "$(pwd)/.genome/codegenome.db" \
   --client cursor \
   --transport http \
   --host 127.0.0.1 \
@@ -119,7 +119,7 @@ Or run the standalone server module:
 
 ```bash
 python -m codegenome.mcp_server \
-  --db-path ./.genome/watcher.db \
+  --db-path ./.genome/codegenome.db \
   --transport stdio
 ```
 
@@ -127,7 +127,7 @@ See [MCP integration](mcp-integration.md) for environment variables, supported c
 
 ## Optional: standalone binary
 
-To build a PyInstaller binary named `watcher` in `dist/` (requires the `dev` extra):
+To build a PyInstaller binary named `codegenome` in `dist/` (requires the `dev` extra):
 
 ```bash
 python build_cli.py
diff --git a/docs/mcp-integration.md b/docs/mcp-integration.md
index ed75076..d04a02f 100644
--- a/docs/mcp-integration.md
+++ b/docs/mcp-integration.md
@@ -18,7 +18,7 @@ python -m codegenome --workspace . --build --mcp --watch
 
 # Terminal 2: install client config
 python -m codegenome.installer \
-  --db-path "$(pwd)/.genome/watcher.db" \
+  --db-path "$(pwd)/.genome/codegenome.db" \
   --client cursor \
   --transport http \
   --host 127.0.0.1 \
@@ -43,7 +43,7 @@ Or configure clients to run the module directly:
 
 ```bash
 python -m codegenome.mcp_server \
-  --db-path ./.genome/watcher.db \
+  --db-path ./.genome/codegenome.db \
   --transport stdio
 ```
 
@@ -56,14 +56,14 @@ python -m codegenome.mcp_server --help
 
 # HTTP
 python -m codegenome.mcp_server \
-  --db-path ./.genome/watcher.db \
+  --db-path ./.genome/codegenome.db \
   --host 127.0.0.1 \
   --port 7331 \
   --transport http
 
 # Stdio
 python -m codegenome.mcp_server \
-  --db-path ./.genome/watcher.db \
+  --db-path ./.genome/codegenome.db \
   --transport stdio
 ```
 
@@ -75,7 +75,7 @@ python -m codegenome.installer --help
 
 | Flag | Description |
 |------|-------------|
-| `--db-path PATH` | Absolute path to `.genome/watcher.db` |
+| `--db-path PATH` | Absolute path to `.genome/codegenome.db` |
 | `--python PATH` | Python executable for stdio transport |
 | `--transport stdio\|http` | Config transport mode |
 | `--host HOST` | HTTP host in config |
@@ -101,12 +101,12 @@ Always use **absolute paths** for `--db-path`.
 
 | Variable | Default | Purpose |
 |----------|---------|---------|
-| `WATCHER_MCP_DB_PATH` | `test.db` | Database path |
-| `WATCHER_MCP_HOST` | `127.0.0.1` | HTTP bind host |
-| `WATCHER_MCP_PORT` | `7331` | HTTP bind port |
-| `WATCHER_MCP_TRANSPORT` | `http` | `http` or `stdio` |
-| `WATCHER_MCP_TIMEOUT` | `30` | Tool timeout (seconds) |
-| `WATCHER_MCP_LOG_LEVEL` | `INFO` | Log level |
+| `CODEGENOME_MCP_DB_PATH` | `test.db` | Database path |
+| `CODEGENOME_MCP_HOST` | `127.0.0.1` | HTTP bind host |
+| `CODEGENOME_MCP_PORT` | `7331` | HTTP bind port |
+| `CODEGENOME_MCP_TRANSPORT` | `http` | `http` or `stdio` |
+| `CODEGENOME_MCP_TIMEOUT` | `30` | Tool timeout (seconds) |
+| `CODEGENOME_MCP_LOG_LEVEL` | `INFO` | Log level |
 
 ## Health check
 
@@ -129,8 +129,8 @@ Manual Cursor rule install:
 
 ```bash
 mkdir -p .cursor/rules
-sed 's/{{MCP_PORT}}/7331/g' extensions/templates/watcher-knowledge-graph.mdc \
-  > .cursor/rules/watcher-knowledge-graph.mdc
+sed 's/{{MCP_PORT}}/7331/g' extensions/templates/codegenome-knowledge-graph.mdc \
+  > .cursor/rules/codegenome-knowledge-graph.mdc
 ```
 
 On Windows PowerShell, copy the template and replace `{{MCP_PORT}}` with `7331` manually or use your editor's find-and-replace.
@@ -157,7 +157,7 @@ codegenome analyze .
 |---------|----------|
 | Connection refused | Run HTTP MCP (`python -m codegenome --mcp --build --watch`) or `mcp_server`; ensure the graph was built |
 | Port 7331 in use | Stop the other instance or run `mcp_server --port 7332` and update client config |
-| Empty tool results | Run `codegenome analyze .` first; confirm `.genome/watcher.db` exists |
+| Empty tool results | Run `codegenome analyze .` first; confirm `.genome/codegenome.db` exists |
 | Client not using MCP | Restart the client after `installer`; verify the config file path |
 | Stdio vs HTTP mismatch | Match `--transport` in `installer` with how the server is started |
 
diff --git a/extensions/README.md b/extensions/README.md
index 073a1a2..19bcd58 100644
--- a/extensions/README.md
+++ b/extensions/README.md
@@ -6,7 +6,7 @@ This folder holds **editor and agent integration assets** that ship with the Cod
 
 | Path | Purpose |
 |------|---------|
-| `templates/watcher-knowledge-graph.mdc` | Cursor rule template — teaches agents to use Codegenome MCP tools |
+| `templates/codegenome-knowledge-graph.mdc` | Cursor rule template — teaches agents to use Codegenome MCP tools |
 | `templates/copilot-instructions.md` | GitHub Copilot instructions template |
 | `templates/claude-instructions.md` | Claude-oriented instructions template |
 
@@ -32,7 +32,7 @@ Write MCP server entries into AI client config files:
 
 ```bash
 python -m codegenome.installer \
-  --db-path /absolute/path/to/project/.genome/watcher.db \
+  --db-path /absolute/path/to/project/.genome/codegenome.db \
   --client cursor \
   --transport http \
   --host 127.0.0.1 \
@@ -47,8 +47,8 @@ See [MCP integration](../docs/mcp-integration.md) for transport modes, health ch
 
 ```bash
 mkdir -p .cursor/rules
-sed 's/{{MCP_PORT}}/7331/g' extensions/templates/watcher-knowledge-graph.mdc \
-  > .cursor/rules/watcher-knowledge-graph.mdc
+sed 's/{{MCP_PORT}}/7331/g' extensions/templates/codegenome-knowledge-graph.mdc \
+  > .cursor/rules/codegenome-knowledge-graph.mdc
 ```
 
 Restart Cursor after installing MCP config or rules.
diff --git a/extensions/templates/claude-instructions.md b/extensions/templates/claude-instructions.md
index 3666328..a959330 100644
--- a/extensions/templates/claude-instructions.md
+++ b/extensions/templates/claude-instructions.md
@@ -4,7 +4,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:{{MCP_PORT}}/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/extensions/templates/watcher-knowledge-graph.mdc b/extensions/templates/codegenome-knowledge-graph.mdc
similarity index 92%
rename from extensions/templates/watcher-knowledge-graph.mdc
rename to extensions/templates/codegenome-knowledge-graph.mdc
index 6796262..dab6019 100644
--- a/extensions/templates/watcher-knowledge-graph.mdc
+++ b/extensions/templates/codegenome-knowledge-graph.mdc
@@ -9,7 +9,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:{{MCP_PORT}}/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/extensions/templates/copilot-instructions.md b/extensions/templates/copilot-instructions.md
index 3666328..a959330 100644
--- a/extensions/templates/copilot-instructions.md
+++ b/extensions/templates/copilot-instructions.md
@@ -4,7 +4,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:{{MCP_PORT}}/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/pyproject.toml b/pyproject.toml
index dc9c188..76fd884 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -9,7 +9,7 @@ description = "Open-source CLI for building and querying local codebase knowledg
 readme = "README.md"
 license = "MIT"
 requires-python = ">=3.11"
-authors = [{ name = "Watcher Contributors" }]
+authors = [{ name = "CodeGenome Contributors" }]
 keywords = ["code-analysis", "knowledge-graph", "mcp", "cli", "tree-sitter"]
 classifiers = [
   "Development Status :: 3 - Alpha",
@@ -52,10 +52,10 @@ dependencies = [
 dev = ["pytest", "pytest-cov", "ruff", "pyinstaller>=6.0,<7"]
 
 [project.urls]
-Homepage = "https://github.com/watcher-dev/codegenome"
-Documentation = "https://github.com/watcher-dev/codegenome#readme"
-Repository = "https://github.com/watcher-dev/codegenome"
-Issues = "https://github.com/watcher-dev/codegenome/issues"
+Homepage = "https://github.com/codegenome-dev/codegenome"
+Documentation = "https://github.com/codegenome-dev/codegenome#readme"
+Repository = "https://github.com/codegenome-dev/codegenome"
+Issues = "https://github.com/codegenome-dev/codegenome/issues"
 
 [project.scripts]
 codegenome = "codegenome.cli:cli"
diff --git a/src/codegenome/__init__.py b/src/codegenome/__init__.py
index 391fc78..5609da8 100644
--- a/src/codegenome/__init__.py
+++ b/src/codegenome/__init__.py
@@ -12,7 +12,7 @@ from .parser import ParseResult, SourceParser
 from .scanner import ScanResult, WorkspaceScanner
 from .timeline import GraphDelta, GraphTimeline, SnapshotInfo
 from .version import __version__
-from .watcher import BuildResult, WatcherConfig, WatcherEngine
+from .core import BuildResult, CodeGenomeConfig, CodeGenomeEngine
 
 __all__ = [
     "__version__",
@@ -31,7 +31,7 @@ __all__ = [
     "SnapshotInfo",
     "SourceParser",
     "SUPPORTED_FORMATS",
-    "WatcherConfig",
-    "WatcherEngine",
+    "CodeGenomeConfig",
+    "CodeGenomeEngine",
     "WorkspaceScanner",
 ]
diff --git a/src/codegenome/__main__.py b/src/codegenome/__main__.py
index 5f6606e..6542aaa 100644
--- a/src/codegenome/__main__.py
+++ b/src/codegenome/__main__.py
@@ -1,4 +1,4 @@
-"""CLI entry point for Watcher."""
+"""CLI entry point for CodeGenome."""
 
 from __future__ import annotations
 
@@ -9,13 +9,13 @@ import sys
 from pathlib import Path
 
 from codegenome.exporter import SUPPORTED_FORMATS
-from codegenome.watcher import WatcherConfig, WatcherEngine
+from codegenome.core import CodeGenomeConfig, CodeGenomeEngine
 
 LOG = logging.getLogger("codegenome")
 
 
 def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
-    """Parse command line arguments for the Watcher CLI.
+    """Parse command line arguments for the CodeGenome CLI.
 
     Args:
         argv (list[str] | None, optional): List of command line arguments. Defaults to None,
@@ -24,7 +24,7 @@ def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
     Returns:
         argparse.Namespace: The parsed command line arguments.
     """
-    parser = argparse.ArgumentParser(description="Watcher CLI — local codebase knowledge graph")
+    parser = argparse.ArgumentParser(description="CodeGenome CLI — local codebase knowledge graph")
     parser.add_argument(
         "--workspace",
         default=".",
@@ -78,7 +78,7 @@ def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
     parser.add_argument(
         "--db-path",
         default=None,
-        help="Timeline SQLite database path (default: .genome/watcher.db)",
+        help="Timeline SQLite database path (default: .genome/codegenome.db)",
     )
     parser.add_argument(
         "--mcp",
@@ -149,7 +149,7 @@ def run_timeline_query(args: argparse.Namespace) -> int:
     from codegenome.graph_store import GraphStore, GraphStoreError
 
     workspace = Path(args.workspace).resolve()
-    db_path = Path(args.db_path).resolve() if args.db_path else workspace / ".genome" / "watcher.db"
+    db_path = Path(args.db_path).resolve() if args.db_path else workspace / ".genome" / "codegenome.db"
 
     store = GraphStore(db_path)
     try:
@@ -186,7 +186,7 @@ def run_timeline_query(args: argparse.Namespace) -> int:
 
 
 def main(argv: list[str] | None = None) -> int:
-    """Main entry point for the codegenome Watcher CLI.
+    """Main entry point for the codegenome CodeGenome CLI.
 
     Args:
         argv (list[str] | None, optional): List of command line arguments. Defaults to None.
@@ -232,7 +232,7 @@ def main(argv: list[str] | None = None) -> int:
         print("Nothing to do. Pass --build, --watch, and/or --live-graph.", file=sys.stderr)
         return 1
 
-    config = WatcherConfig(
+    config = CodeGenomeConfig(
         workspace=workspace,
         db_path=Path(args.db_path).resolve() if args.db_path else None,
         export_formats=tuple(fmt.lower() for fmt in args.export),
@@ -241,7 +241,7 @@ def main(argv: list[str] | None = None) -> int:
         live_graph=args.live_graph,
         live_graph_poll_seconds=max(1.0, float(args.live_graph_interval)),
     )
-    engine = WatcherEngine(config)
+    engine = CodeGenomeEngine(config)
 
     try:
         if args.build or args.watch or args.live_graph:
diff --git a/src/codegenome/ai_chat.py b/src/codegenome/ai_chat.py
index e6752ca..eccb141 100644
--- a/src/codegenome/ai_chat.py
+++ b/src/codegenome/ai_chat.py
@@ -102,7 +102,7 @@ CONTEXT_PROFILES = {
 }
 DEFAULT_HTTP_HEADERS = {
     "Accept": "application/json",
-    "User-Agent": "CodeGenome/0.1 (+https://github.com/watcher-dev/codegenome)",
+    "User-Agent": "CodeGenome/0.1 (+https://github.com/codegenome-dev/codegenome)",
 }
 
 
diff --git a/src/codegenome/assets/html/graph-viewer.js b/src/codegenome/assets/html/graph-viewer.js
index c179b6d..db8eaf0 100644
--- a/src/codegenome/assets/html/graph-viewer.js
+++ b/src/codegenome/assets/html/graph-viewer.js
@@ -152,7 +152,7 @@
 
     if (window.location.protocol === 'file:') {
       setLivePending(false);
-      showToast('Open via Watcher extension for live updates.');
+      showToast('Open via CodeGenome extension for live updates.');
       return;
     }
 
@@ -183,7 +183,7 @@
   }
 
   function readEmbeddedGraph() {
-    const element = document.getElementById('watcher-graph-data');
+    const element = document.getElementById('codegenome-graph-data');
     if (!element || !element.textContent) {
       return null;
     }
diff --git a/src/codegenome/builder.py b/src/codegenome/builder.py
index e8ac0cf..d49dfdc 100644
--- a/src/codegenome/builder.py
+++ b/src/codegenome/builder.py
@@ -1,4 +1,4 @@
-"""NetworkX graph builder for Watcher scan and parse results."""
+"""NetworkX graph builder for CodeGenome scan and parse results."""
 
 from __future__ import annotations
 
diff --git a/src/codegenome/cli.py b/src/codegenome/cli.py
index 1b80560..e568248 100644
--- a/src/codegenome/cli.py
+++ b/src/codegenome/cli.py
@@ -4,7 +4,7 @@ import sys
 from pathlib import Path
 import click
 
-from codegenome.watcher import WatcherEngine, WatcherConfig
+from codegenome.core import CodeGenomeEngine, CodeGenomeConfig
 
 @click.group()
 def cli():
@@ -21,8 +21,8 @@ def analyze(path: str):
     """
     click.echo(f"Analyzing workspace at {path}...")
     workspace = Path(path).resolve()
-    config = WatcherConfig(workspace=workspace, export_formats=("json",))
-    engine = WatcherEngine(config)
+    config = CodeGenomeConfig(workspace=workspace, export_formats=("json",))
+    engine = CodeGenomeEngine(config)
 
     def on_progress(message: str) -> None:
         click.echo(message)
@@ -59,12 +59,12 @@ def export(export_format: str, path: str):
         path (str): The workspace directory path to export from.
     """
     workspace = Path(path).resolve()
-    config = WatcherConfig(workspace=workspace)
-    engine = WatcherEngine(config)
+    config = CodeGenomeConfig(workspace=workspace)
+    engine = CodeGenomeEngine(config)
     
     try:
         # Check if the graph exists. If not loaded, it means it hasn't been analyzed.
-        # engine._load_existing_graph() is called in WatcherEngine.__init__.
+        # engine._load_existing_graph() is called in CodeGenomeEngine.__init__.
         # Alternatively, we can check if the graph has nodes.
         if engine.builder.graph.number_of_nodes() == 0:
             click.echo("Error: No graph found. Please run 'codegenome analyze' first before exporting.", err=True)
@@ -119,8 +119,8 @@ def mcp_start(path: str, transport: str, port: int, lan: bool):
         lan (bool): Whether to expose HTTP transport on the local network.
     """
     workspace = Path(path).resolve()
-    config = WatcherConfig(workspace=workspace)
-    engine = WatcherEngine(config)
+    config = CodeGenomeConfig(workspace=workspace)
+    engine = CodeGenomeEngine(config)
     db_path = engine.db_path
     engine.close()  # Close the engine since the MCP server process will open its own connection
     
@@ -159,11 +159,11 @@ def evolve(path: str, live: bool, lan: bool):
     from socketserver import ThreadingTCPServer
     from watchdog.observers import Observer
     from codegenome.ai_chat import AIChatError, chat_completion, load_models, settings_payload
-    from codegenome.watcher import WatcherConfig, WatcherEngine, SurgicalUpdateHandler
+    from codegenome.core import CodeGenomeConfig, CodeGenomeEngine, SurgicalUpdateHandler
 
     workspace = Path(path).resolve()
-    config = WatcherConfig(workspace=workspace, export_formats=("json", "html"))
-    engine = WatcherEngine(config)
+    config = CodeGenomeConfig(workspace=workspace, export_formats=("json", "html"))
+    engine = CodeGenomeEngine(config)
     
     click.echo(f"Running initial build for {workspace}...")
     engine.build(full=False)
diff --git a/src/codegenome/clusterer.py b/src/codegenome/clusterer.py
index 323147c..ae0b8c7 100644
--- a/src/codegenome/clusterer.py
+++ b/src/codegenome/clusterer.py
@@ -1,4 +1,4 @@
-"""Leiden community detection and bridge-node analysis for Watcher graphs."""
+"""Leiden community detection and bridge-node analysis for CodeGenome graphs."""
 
 from __future__ import annotations
 
diff --git a/src/codegenome/watcher.py b/src/codegenome/core.py
similarity index 95%
rename from src/codegenome/watcher.py
rename to src/codegenome/core.py
index 07d0c3e..fc0e406 100644
--- a/src/codegenome/watcher.py
+++ b/src/codegenome/core.py
@@ -1,4 +1,4 @@
-"""WatcherEngine orchestration for builds, watching, MCP, and exports."""
+"""CodeGenomeEngine orchestration for builds, watching, MCP, and exports."""
 
 from __future__ import annotations
 
@@ -35,8 +35,8 @@ PARSE_PROGRESS_INTERVAL = 50
 
 
 @dataclass
-class WatcherConfig:
-    """Configuration for WatcherEngine."""
+class CodeGenomeConfig:
+    """Configuration for CodeGenomeEngine."""
 
     workspace: Path
     db_path: Path | None = None
@@ -53,7 +53,7 @@ class WatcherConfig:
 
 @dataclass
 class BuildResult:
-    """Container for the output of a WatcherEngine build or update."""
+    """Container for the output of a CodeGenomeEngine build or update."""
 
     graph: nx.DiGraph
     report: IntelligenceReport
@@ -64,11 +64,11 @@ class BuildResult:
 class _RebuildHandler(FileSystemEventHandler):
     """File system event handler to trigger incremental rebuilds with debouncing."""
 
-    def __init__(self, engine: WatcherEngine, debounce_seconds: float) -> None:
+    def __init__(self, engine: CodeGenomeEngine, debounce_seconds: float) -> None:
         """Initialize the _RebuildHandler.
 
         Args:
-            engine (WatcherEngine): The engine to invoke rebuilds on.
+            engine (CodeGenomeEngine): The engine to invoke rebuilds on.
             debounce_seconds (float): Delay in seconds before triggering a rebuild.
         """
         self._engine = engine
@@ -108,17 +108,17 @@ class _RebuildHandler(FileSystemEventHandler):
         )
         try:
             self._engine.rebuild_incremental()
-        except Exception:  # noqa: BLE001 - keep watcher alive
+        except Exception:  # noqa: BLE001 - keep codegenome alive
             LOG.exception("Incremental rebuild failed")
 
 
 class SurgicalUpdateHandler(FileSystemEventHandler):
     """Surgically update the graph on individual file changes."""
-    def __init__(self, engine: WatcherEngine, live_server=None) -> None:
+    def __init__(self, engine: CodeGenomeEngine, live_server=None) -> None:
         """Initialize the SurgicalUpdateHandler.
 
         Args:
-            engine (WatcherEngine): The engine performing graph updates.
+            engine (CodeGenomeEngine): The engine performing graph updates.
             live_server (LiveGraphServer | None, optional): Server for real-time broadcasts. Defaults to None.
         """
         self._engine = engine
@@ -168,19 +168,19 @@ class SurgicalUpdateHandler(FileSystemEventHandler):
                 LOG.exception(f"Surgical update failed for {event.src_path}")
 
 
-class WatcherEngine:
+class CodeGenomeEngine:
     """Coordinate scanning, graph building, exports, watching, and MCP startup."""
 
-    def __init__(self, config: WatcherConfig) -> None:
-        """Initialize the WatcherEngine.
+    def __init__(self, config: CodeGenomeConfig) -> None:
+        """Initialize the CodeGenomeEngine.
 
         Args:
-            config (WatcherConfig): The configuration defining paths and options.
+            config (CodeGenomeConfig): The configuration defining paths and options.
         """
         self.config = config
         self.workspace = config.workspace.resolve()
         self.genome_dir = self.workspace / ".genome"
-        self.db_path = (config.db_path or self.genome_dir / "watcher.db").resolve()
+        self.db_path = (config.db_path or self.genome_dir / "codegenome.db").resolve()
         self.export_dir = (config.export_dir or self.genome_dir / "exports").resolve()
         self.graph_json_path = (
             config.graph_json_path or self.genome_dir / "graph.json"
@@ -479,7 +479,7 @@ class WatcherEngine:
                 sys.stderr.write(line)
                 sys.stderr.flush()
 
-        thread = threading.Thread(target=forward, name="watcher-mcp-stderr", daemon=True)
+        thread = threading.Thread(target=forward, name="codegenome-mcp-stderr", daemon=True)
         thread.start()
 
     def stop_mcp(self) -> None:
diff --git a/src/codegenome/exporter.py b/src/codegenome/exporter.py
index a7320b2..e2d1591 100644
--- a/src/codegenome/exporter.py
+++ b/src/codegenome/exporter.py
@@ -1,4 +1,4 @@
-"""Export Watcher graphs to JSON, HTML, GraphML, Cypher, Markdown, and Obsidian."""
+"""Export CodeGenome graphs to JSON, HTML, GraphML, Cypher, Markdown, and Obsidian."""
 
 from __future__ import annotations
 
@@ -65,7 +65,7 @@ class GraphStatistics:
 
 @dataclass
 class GraphExporter:
-    """Serialize Watcher graphs and intelligence into multiple formats.
+    """Serialize CodeGenome graphs and intelligence into multiple formats.
 
     Attributes:
         graph (Graph): The graph instance to be exported.
@@ -212,7 +212,7 @@ class GraphExporter:
             Path: The path to the successfully created Cypher file.
         """
         lines = [
-            "// Watcher graph export for Neo4j",
+            "// CodeGenome graph export for Neo4j",
             f"// workspace: {self.workspace_name}",
             "",
         ]
@@ -294,7 +294,7 @@ class GraphExporter:
             )
 
         index_lines = [
-            "# Watcher Graph Vault",
+            "# CodeGenome Graph Vault",
             "",
             f"Workspace: `{self.workspace_name}`",
             "",
@@ -313,7 +313,7 @@ class GraphExporter:
                     f"- Circular dependency groups: {len(self.report.circular_dependencies)}",
                 ]
             )
-        vault_root.joinpath("Watcher Index.md").write_text(
+        vault_root.joinpath("CodeGenome Index.md").write_text(
             "\n".join(index_lines) + "\n",
             encoding="utf-8",
         )
diff --git a/src/codegenome/graph_store.py b/src/codegenome/graph_store.py
index cfbd9a5..25b0592 100644
--- a/src/codegenome/graph_store.py
+++ b/src/codegenome/graph_store.py
@@ -1,4 +1,4 @@
-"""Graph query layer for the Watcher MCP server."""
+"""Graph query layer for the CodeGenome MCP server."""
 
 from __future__ import annotations
 
@@ -37,7 +37,7 @@ class GraphSummary:
 
 
 class GraphStore:
-    """Load and query a Watcher timeline database.
+    """Load and query a CodeGenome timeline database.
 
     Provides a high-level API to interact with versioned graph snapshots,
     perform queries, and extract code intelligence metrics.
diff --git a/src/codegenome/installer.py b/src/codegenome/installer.py
index 57466d5..b60f4aa 100644
--- a/src/codegenome/installer.py
+++ b/src/codegenome/installer.py
@@ -1,4 +1,4 @@
-"""Install Watcher MCP server configs for common AI coding clients."""
+"""Install CodeGenome MCP server configs for common AI coding clients."""
 
 from __future__ import annotations
 
@@ -257,10 +257,10 @@ def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
     Returns:
         argparse.Namespace: The parsed command-line arguments.
     """
-    parser = argparse.ArgumentParser(description="Install Watcher MCP configs for AI clients")
+    parser = argparse.ArgumentParser(description="Install CodeGenome MCP configs for AI clients")
     parser.add_argument(
         "--db-path",
-        default=os.getenv("WATCHER_MCP_DB_PATH", "test.db"),
+        default=os.getenv("CODEGENOME_MCP_DB_PATH", "test.db"),
         help="Timeline database path passed to the MCP server",
     )
     parser.add_argument(
@@ -271,18 +271,18 @@ def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
     parser.add_argument(
         "--transport",
         choices=("stdio", "http"),
-        default=os.getenv("WATCHER_MCP_TRANSPORT", "stdio"),
+        default=os.getenv("CODEGENOME_MCP_TRANSPORT", "stdio"),
         help="Transport mode written into client configs",
     )
     parser.add_argument(
         "--host",
-        default=os.getenv("WATCHER_MCP_HOST", "127.0.0.1"),
+        default=os.getenv("CODEGENOME_MCP_HOST", "127.0.0.1"),
         help="Host used for HTTP transport configs",
     )
     parser.add_argument(
         "--port",
         type=int,
-        default=int(os.getenv("WATCHER_MCP_PORT", "7331")),
+        default=int(os.getenv("CODEGENOME_MCP_PORT", "7331")),
         help="Port used for HTTP transport configs",
     )
     parser.add_argument(
diff --git a/src/codegenome/intelligence.py b/src/codegenome/intelligence.py
index 583f45a..f4260bf 100644
--- a/src/codegenome/intelligence.py
+++ b/src/codegenome/intelligence.py
@@ -1,4 +1,4 @@
-"""Architectural intelligence analysis over Watcher dependency graphs.
+"""Architectural intelligence analysis over CodeGenome dependency graphs.
 
 This module provides tools for analyzing a dependency graph and deriving
 actionable architectural signals such as dead code detection, circular
@@ -40,7 +40,7 @@ class IntelligenceReport:
 
 
 class GraphIntelligence:
-    """Derive actionable architectural signals from a Watcher graph.
+    """Derive actionable architectural signals from a CodeGenome graph.
 
     This class provides various methods to analyze the codebase graph
     and detect issues like dead code, god nodes, and circular dependencies.
diff --git a/src/codegenome/live_graph_monitor.py b/src/codegenome/live_graph_monitor.py
index 3dbc851..0e24d4f 100644
--- a/src/codegenome/live_graph_monitor.py
+++ b/src/codegenome/live_graph_monitor.py
@@ -14,7 +14,7 @@ from codegenome.workspace_metrics import (
 )
 
 if TYPE_CHECKING:
-    from codegenome.watcher import WatcherEngine
+    from codegenome.core import CodeGenomeEngine
 
 LOG = logging.getLogger(__name__)
 
@@ -24,13 +24,13 @@ class LiveGraphMonitor:
 
     def __init__(
         self,
-        engine: WatcherEngine,
+        engine: CodeGenomeEngine,
         poll_interval_seconds: float,
     ) -> None:
         """Initialize the LiveGraphMonitor.
 
         Args:
-            engine (WatcherEngine): The engine used for checking and rebuilding the graph.
+            engine (CodeGenomeEngine): The engine used for checking and rebuilding the graph.
             poll_interval_seconds (float): Interval in seconds between polls.
         """
         self._engine = engine
@@ -52,7 +52,7 @@ class LiveGraphMonitor:
         )
         self._thread = threading.Thread(
             target=self._poll_loop,
-            name="watcher-live-graph",
+            name="codegenome-live-graph",
             daemon=True,
         )
         self._thread.start()
diff --git a/src/codegenome/mcp_server.py b/src/codegenome/mcp_server.py
index 5d2dd25..4a96a57 100644
--- a/src/codegenome/mcp_server.py
+++ b/src/codegenome/mcp_server.py
@@ -1,4 +1,4 @@
-"""FastMCP server exposing Watcher graph tools over localhost HTTP or stdio."""
+"""FastMCP server exposing CodeGenome graph tools over localhost HTTP or stdio."""
 
 from __future__ import annotations
 
@@ -31,12 +31,12 @@ DEFAULT_PORT = 7331
 DEFAULT_TIMEOUT_SECONDS = 30.0
 DEFAULT_TRANSPORT: Literal["http", "stdio"] = "http"
 
-ENV_HOST = "WATCHER_MCP_HOST"
-ENV_PORT = "WATCHER_MCP_PORT"
-ENV_DB_PATH = "WATCHER_MCP_DB_PATH"
-ENV_TIMEOUT = "WATCHER_MCP_TIMEOUT"
-ENV_LOG_LEVEL = "WATCHER_MCP_LOG_LEVEL"
-ENV_TRANSPORT = "WATCHER_MCP_TRANSPORT"
+ENV_HOST = "CODEGENOME_MCP_HOST"
+ENV_PORT = "CODEGENOME_MCP_PORT"
+ENV_DB_PATH = "CODEGENOME_MCP_DB_PATH"
+ENV_TIMEOUT = "CODEGENOME_MCP_TIMEOUT"
+ENV_LOG_LEVEL = "CODEGENOME_MCP_LOG_LEVEL"
+ENV_TRANSPORT = "CODEGENOME_MCP_TRANSPORT"
 
 F = TypeVar("F", bound=Callable[..., Any])
 
@@ -204,7 +204,7 @@ class GraphService:
         self.config = config
         self._lock = threading.RLock()
         self._store = GraphStore(config.db_path)
-        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="watcher-mcp")
+        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="codegenome-mcp")
 
     @property
     def store(self) -> GraphStore:
@@ -470,7 +470,7 @@ def create_server(
         summary = service.run(service.store.summary)
         payload = {
             "status": "ok",
-            "service": "watcher-mcp",
+            "service": "codegenome-mcp",
             "version": __version__,
             "db_path": str(service.config.db_path),
             "snapshot_id": summary.snapshot_id,
diff --git a/src/codegenome/parser.py b/src/codegenome/parser.py
index 3ce5646..5053aca 100644
--- a/src/codegenome/parser.py
+++ b/src/codegenome/parser.py
@@ -243,10 +243,10 @@ class SourceParser:
         self._parsers: dict[str, Parser] = {}
         for key, language in self._languages.items():
             try:
-                parser = Parser(language)
-            except TypeError:
                 parser = Parser()
                 parser.set_language(language)
+            except AttributeError:
+                parser = Parser(language)
             self._parsers[key] = parser
 
     def detect_language(self, path: Path | str) -> str | None:
diff --git a/src/codegenome/rules.py b/src/codegenome/rules.py
index 903b4be..f71c852 100644
--- a/src/codegenome/rules.py
+++ b/src/codegenome/rules.py
@@ -1,4 +1,4 @@
-"""Generate Watcher AI agent rules and instructions."""
+"""Generate CodeGenome AI agent rules and instructions."""
 
 from __future__ import annotations
 
@@ -42,7 +42,7 @@ def rule_targets(workspace: Path | None = None) -> list[RuleTarget]:
         RuleTarget(
             key="cursor",
             label="Cursor",
-            output_path=workspace / ".cursor" / "rules" / "watcher-knowledge-graph.mdc",
+            output_path=workspace / ".cursor" / "rules" / "codegenome-knowledge-graph.mdc",
             template_name="cursor-rules.mdc",
         ),
         RuleTarget(
diff --git a/src/codegenome/templates/graph.html.j2 b/src/codegenome/templates/graph.html.j2
index 1624aa1..6dd7c93 100644
--- a/src/codegenome/templates/graph.html.j2
+++ b/src/codegenome/templates/graph.html.j2
@@ -1029,7 +1029,7 @@
     </div>
 
     <script type="text/javascript">
-        // Parse raw payload exported directly from SQLite and Watcher engine
+        // Parse raw payload exported directly from SQLite and CodeGenome engine
         const graphData = {{ graph_json | safe }};
         const config = {{ config_json | safe }};
 
diff --git a/src/codegenome/templates/rules/cursor-rules.mdc b/src/codegenome/templates/rules/cursor-rules.mdc
index 6796262..dab6019 100644
--- a/src/codegenome/templates/rules/cursor-rules.mdc
+++ b/src/codegenome/templates/rules/cursor-rules.mdc
@@ -9,7 +9,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:{{MCP_PORT}}/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/src/codegenome/templates/rules/markdown-instructions.md b/src/codegenome/templates/rules/markdown-instructions.md
index 3666328..a959330 100644
--- a/src/codegenome/templates/rules/markdown-instructions.md
+++ b/src/codegenome/templates/rules/markdown-instructions.md
@@ -4,7 +4,7 @@ You are operating within a repository analyzed by CodeGenome, an architectural k
 
 ## Core Directives
 
-1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
+1. **Mandatory MCP Usage**: When `.genome/codegenome.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
 2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:{{MCP_PORT}}/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
 3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
 4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
diff --git a/src/codegenome/timeline.py b/src/codegenome/timeline.py
index ed90f87..ca40d2c 100644
--- a/src/codegenome/timeline.py
+++ b/src/codegenome/timeline.py
@@ -1,4 +1,4 @@
-"""SQLite-backed graph snapshot and delta timeline for Watcher.
+"""SQLite-backed graph snapshot and delta timeline for CodeGenome.
 
 This module provides the GraphTimeline class, which records full dependency
 graphs into a SQLite database, allowing for historical analysis and
diff --git a/test2.py b/test2.py
new file mode 100644
index 0000000..fd1124c
--- /dev/null
+++ b/test2.py
@@ -0,0 +1,13 @@
+import tree_sitter
+import tree_sitter_python
+lang = tree_sitter.Language(tree_sitter_python.language(), 'python')
+
+try:
+    p = tree_sitter.Parser()
+    p.set_language(lang)
+    print("set_language successful")
+except AttributeError:
+    print("falling back to Parser(lang)")
+    p = tree_sitter.Parser(lang)
+
+print(p.parse(b'def foo(): pass'))
diff --git a/tests/test_mcp_server.py b/tests/test_mcp_server.py
index ff48133..8d9126f 100644
--- a/tests/test_mcp_server.py
+++ b/tests/test_mcp_server.py
@@ -1,4 +1,4 @@
-"""Tests for Watcher MCP server and graph store."""
+"""Tests for CodeGenome MCP server and graph store."""
 
 from __future__ import annotations
 

```
