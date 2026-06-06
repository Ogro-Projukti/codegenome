# MCP Persistent Usage and Token Savings

This document describes the updated MCP activity accounting model: CodeGenome now keeps both per-server-session counters and persisted workspace-level counters for monthly and lifetime token savings.

---

## Problem

The original MCP activity tracker was process-local. That made the TUI useful for a single running HTTP MCP server, but it had two gaps:

1. Restarting the MCP server reset the visible call and token-savings counters.
2. Calls made through another MCP transport or client could be missing from the HTTP server's in-memory session counter.

The new behavior keeps the fast in-memory session counters, but also writes every MCP tool-call event to the workspace SQLite database.

---

## Storage

MCP usage events are persisted in the workspace DB:

```text
.genome/codegenome.db
└── mcp_activity_events
```

Each row stores:

| Field | Meaning |
|-------|---------|
| `timestamp` | Unix timestamp for the call |
| `tool` | MCP tool name, such as `search_nodes` or `get_graph` |
| `client` | Client identity, such as `mcp`, `cursor-vscode`, or `stdio` |
| `args_json` | Summarized JSON arguments |
| `status` | `ok` or `error` |
| `duration_ms` | Tool execution time |
| `response_tokens` | Estimated response payload tokens |
| `tokens_saved` | Estimated tokens avoided versus file reads |
| `error` | Error text for failed calls |

The table is created automatically on MCP server startup.

---

## Counters

`/health` and `/mcp/activity` now expose combined activity stats with three scopes:

```json
{
  "mcp_activity": {
    "total_calls": 42,
    "total_tokens_saved": 120000,
    "session": {
      "total_calls": 4,
      "total_tokens_saved": 9000
    },
    "month": {
      "total_calls": 18,
      "total_tokens_saved": 48000
    },
    "lifetime": {
      "total_calls": 42,
      "total_tokens_saved": 120000
    },
    "persistent": true
  }
}
```

The top-level fields mirror `lifetime` so existing clients that read `total_calls` and `total_tokens_saved` automatically show the combined persisted totals.

### Session

`session` is the current MCP server process only. It resets when that process restarts.

### Month

`month` is all persisted MCP activity since the first day of the current UTC month.

### Lifetime

`lifetime` is all persisted MCP activity stored in the workspace DB.

---

## TUI Display

The TUI stats bar displays:

```text
MCP calls: 42 | Saved: session 9,000 | month 48,000 | lifetime 120,000
```

The bar polls:

```text
GET /mcp/activity?limit=1
```

It falls back to `/health` if the activity endpoint is unavailable.

The TUI also triggers an immediate refresh when the MCP log emits a structured `tool_call` event.

---

## Multi-Client Behavior

Calls from different clients combine if they write to the same workspace database.

Examples:

| Client path | Recorded in session? | Recorded in month/lifetime? |
|-------------|----------------------|------------------------------|
| Direct HTTP call to `127.0.0.1:7331/mcp` | Yes, for that HTTP server | Yes |
| Cursor MCP server using the same `.genome/codegenome.db` | Only in its own process | Yes |
| Fresh MCP server after restart | New session starts at zero | Existing lifetime/month totals remain |

This is why direct HTTP calls and Cursor MCP calls can both appear in the combined lifetime totals, while only direct calls to the visible HTTP process appear in that server's `session` counter.

---

## Manual Verification

Start MCP:

```bash
codegenome mcp-start --path D:\GITHUB\OP\codegenome --transport http --port 7331
```

Read activity:

```bash
curl "http://127.0.0.1:7331/mcp/activity?limit=1"
```

Expected shape:

```json
{
  "status": "ok",
  "stats": {
    "session": { "...": "..." },
    "month": { "...": "..." },
    "lifetime": { "...": "..." },
    "persistent": true
  },
  "events": []
}
```

Call a tool through HTTP MCP, then read activity again. `session`, `month`, and `lifetime` should increment.

Call a tool through Cursor's configured MCP server. If it points at the same workspace DB, `month` and `lifetime` should increment. The HTTP server's `session` counter will not increment unless the call went through that exact HTTP server process.

---

## Tests

Focused coverage:

```bash
python -m pytest tests/test_mcp_activity.py tests/test_mcp_server.py tests/test_tui_mcp_stats.py -q
```

Covered behavior:

- Events persist to SQLite.
- Lifetime/month counters survive a new tracker instance.
- `/health` and `/mcp/activity` expose combined stats.
- TUI formatting supports session/month/lifetime stats and legacy flat stats.
