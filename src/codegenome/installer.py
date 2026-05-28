"""Install Watcher MCP server configs for common AI coding clients."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SERVER_NAME = "watcher"

TransportMode = Literal["stdio", "http"]


@dataclass(frozen=True)
class ClientTarget:
    key: str
    label: str
    config_path: Path
    root_key: str


def default_python_executable() -> str:
    return sys.executable


def resolve_db_path(raw: str) -> str:
    return str(Path(raw).expanduser().resolve())


def build_server_entry(
    *,
    python_executable: str,
    db_path: str,
    transport: TransportMode,
    host: str,
    port: int,
) -> dict[str, Any]:
    if transport == "http":
        return {"url": f"http://{host}:{port}/mcp"}

    return {
        "command": python_executable,
        "args": [
            "-m",
            "codegenome.mcp_server",
            "--db-path",
            db_path,
            "--transport",
            "stdio",
        ],
    }


def client_targets(home: Path | None = None) -> list[ClientTarget]:
    home = home or Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))

    return [
        ClientTarget(
            key="claude",
            label="Claude Desktop",
            config_path=_first_existing_path(
                [
                    appdata / "Claude" / "claude_desktop_config.json",
                    home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
                    home / ".config" / "claude-desktop" / "claude_desktop_config.json",
                ]
            ),
            root_key="mcpServers",
        ),
        ClientTarget(
            key="cursor",
            label="Cursor",
            config_path=home / ".cursor" / "mcp.json",
            root_key="mcpServers",
        ),
        ClientTarget(
            key="codex",
            label="Codex",
            config_path=home / ".codex" / "mcp.json",
            root_key="mcpServers",
        ),
        ClientTarget(
            key="gemini",
            label="Gemini",
            config_path=home / ".gemini" / "mcp.json",
            root_key="mcpServers",
        ),
        ClientTarget(
            key="aider",
            label="Aider",
            config_path=home / ".aider" / "mcp.json",
            root_key="mcpServers",
        ),
        ClientTarget(
            key="windsurf",
            label="Windsurf",
            config_path=home / ".codeium" / "windsurf" / "mcp_config.json",
            root_key="mcpServers",
        ),
        ClientTarget(
            key="copilot",
            label="GitHub Copilot (VS Code)",
            config_path=Path.cwd() / ".vscode" / "mcp.json",
            root_key="servers",
        ),
    ]


def _first_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.parent.exists():
            return candidate
    return candidates[0]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return {}
    return json.loads(content)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def merge_server_config(
    existing: dict[str, Any],
    *,
    root_key: str,
    server_name: str,
    server_entry: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing)
    servers = dict(merged.get(root_key, {}))
    servers[server_name] = server_entry
    merged[root_key] = servers
    return merged


def install_client(
    target: ClientTarget,
    *,
    server_entry: dict[str, Any],
    dry_run: bool = False,
) -> Path:
    existing = load_json(target.config_path)
    merged = merge_server_config(
        existing,
        root_key=target.root_key,
        server_name=SERVER_NAME,
        server_entry=server_entry,
    )
    if not dry_run:
        write_json(target.config_path, merged)
    return target.config_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Watcher MCP configs for AI clients")
    parser.add_argument(
        "--db-path",
        default=os.getenv("WATCHER_MCP_DB_PATH", "test.db"),
        help="Timeline database path passed to the MCP server",
    )
    parser.add_argument(
        "--python",
        default=default_python_executable(),
        help="Python executable used for stdio transport",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=os.getenv("WATCHER_MCP_TRANSPORT", "stdio"),
        help="Transport mode written into client configs",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("WATCHER_MCP_HOST", "127.0.0.1"),
        help="Host used for HTTP transport configs",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("WATCHER_MCP_PORT", "7331")),
        help="Port used for HTTP transport configs",
    )
    parser.add_argument(
        "--client",
        action="append",
        choices=[target.key for target in client_targets()],
        help="Install only selected clients (repeatable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print target paths without writing files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = resolve_db_path(args.db_path)
    server_entry = build_server_entry(
        python_executable=args.python,
        db_path=db_path,
        transport=args.transport,
        host=args.host,
        port=args.port,
    )

    selected = set(args.client) if args.client else None
    installed: list[tuple[str, Path]] = []

    for target in client_targets():
        if selected is not None and target.key not in selected:
            continue
        path = install_client(target, server_entry=server_entry, dry_run=args.dry_run)
        installed.append((target.label, path))

    if not installed:
        print("No clients selected.", file=sys.stderr)
        return 1

    action = "Would install" if args.dry_run else "Installed"
    for label, path in installed:
        print(f"{action} {label}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
