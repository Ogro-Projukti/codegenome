"""Command-line interface for codegenome."""

import sys
from pathlib import Path
import click

from codegenome.core import CodeGenomeEngine, CodeGenomeConfig

@click.group()
def cli():
    """codegenome - Open-source CLI for building and querying local codebase knowledge graphs."""
    pass

@cli.command()
@click.option(
    "--memory-bounded",
    is_flag=True,
    help="Keep only a bounded file working set in memory after the initial build.",
)
@click.option(
    "--max-working-files",
    default=64,
    show_default=True,
    type=int,
    help="Maximum files resident in memory when --memory-bounded is enabled.",
)
@click.option(
    "--retain-snapshots",
    default=100,
    show_default=True,
    type=click.IntRange(min=1),
    help="Automatically retain only the newest snapshot count after analysis.",
)
@click.option(
    "--retention-days",
    default=None,
    type=click.FloatRange(min=0.0),
    help="Also remove snapshots older than this many days.",
)
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def analyze(
    path: str,
    memory_bounded: bool,
    max_working_files: int,
    retain_snapshots: int,
    retention_days: float | None,
):
    """Triggers the tree-sitter scan, builds the ASTs, and saves to the SQLite graph_store.

    Args:
        path (str): The workspace directory path to analyze.
    """
    click.echo(f"Analyzing workspace at {path}...")
    workspace = Path(path).resolve()
    config = CodeGenomeConfig(
        workspace=workspace,
        export_formats=("json",),
        memory_bounded=memory_bounded,
        max_working_files=max(1, max_working_files),
        snapshot_retention_count=retain_snapshots,
        snapshot_retention_days=retention_days,
    )
    engine = CodeGenomeEngine(config)

    def on_progress(message: str) -> None:
        click.echo(message)
    
    try:
        result = engine.build(full=False, on_progress=on_progress)
        click.echo(f"Build complete: {result.graph.number_of_nodes()} nodes, {result.graph.number_of_edges()} edges.")
    except Exception as e:
        click.echo(f"Error during analysis: {e}", err=True)
        sys.exit(1)
    finally:
        engine.close()


@cli.command()
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["obsidian", "html", "cypher", "json"], case_sensitive=False),
    required=True,
    help="Format to export the graph store into."
)
@click.option(
    "--path",
    default=".",
    type=click.Path(exists=True, file_okay=False),
    help="Workspace path to export from."
)
def export(export_format: str, path: str):
    """Triggers the exporter pipeline to dump the current graph store into the requested format.

    Args:
        export_format (str): Format to export the graph store into (e.g. obsidian, html).
        path (str): The workspace directory path to export from.
    """
    workspace = Path(path).resolve()
    config = CodeGenomeConfig(workspace=workspace)
    engine = CodeGenomeEngine(config)
    
    try:
        # Check if the graph exists. If not loaded, it means it hasn't been analyzed.
        # engine._load_existing_graph() is called in CodeGenomeEngine.__init__.
        # Alternatively, we can check if the graph has nodes.
        if engine.builder.graph.number_of_nodes() == 0:
            click.echo("Error: No graph found. Please run 'codegenome analyze' first before exporting.", err=True)
            sys.exit(1)
            
        click.echo(f"Exporting workspace {workspace} to {export_format}...")
        result_paths = engine.export(formats=[export_format.lower()])
        for fmt, out_path in result_paths.items():
            click.echo(f"Successfully exported {fmt} to: {out_path}")
            
    except RuntimeError as e:
        click.echo(f"Export error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error during export: {e}", err=True)
        sys.exit(1)
    finally:
        engine.close()


@cli.command(name="mcp-start")
@click.option(
    "--path",
    default=".",
    type=click.Path(exists=True, file_okay=False),
    help="Workspace path for the MCP server."
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"], case_sensitive=False),
    default="stdio",
    help="Transport protocol (stdio or http)."
)
@click.option(
    "--port",
    type=int,
    default=7331,
    help="Port to bind to when using HTTP transport."
)
@click.option(
    "--lan",
    is_flag=True,
    help="Allow HTTP transport to bind on LAN (0.0.0.0) instead of localhost.",
)
@click.option(
    "--memory-bounded",
    is_flag=True,
    help="Load MCP query subgraphs on demand instead of the full graph.",
)
@click.option(
    "--full-analysis-on-demand",
    is_flag=True,
    help="Allow global MCP analysis tools to temporarily load the full graph.",
)
def mcp_start(path: str, transport: str, port: int, lan: bool, memory_bounded: bool, full_analysis_on_demand: bool):
    """Initializes and starts the MCP server so external LLMs can connect.

    Args:
        path (str): The workspace directory path for the MCP server.
        transport (str): Transport protocol (stdio or http).
        port (int): Port to bind to when using HTTP transport.
        lan (bool): Whether to expose HTTP transport on the local network.
    """
    workspace = Path(path).resolve()
    config = CodeGenomeConfig(workspace=workspace)
    engine = CodeGenomeEngine(config)
    db_path = engine.db_path
    engine.close()  # Close the engine since the MCP server process will open its own connection
    
    click.echo(f"Starting MCP server for workspace {workspace} (DB: {db_path}) via {transport}...", err=True)
    
    from codegenome.mcp_server import main as mcp_main
    args = ["--db-path", str(db_path), "--transport", transport.lower()]
    if memory_bounded:
        args.append("--memory-bounded")
    if full_analysis_on_demand:
        args.append("--full-analysis-on-demand")
    if transport.lower() == "http":
        host = "0.0.0.0" if lan else "127.0.0.1"
        args.extend(["--host", host])
        args.extend(["--port", str(port)])
        if lan:
            args.append("--allow-remote-http")
    sys.exit(mcp_main(args))

@cli.command()
@click.option("--live", is_flag=True, help="Enable WebSocket real-time broadcast.")
@click.option(
    "--lan",
    is_flag=True,
    help="Expose HTTP and WebSocket on the local network (0.0.0.0).",
)
@click.option(
    "--memory-bounded",
    is_flag=True,
    help="Keep only a bounded file working set in memory after the initial build.",
)
@click.option(
    "--max-working-files",
    default=64,
    show_default=True,
    type=int,
    help="Maximum files resident in memory when --memory-bounded is enabled.",
)
@click.option(
    "--retain-snapshots",
    default=100,
    show_default=True,
    type=click.IntRange(min=1),
    help="Automatically retain only the newest snapshot count while evolving.",
)
@click.option(
    "--retention-days",
    default=None,
    type=click.FloatRange(min=0.0),
    help="Also remove snapshots older than this many days.",
)
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def evolve(
    path: str,
    live: bool,
    lan: bool,
    memory_bounded: bool,
    max_working_files: int,
    retain_snapshots: int,
    retention_days: float | None,
):
    """Start real-time architectural observer and open live UI.

    Args:
        path (str): The workspace directory path to observe.
        live (bool): Whether to enable WebSocket real-time broadcast.
        lan (bool): Whether to bind services for LAN access.
    """
    from codegenome.live_session import LiveSession, LiveSessionConfig

    session = LiveSession(
        LiveSessionConfig(
            workspace=Path(path).resolve(),
            live=live,
            lan=lan,
            memory_bounded=memory_bounded,
            max_working_files=max(1, max_working_files),
            snapshot_retention_count=retain_snapshots,
            snapshot_retention_days=retention_days,
        ),
        emit=click.echo,
    )
    session.serve()


@cli.command(name="db-maintain")
@click.option(
    "--path",
    default=".",
    type=click.Path(exists=True, file_okay=False),
    help="Workspace whose .genome/codegenome.db should be maintained.",
)
@click.option(
    "--retain-snapshots",
    default=100,
    show_default=True,
    type=click.IntRange(min=1),
    help="Retain at most this many newest snapshots.",
)
@click.option(
    "--max-age-days",
    default=None,
    type=click.FloatRange(min=0.0),
    help="Also remove snapshots older than this many days.",
)
@click.option(
    "--compact/--no-compact",
    default=False,
    show_default=True,
    help="VACUUM the database after pruning to return free pages to disk.",
)
def db_maintain(
    path: str,
    retain_snapshots: int,
    max_age_days: float | None,
    compact: bool,
) -> None:
    """Prune snapshot history transactionally and optionally compact SQLite."""
    from codegenome.timeline import GraphTimeline

    db_path = Path(path).resolve() / ".genome" / "codegenome.db"
    if not db_path.exists():
        raise click.ClickException(f"No CodeGenome database found at {db_path}")
    timeline = GraphTimeline(db_path)
    try:
        result = timeline.prune_snapshots(
            max_snapshots=retain_snapshots,
            max_age_seconds=(
                max_age_days * 24 * 60 * 60 if max_age_days is not None else None
            ),
            compact=compact,
        )
    finally:
        timeline.close()
    reclaimed = result.database_bytes_before - result.database_bytes_after
    click.echo(
        f"Snapshots: {result.snapshots_before} -> {result.snapshots_after}; "
        f"deleted {len(result.deleted_snapshot_ids)}; "
        f"disk reclaimed {max(0, reclaimed):,} bytes."
    )


@cli.command()
@click.option(
    "--client",
    multiple=True,
    type=click.Choice(["cursor", "copilot", "windsurf", "agents", "all"], case_sensitive=False),
    help="Target AI client to generate rules for (repeatable). Use 'all' for all clients."
)
@click.option(
    "--port",
    type=int,
    default=7331,
    help="MCP server port to embed in the generated rules."
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print target paths without writing files."
)
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def rules(client: tuple[str], port: int, dry_run: bool, path: str):
    """Generate agent rules (e.g. .cursorrules, AGENTS.md) pointing to the MCP server.

    Args:
        client (tuple[str]): Target AI client(s) to generate rules for.
        port (int): MCP server port to embed in the generated rules.
        dry_run (bool): If True, print target paths without writing files.
        path (str): The workspace directory path.
    """
    from codegenome.rules import generate_rules
    
    workspace = Path(path).resolve()
    
    # default to all if no clients provided
    selected = list(client) if client else ["all"]
    
    click.echo(f"Generating rules for workspace {workspace} (MCP Port: {port})...")
    
    try:
        results = generate_rules(
            selected_clients=selected,
            port=port,
            workspace=workspace,
            dry_run=dry_run
        )
        
        if not results:
            click.echo("No clients selected or found.")
            return

        action = "Would generate" if dry_run else "Generated"
        for label, out_path in results:
            # try to make path relative to workspace for cleaner output
            try:
                rel_path = out_path.relative_to(workspace)
                click.echo(f"{action} {label} rules at: {rel_path}")
            except ValueError:
                click.echo(f"{action} {label} rules at: {out_path}")
                
    except Exception as e:
        click.echo(f"Error generating rules: {e}", err=True)
        sys.exit(1)


@cli.command()
def tui():
    """Launch the interactive Textual TUI dashboard."""
    from codegenome.tui import main as tui_main
    tui_main()

if __name__ == "__main__":
    cli()
