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

@cli.command()
@click.option("--live", is_flag=True, help="Enable WebSocket real-time broadcast.")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def evolve(path: str, live: bool):
    """Start real-time architectural observer and open live UI."""
    import time
    import threading
    import webbrowser
    from http.server import SimpleHTTPRequestHandler
    from socketserver import TCPServer
    from watchdog.observers import Observer
    from codegenome.watcher import WatcherConfig, WatcherEngine, SurgicalUpdateHandler

    workspace = Path(path).resolve()
    config = WatcherConfig(workspace=workspace, export_formats=("json", "html"))
    engine = WatcherEngine(config)
    
    click.echo(f"Running initial build for {workspace}...")
    engine.build(full=False)
    
    live_server = None
    if live:
        from codegenome.live_server import LiveGraphServer
        live_server = LiveGraphServer(host="127.0.0.1", port=8765)
        live_server.start_background()
        click.echo("WebSocket server initialized on ws://127.0.0.1:8765")
    
    def serve_forever():
        import os
        os.chdir(engine.export_dir)
        # Suppress logging in SimpleHTTPRequestHandler to keep terminal clean
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        with TCPServer(("", 8000), QuietHandler) as httpd:
            httpd.serve_forever()
            
    server_thread = threading.Thread(target=serve_forever, daemon=True)
    server_thread.start()
    
    url = "http://localhost:8000/graph.html?live=1"
    click.echo(f"HTTP Server started. Opening live graph UI at {url}...")
    webbrowser.open(url)
    
    click.echo("Watching for .py file changes (Press Ctrl+C to stop)...")
    observer = Observer()
    handler = SurgicalUpdateHandler(engine, live_server=live_server)
    observer.schedule(handler, str(workspace), recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nStopping observer...")
        observer.stop()
    finally:
        observer.join()
        engine.close()
        if live_server:
            live_server.stop()


if __name__ == "__main__":
    cli()
