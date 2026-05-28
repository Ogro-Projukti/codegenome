# Watcher knowledge graph (MCP)

This project has a Watcher knowledge graph at `.watcher/`.

For codebase, architecture, dependency, or symbol questions:

1. When `.watcher/watcher.db` exists and MCP is healthy, **use the Watcher MCP server** first (`watcher` on `http://127.0.0.1:{{MCP_PORT}}/mcp`).
2. Prefer MCP tools over raw grep or reading entire files:
   - `search_nodes`, `get_neighbors`, `get_entry_points`, `get_dead_code`
   - `get_circular_deps`, `get_god_nodes`, `get_complexity`, `get_churn`
   - `get_graph`, `get_timeline`, `get_changes`
3. If MCP returns empty data, run **Watcher: Build Graph** before falling back to file search.
4. After code changes, keep the graph current via **Watcher: Build Graph** or watch mode.
