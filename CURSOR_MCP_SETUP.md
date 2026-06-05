# CodeGenome Cursor MCP Setup

This project uses **CodeGenome** to provide an architectural knowledge graph that helps Cursor understand the codebase deeply.

## Prerequisites

1. Ensure `codegenome` is installed in your environment:
   ```bash
   pip install codegenome
   ```
2. You must generate the initial knowledge graph so that the `codegenome.db` exists. Run:
   ```bash
   codegenome analyze
   ```
   *Note: This repository is already configured to ignore `.genome/codegenome.db` in `.gitignore`.*

## Cursor MCP Integration

Cursor automatically reads the `.cursor/mcp.json` file in this repository. The configuration points to the `codegenome mcp-start` command. 

Once Cursor connects to the MCP server, it will generate the necessary tool configurations under `.cursor/mcps/` automatically at runtime.

### Troubleshooting

- **Server Not Starting?** If Cursor cannot find the `codegenome` command, you may need to update the `command` field in `.cursor/mcp.json` to point to the absolute path of your `codegenome` executable (e.g., inside your virtual environment, like `.venv/bin/codegenome` or `.venv/Scripts/codegenome.exe`), or run Cursor from an activated terminal.
- **Tools Missing?** Ensure that `.genome/codegenome.db` has been created by running `codegenome analyze`.

## Continuous Updates

To keep the CodeGenome knowledge graph updated automatically as you edit files, run the live codegenome in the background:
```bash
codegenome evolve --live
```
