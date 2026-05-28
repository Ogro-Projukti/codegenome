"""Generate Watcher AI agent rules and instructions."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files  # type: ignore


@dataclass(frozen=True)
class RuleTarget:
    key: str
    label: str
    output_path: Path
    template_name: str


def rule_targets(workspace: Path | None = None) -> list[RuleTarget]:
    workspace = workspace or Path.cwd()

    return [
        RuleTarget(
            key="cursor",
            label="Cursor",
            output_path=workspace / ".cursor" / "rules" / "watcher-knowledge-graph.mdc",
            template_name="cursor-rules.mdc",
        ),
        RuleTarget(
            key="copilot",
            label="GitHub Copilot",
            output_path=workspace / ".github" / "copilot-instructions.md",
            template_name="markdown-instructions.md",
        ),
        RuleTarget(
            key="windsurf",
            label="Windsurf",
            output_path=workspace / ".windsurfrules",
            template_name="markdown-instructions.md",
        ),
        RuleTarget(
            key="agents",
            label="AGENTS.md",
            output_path=workspace / "AGENTS.md",
            template_name="markdown-instructions.md",
        ),
    ]


def load_template(template_name: str) -> str:
    """Load a rule template from the package resources."""
    template_path = files("codegenome.templates.rules").joinpath(template_name)
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_name}")
    return template_path.read_text(encoding="utf-8")


def write_rule(path: Path, content: str) -> None:
    """Write rule content to the given path, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate_rules_for_target(
    target: RuleTarget,
    port: int,
    dry_run: bool = False,
) -> Path:
    """Generate and write rules for a specific target."""
    template_content = load_template(target.template_name)
    
    # Substitute placeholders
    rule_content = template_content.replace("{{MCP_PORT}}", str(port))
    
    if not dry_run:
        write_rule(target.output_path, rule_content)
        
    return target.output_path


def generate_rules(
    selected_clients: list[str] | None = None,
    port: int = 7331,
    workspace: Path | None = None,
    dry_run: bool = False,
) -> list[tuple[str, Path]]:
    """Generate rules for the selected clients. 
    If 'all' is in selected_clients, generates for all supported clients.
    """
    targets = rule_targets(workspace)
    
    if selected_clients and "all" in selected_clients:
        selected_clients = None  # means all
    elif selected_clients:
        selected_clients = set(selected_clients)
        
    generated = []
    
    for target in targets:
        if selected_clients is not None and target.key not in selected_clients:
            continue
            
        path = generate_rules_for_target(target, port, dry_run)
        generated.append((target.label, path))
        
    return generated
