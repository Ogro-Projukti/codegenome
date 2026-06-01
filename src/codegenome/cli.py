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
    """Triggers the tree-sitter scan, builds the ASTs, and saves to the SQLite graph_store.

    Args:
        path (str): The workspace directory path to analyze.
    """
    click.echo(f"Analyzing workspace at {path}...")
    workspace = Path(path).resolve()
    config = WatcherConfig(workspace=workspace, export_formats=("json",))
    engine = WatcherEngine(config)

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
def mcp_start(path: str, transport: str, port: int, lan: bool):
    """Initializes and starts the MCP server so external LLMs can connect.

    Args:
        path (str): The workspace directory path for the MCP server.
        transport (str): Transport protocol (stdio or http).
        port (int): Port to bind to when using HTTP transport.
        lan (bool): Whether to expose HTTP transport on the local network.
    """
    workspace = Path(path).resolve()
    config = WatcherConfig(workspace=workspace)
    engine = WatcherEngine(config)
    db_path = engine.db_path
    engine.close()  # Close the engine since the MCP server process will open its own connection
    
    click.echo(f"Starting MCP server for workspace {workspace} (DB: {db_path}) via {transport}...", err=True)
    
    from codegenome.mcp_server import main as mcp_main
    args = ["--db-path", str(db_path), "--transport", transport.lower()]
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
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def evolve(path: str, live: bool, lan: bool):
    """Start real-time architectural observer and open live UI.

    Args:
        path (str): The workspace directory path to observe.
        live (bool): Whether to enable WebSocket real-time broadcast.
        lan (bool): Whether to bind services for LAN access.
    """
    import time
    import threading
    import webbrowser
    from http.server import SimpleHTTPRequestHandler
    from socketserver import ThreadingTCPServer
    from watchdog.observers import Observer
    from codegenome.ai_chat import AIChatError, chat_completion, load_models, settings_payload
    from codegenome.watcher import WatcherConfig, WatcherEngine, SurgicalUpdateHandler

    workspace = Path(path).resolve()
    config = WatcherConfig(workspace=workspace, export_formats=("json", "html"))
    engine = WatcherEngine(config)
    
    click.echo(f"Running initial build for {workspace}...")
    engine.build(full=False)
    
    from codegenome.network_utils import get_lan_ip

    http_port = 8000
    ws_port = 8765
    bind_host = "0.0.0.0" if lan else "127.0.0.1"
    lan_ip = get_lan_ip() if lan else "127.0.0.1"

    live_server = None
    if live:
        from codegenome.live_server import LiveGraphServer
        live_server = LiveGraphServer(host=bind_host, port=ws_port)
        live_server.start_background()
        if lan:
            click.echo(f"WebSocket server listening on ws://0.0.0.0:{ws_port}")
            click.echo(f"  LAN clients connect to ws://{lan_ip}:{ws_port}")
        else:
            click.echo(f"WebSocket server initialized on ws://127.0.0.1:{ws_port}")

    def serve_forever():
        import json

        class QuietHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(engine.export_dir), **kwargs)

            def log_message(self, format, *args):
                pass

            def do_GET(self):
                if self.path == "/ai/settings":
                    self._send_json(settings_payload(engine.genome_dir))
                    return
                super().do_GET()

            def do_POST(self):
                if self.path == "/ai/models":
                    self._handle_models()
                    return
                if self.path == "/ai/chat":
                    self._handle_chat()
                    return
                self.send_error(404, "Unknown AI endpoint")

            def _handle_models(self):
                try:
                    payload = self._read_json_body()
                    models = load_models(
                        engine.genome_dir,
                        str(payload.get("provider", "")),
                        _optional_string(payload.get("api_key")),
                        save_api_key=bool(payload.get("save_api_key")),
                    )
                    self._send_json({"models": models})
                except AIChatError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                except Exception as exc:  # noqa: BLE001 - keep live server responsive
                    self._send_json({"error": f"AI model loading failed: {exc}"}, status=500)

            def _handle_chat(self):
                try:
                    payload = self._read_json_body()
                    answer = chat_completion(
                        engine.genome_dir,
                        engine.graph_json_path,
                        str(payload.get("provider", "")),
                        str(payload.get("model", "")),
                        payload.get("messages", []),
                        _optional_string(payload.get("api_key")),
                        _optional_string(payload.get("selected_node_id")),
                        _optional_string(payload.get("context_size")),
                        save_api_key=bool(payload.get("save_api_key")),
                    )
                    self._send_json({"message": answer})
                except AIChatError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                except Exception as exc:  # noqa: BLE001 - keep live server responsive
                    self._send_json({"error": f"AI chat failed: {exc}"}, status=500)

            def _read_json_body(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                return json.loads(raw.decode("utf-8"))

            def _send_json(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        def _optional_string(value):
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        with ThreadingTCPServer((bind_host if lan else "", http_port), QuietHandler) as httpd:
            httpd.serve_forever()

    server_thread = threading.Thread(target=serve_forever, daemon=True)
    server_thread.start()

    live_query = "?live=1"
    local_url = f"http://localhost:{http_port}/graph.html{live_query}"
    if lan:
        lan_url = f"http://{lan_ip}:{http_port}/graph.html{live_query}"
        click.echo(f"HTTP server listening on http://0.0.0.0:{http_port}")
        click.echo(f"  Open locally:  {local_url}")
        click.echo(f"  Share on LAN:  {lan_url}")
    else:
        click.echo(f"HTTP Server started. Opening live graph UI at {local_url}...")
    webbrowser.open(local_url)
    
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
