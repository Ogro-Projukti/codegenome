"""Command-line interface for codegenome."""

import sys
from pathlib import Path
import click

from codegenome.watcher import WatcherEngine, WatcherConfig

@click.group()
def cli():
    """codegenome - Open-source CLI for building and querying local codebase knowledge graphs."""
    pass

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def analyze(path: str):
    """Triggers the tree-sitter scan, builds the ASTs, and saves to the SQLite graph_store."""
    click.echo(f"Analyzing workspace at {path}...")
    workspace = Path(path).resolve()
    config = WatcherConfig(workspace=workspace, export_formats=("json",))
    engine = WatcherEngine(config)
    
    try:
        result = engine.build(full=False)
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
    """Triggers the exporter pipeline to dump the current graph store into the requested format."""
    workspace = Path(path).resolve()
    config = WatcherConfig(workspace=workspace)
    engine = WatcherEngine(config)
    
    try:
        # Check if the graph exists. If not loaded, it means it hasn't been analyzed.
        # engine._load_existing_graph() is called in WatcherEngine.__init__.
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
def mcp_start(path: str):
    """Initializes and starts the MCP server so external LLMs can connect."""
    workspace = Path(path).resolve()
    config = WatcherConfig(workspace=workspace)
    engine = WatcherEngine(config)
    db_path = engine.db_path
    engine.close()  # Close the engine since the MCP server process will open its own connection
    
    click.echo(f"Starting MCP server for workspace {workspace} (DB: {db_path})...")
    
    from codegenome.mcp_server import main as mcp_main
    sys.exit(mcp_main(["--db-path", str(db_path), "--transport", "stdio"]))

if __name__ == "__main__":
    cli()
