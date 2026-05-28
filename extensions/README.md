# Extensions & editor integrations

This folder holds **editor and agent integration assets** that ship with the open-source CLI repo. They are copied from the Watcher monorepo and will grow here as CLI-side installers expand.

## Contents

| Path | Purpose |
|------|---------|
| `templates/watcher-knowledge-graph.mdc` | Cursor rule template — teaches agents to use Watcher MCP tools |
| `templates/copilot-instructions.md` | GitHub Copilot instructions template |

Templates use `{{MCP_PORT}}` as a placeholder (default MCP port: `7331`).

## MCP client installer (CLI)

The Python package includes a config writer for AI clients:

```bash
python -m codegenome.installer \
  --db-path /absolute/path/to/project/.watcher/watcher.db \
  --client cursor \
  --transport http \
  --host 127.0.0.1 \
  --port 7331
```

Supported clients: `claude`, `cursor`, `codex`, `gemini`, `aider`, `windsurf`, `copilot`.

## Planned moves from the monorepo

- Cursor rule / Copilot template install command on the main `watcher` CLI (today: VS Code extension only)
- Additional agent rule formats (AGENTS.md, Windsurf rules, etc.)
- VS Code extension remains a separate package; only shared templates and installer logic live here

## Manual install (Cursor rule)

```bash
mkdir -p .cursor/rules
sed 's/{{MCP_PORT}}/7331/g' extensions/templates/watcher-knowledge-graph.mdc \
  > .cursor/rules/watcher-knowledge-graph.mdc
```

Restart Cursor after installing MCP config or rules.
