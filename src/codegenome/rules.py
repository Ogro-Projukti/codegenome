"""Generate CodeGenome AI agent rules and instructions."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files  # type: ignore


MANAGED_SECTION_START = "<!-- BEGIN CODEGENOME MANAGED RULES -->"
MANAGED_SECTION_END = "<!-- END CODEGENOME MANAGED RULES -->"


class RuleMergeError(ValueError):
    """Raised when an existing managed section cannot be updated safely."""


@dataclass(frozen=True)
class RuleTarget:
    """Target configuration for generating AI rules.
    
    Attributes:
        key (str): The internal identifier for the rule target.
        label (str): The human-readable name of the target.
        output_path (Path): The path where the rule file will be written.
        template_name (str): The name of the template file to use.
    """
    key: str
    label: str
    output_path: Path
    template_name: str


def rule_targets(workspace: Path | None = None) -> list[RuleTarget]:
    """Get the supported rule generation targets.

    Args:
        workspace (Path | None, optional): The workspace directory. Defaults to the current working directory.

    Returns:
        list[RuleTarget]: A list of rule target configurations.
    """
    workspace = workspace or Path.cwd()

    return [
        RuleTarget(
            key="cursor",
            label="Cursor",
            output_path=workspace / ".cursor" / "rules" / "codegenome-knowledge-graph.mdc",
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
    """Load a rule template from the package resources.

    Args:
        template_name (str): The filename of the template to load.

    Returns:
        str: The content of the loaded template.

    Raises:
        FileNotFoundError: If the specified template cannot be found.
    """
    template_path = files("codegenome.templates.rules").joinpath(template_name)
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_name}")
    return template_path.read_text(encoding="utf-8")


def write_rule(path: Path, content: str) -> None:
    """Merge generated rules into a managed section and write atomically.

    Args:
        path (Path): The destination file path.
        content (str): The text content to write.

    Raises:
        RuleMergeError: If existing managed markers are incomplete or ambiguous.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    updated = _render_rule(existing, content)
    if existing == updated:
        return

    if existing is not None:
        _atomic_write(backup_path_for(path), existing)
    _atomic_write(path, updated)


def backup_path_for(path: Path) -> Path:
    """Return the single-file recovery backup used before managed updates."""
    return path.with_name(f"{path.name}.codegenome.bak")


def _render_rule(existing: str | None, content: str) -> str:
    prefix, managed_content = _split_front_matter(content)
    managed_block = (
        f"{MANAGED_SECTION_START}\n"
        f"{managed_content.strip()}\n"
        f"{MANAGED_SECTION_END}"
    )

    if existing is None or existing.rstrip() == content.rstrip():
        prefix_block = f"{prefix.rstrip()}\n\n" if prefix else ""
        return f"{prefix_block}{managed_block}\n"

    start_count = existing.count(MANAGED_SECTION_START)
    end_count = existing.count(MANAGED_SECTION_END)
    if start_count == 0 and end_count == 0:
        separator = "\n\n" if existing.strip() else ""
        return f"{existing.rstrip()}{separator}{managed_block}\n"
    if start_count != 1 or end_count != 1:
        raise RuleMergeError(
            f"Refusing to update {start_count} start marker(s) and "
            f"{end_count} end marker(s); repair the managed section first."
        )

    start = existing.index(MANAGED_SECTION_START)
    end = existing.index(MANAGED_SECTION_END)
    if end < start:
        raise RuleMergeError("Managed section end marker appears before its start marker.")
    end += len(MANAGED_SECTION_END)
    return f"{existing[:start]}{managed_block}{existing[end:]}"


def _split_front_matter(content: str) -> tuple[str, str]:
    """Keep MDC front matter valid while managing its Markdown body."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", content
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[: index + 1]), "".join(lines[index + 1 :])
    return "", content


def _atomic_write(path: Path, content: str) -> None:
    """Replace a text file from a same-directory temporary file."""
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            shutil.copymode(path, temporary_path)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def generate_rules_for_target(
    target: RuleTarget,
    port: int,
    dry_run: bool = False,
) -> Path:
    """Generate and write rules for a specific target.

    Args:
        target (RuleTarget): The target configuration to generate rules for.
        port (int): The MCP server port to interpolate into the template.
        dry_run (bool, optional): If True, do not actually write the file. Defaults to False.

    Returns:
        Path: The path where the rule was (or would be) written.
    """
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

    Args:
        selected_clients (list[str] | None, optional): List of client keys to generate rules for. Defaults to None.
        port (int, optional): The MCP server port. Defaults to 7331.
        workspace (Path | None, optional): The workspace directory. Defaults to None.
        dry_run (bool, optional): If True, do not actually write the files. Defaults to False.

    Returns:
        list[tuple[str, Path]]: A list of tuples containing the target label and output path.
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
