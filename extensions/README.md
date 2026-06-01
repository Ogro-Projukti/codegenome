# Extensions and editor integrations

This folder holds **editor and agent integration assets** that ship with the Codegenome repository.

## Contents

| Path | Purpose |
|------|---------|
| `templates/watcher-knowledge-graph.mdc` | Cursor rule template — teaches agents to use Codegenome MCP tools |
| `templates/copilot-instructions.md` | GitHub Copilot instructions template |
| `templates/claude-instructions.md` | Claude-oriented instructions template |

Templates use `{{MCP_PORT}}` as a placeholder (default MCP port: `7331`).

## Generate rules with the CLI

Prefer the built-in generator over manual copying:

```bash
codegenome rules --client cursor --port 7331 .
codegenome rules --client copilot --port 7331 .
codegenome rules --client all --port 7331 .
```

Supported `--client` values: `cursor`, `copilot`, `windsurf`, `agents`, `all`.

Use `--dry-run` to preview output paths without writing files.

## MCP client installer

Write MCP server entries into AI client config files:

```bash
python -m codegenome.installer \
  --db-path /absolute/path/to/project/.genome/watcher.db \
  --client cursor \
  --transport http \
  --host 127.0.0.1 \
  --port 7331
```

Supported installer clients: `claude`, `cursor`, `codex`, `gemini`, `aider`, `windsurf`, `copilot`.

See [MCP integration](../docs/mcp-integration.md) for transport modes, health checks, and troubleshooting.

## Manual install (Cursor rule)

```bash
mkdir -p .cursor/rules
sed 's/{{MCP_PORT}}/7331/g' extensions/templates/watcher-knowledge-graph.mdc \
  > .cursor/rules/watcher-knowledge-graph.mdc
```

Restart Cursor after installing MCP config or rules.

## Related documentation

| Doc | Description |
|-----|-------------|
| [MCP integration](../docs/mcp-integration.md) | Server setup and installer |
| [CLI reference](../docs/cli-reference.md) | `codegenome rules` and other commands |
| [Installation](../docs/installation.md) | pip install and first graph build |
