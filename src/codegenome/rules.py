"""Generate CodeGenome AI agent rules and instructions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files  # type: ignore


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
    """Write rule content to the given path, creating parent directories if needed.
    
    If the file already exists, appends the content with section markers to preserve
    existing user content. If a CodeGenome section already exists, it will be replaced.

    Args:
        path (Path): The destination file path.
        content (str): The text content to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Section markers to identify CodeGenome-managed content
    BEGIN_MARKER = "<!-- BEGIN CODEGENOME MCP INTEGRATION -->"
    END_MARKER = "<!-- END CODEGENOME MCP INTEGRATION -->"
    
    # Wrap content with markers
    wrapped_content = f"{BEGIN_MARKER}\n{content}\n{END_MARKER}\n"
    
    if not path.exists():
        # File doesn't exist - create it with wrapped content
        path.write_text(wrapped_content, encoding="utf-8")
        return
    
    # File exists - read current content
    try:
        existing_content = path.read_text(encoding="utf-8")
    except Exception:
        # If we can't read it, backup and overwrite
        backup_path = path.with_suffix(path.suffix + ".backup")
        path.rename(backup_path)
        path.write_text(wrapped_content, encoding="utf-8")
        return
    
    # Check if CodeGenome section already exists
    if BEGIN_MARKER in existing_content and END_MARKER in existing_content:
        # Replace existing section
        start_idx = existing_content.find(BEGIN_MARKER)
        end_idx = existing_content.find(END_MARKER) + len(END_MARKER)
        
        # Preserve content before and after the section
        before = existing_content[:start_idx]
        after = existing_content[end_idx:]
        
        new_content = before + wrapped_content + after
        path.write_text(new_content, encoding="utf-8")
    else:
        # No existing section - append with separator
        separator = "\n\n" if existing_content.strip() else ""
        new_content = existing_content + separator + wrapped_content
        path.write_text(new_content, encoding="utf-8")


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
