"""Unified Click command-line interface for CodeGenome."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import click

from codegenome.core import CodeGenomeConfig, CodeGenomeEngine
from codegenome.exporter import SUPPORTED_FORMATS
from codegenome.version import __version__

EXPORT_FORMATS = tuple(sorted(SUPPORTED_FORMATS))
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    default="INFO",
    show_default=True,
    help="Logging verbosity for this invocation.",
)
@click.version_option(version=__version__)
def cli(log_level: str) -> None:
    """Build, inspect, and serve local codebase knowledge graphs."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(levelname)s %(name)s: %(message)s",
    )


@cli.command()
@click.option("--full", is_flag=True, help="Force a full rebuild.")
@click.option(
    "--format",
    "export_formats",
    multiple=True,
    type=click.Choice(EXPORT_FORMATS, case_sensitive=False),
    default=("json",),
    show_default=True,
    help="Export format written after analysis; repeat for multiple formats.",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Timeline database path (default: PATH/.genome/codegenome.db).",
)
@click.option("--watch", is_flag=True, help="Watch for changes after the initial build.")
@click.option(
    "--watch-debounce",
    type=click.FloatRange(min=0.0),
    default=30.0,
    show_default=True,
    metavar="SECONDS",
    help="Inactivity interval before a watched rebuild.",
)
@click.option(
    "--live-graph",
    is_flag=True,
    help="Poll workspace totals and rebuild when the workspace grows.",
)
@click.option(
    "--live-graph-interval",
    type=click.FloatRange(min=1.0),
    default=30.0,
    show_default=True,
    metavar="SECONDS",
    help="Polling interval used by --live-graph.",
)
@click.option(
    "--start-mcp",
    "--mcp",
    is_flag=True,
    help="Start loopback HTTP MCP after the build.",
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
    type=click.IntRange(min=1),
    help="Maximum resident files in memory-bounded mode.",
)
@click.option(
    "--retain-snapshots",
    default=100,
    show_default=True,
    type=click.IntRange(min=1),
    help="Retain at most this many recent snapshots.",
)
@click.option(
    "--retention-days",
    default=None,
    type=click.FloatRange(min=0.0),
    help="Also remove snapshots older than this many days.",
)
@click.argument("path", default=".", type=click.Path(path_type=Path, exists=True, file_okay=False))
def analyze(
    path: Path,
    full: bool,
    export_formats: tuple[str, ...],
    db_path: Path | None,
    watch: bool,
    watch_debounce: float,
    live_graph: bool,
    live_graph_interval: float,
    start_mcp: bool,
    memory_bounded: bool,
    max_working_files: int,
    retain_snapshots: int,
    retention_days: float | None,
) -> None:
    """Build or incrementally update the graph for PATH."""
    if start_mcp and not (watch or live_graph):
        raise click.UsageError(
            "--mcp requires --watch or --live-graph; use 'mcp-start' for a standalone server"
        )
    workspace = path.resolve()
    click.echo(f"Analyzing workspace at {workspace}...")
    config = CodeGenomeConfig(
        workspace=workspace,
        db_path=db_path.resolve() if db_path else None,
        export_formats=tuple(fmt.lower() for fmt in export_formats),
        start_mcp=start_mcp,
        watch_debounce_seconds=watch_debounce,
        live_graph=live_graph,
        live_graph_poll_seconds=live_graph_interval,
        memory_bounded=memory_bounded,
        max_working_files=max_working_files,
        snapshot_retention_count=retain_snapshots,
        snapshot_retention_days=retention_days,
    )
    engine = CodeGenomeEngine(config)

    try:
        result = engine.build(full=full, on_progress=click.echo)
        click.echo(
            f"Build complete: {result.graph.number_of_nodes()} nodes, "
            f"{result.graph.number_of_edges()} edges."
        )
        if start_mcp:
            process = engine.start_mcp()
            click.echo(
                f"MCP server started (pid={process.pid}) on "
                f"{config.mcp_host}:{config.mcp_port}."
            )
        if live_graph:
            engine.monitor_live_graph()
        elif watch:
            engine.watch()
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(f"Analysis failed: {exc}") from exc
    finally:
        engine.close()


@cli.command()
@click.option(
    "--format",
    "export_formats",
    multiple=True,
    required=True,
    type=click.Choice(EXPORT_FORMATS, case_sensitive=False),
    help="Export format; repeat for multiple formats.",
)
@click.option(
    "--path",
    default=".",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    show_default=True,
    help="Workspace containing the graph database.",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Timeline database path (default: PATH/.genome/codegenome.db).",
)
def export(export_formats: tuple[str, ...], path: Path, db_path: Path | None) -> None:
    """Export an existing graph in one or more formats."""
    workspace = path.resolve()
    engine = CodeGenomeEngine(
        CodeGenomeConfig(
            workspace=workspace,
            db_path=db_path.resolve() if db_path else None,
        )
    )
    try:
        if engine.builder.graph.number_of_nodes() == 0:
            raise click.ClickException(
                "No graph found. Run 'codegenome analyze' before exporting."
            )
        result_paths = engine.export(formats=[fmt.lower() for fmt in export_formats])
        for name, output_path in sorted(result_paths.items()):
            click.echo(f"Exported {name}: {output_path}")
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(f"Export failed: {exc}") from exc
    finally:
        engine.close()


@cli.command(name="mcp-start")
@click.option(
    "--path",
    default=".",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    show_default=True,
    help="Workspace served by MCP.",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Timeline database path (default: PATH/.genome/codegenome.db).",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"], case_sensitive=False),
    default="stdio",
    show_default=True,
    help="MCP transport protocol.",
)
@click.option("--port", type=click.IntRange(min=1, max=65535), default=7331, show_default=True)
@click.option(
    "--lan",
    is_flag=True,
    help="Allow HTTP to bind on 0.0.0.0 instead of loopback.",
)
@click.option(
    "--memory-bounded",
    is_flag=True,
    help="Load query subgraphs from SQLite on demand.",
)
@click.option(
    "--full-analysis-on-demand",
    is_flag=True,
    help="Allow global tools to temporarily load the full graph.",
)
def mcp_start(
    path: Path,
    db_path: Path | None,
    transport: str,
    port: int,
    lan: bool,
    memory_bounded: bool,
    full_analysis_on_demand: bool,
) -> None:
    """Start the MCP server for an analyzed workspace."""
    workspace = path.resolve()
    resolved_db = (db_path or workspace / ".genome" / "codegenome.db").resolve()
    transport = transport.lower()
    if lan and transport != "http":
        raise click.UsageError("--lan requires --transport http")
    if not resolved_db.is_file():
        raise click.ClickException(
            f"No CodeGenome database found at {resolved_db}. Run 'codegenome analyze' first."
        )

    host = "0.0.0.0" if lan else "127.0.0.1"
    args = ["--db-path", str(resolved_db), "--transport", transport]
    if memory_bounded:
        args.append("--memory-bounded")
    if full_analysis_on_demand:
        args.append("--full-analysis-on-demand")
    if transport == "http":
        args.extend(["--host", host, "--port", str(port)])
        if lan:
            args.append("--allow-remote-http")

    click.echo(
        f"Starting MCP for {workspace} (DB: {resolved_db}) via {transport}...",
        err=True,
    )
    from codegenome.mcp_server import main as mcp_main

    exit_code = mcp_main(args)
    if exit_code:
        raise click.exceptions.Exit(exit_code)


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
    type=click.IntRange(min=1),
    help="Maximum resident files in memory-bounded mode.",
)
@click.option(
    "--retain-snapshots",
    default=100,
    show_default=True,
    type=click.IntRange(min=1),
    help="Retain at most this many recent snapshots.",
)
@click.option(
    "--retention-days",
    default=None,
    type=click.FloatRange(min=0.0),
    help="Also remove snapshots older than this many days.",
)
@click.argument("path", default=".", type=click.Path(path_type=Path, exists=True, file_okay=False))
def evolve(
    path: Path,
    live: bool,
    lan: bool,
    memory_bounded: bool,
    max_working_files: int,
    retain_snapshots: int,
    retention_days: float | None,
) -> None:
    """Observe PATH continuously and serve the live graph UI."""
    if lan and not live:
        raise click.UsageError("--lan requires --live")

    from codegenome.live_session import LiveSession, LiveSessionConfig

    session = LiveSession(
        LiveSessionConfig(
            workspace=path.resolve(),
            live=live,
            lan=lan,
            memory_bounded=memory_bounded,
            max_working_files=max_working_files,
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
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    show_default=True,
    help="Workspace whose snapshot database should be maintained.",
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
    help="VACUUM after pruning to return free pages to disk.",
)
def db_maintain(
    path: Path,
    retain_snapshots: int,
    max_age_days: float | None,
    compact: bool,
) -> None:
    """Prune snapshot history transactionally and optionally compact SQLite."""
    from codegenome.timeline import GraphTimeline

    db_path = path.resolve() / ".genome" / "codegenome.db"
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


def _resolved_database(path: Path, db_path: Path | None) -> Path:
    return (db_path or path.resolve() / ".genome" / "codegenome.db").resolve()


def _run_store_query(db_path: Path, query: Callable[[object], object]) -> None:
    from codegenome.graph_store import GraphStore, GraphStoreError

    if not db_path.is_file():
        raise click.ClickException(f"No CodeGenome database found at {db_path}")
    store = GraphStore(db_path, memory_bounded=True)
    try:
        store.open()
        click.echo(json.dumps(query(store), sort_keys=True))
    except (GraphStoreError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        store.close()


def _database_options(command: Callable[..., object]) -> Callable[..., object]:
    command = click.option(
        "--db-path",
        type=click.Path(path_type=Path, dir_okay=False),
        help="Timeline database path (default: PATH/.genome/codegenome.db).",
    )(command)
    command = click.option(
        "--path",
        default=".",
        type=click.Path(path_type=Path, exists=True, file_okay=False),
        show_default=True,
        help="Workspace containing the timeline database.",
    )(command)
    return command


@cli.command()
@_database_options
@click.option("--node-id", help="Return history for one node ID.")
def timeline(path: Path, db_path: Path | None, node_id: str | None) -> None:
    """Print snapshot or node history as JSON."""
    _run_store_query(
        _resolved_database(path, db_path),
        lambda store: store.get_timeline(node_id=node_id),
    )


@cli.command()
@_database_options
@click.option("--snapshot-from", type=click.IntRange(min=1), required=True)
@click.option("--snapshot-to", type=click.IntRange(min=1), required=True)
def changes(
    path: Path,
    db_path: Path | None,
    snapshot_from: int,
    snapshot_to: int,
) -> None:
    """Print the delta between two snapshots as JSON."""
    _run_store_query(
        _resolved_database(path, db_path),
        lambda store: store.get_changes(
            snapshot_from=snapshot_from,
            snapshot_to=snapshot_to,
        ),
    )


@cli.command()
@_database_options
@click.option("--file", "file_path", help="Return churn for a single file path.")
@click.option("--snapshot-from", type=click.IntRange(min=1))
@click.option("--snapshot-to", type=click.IntRange(min=1))
@click.option("--limit", type=click.IntRange(min=1), default=25, show_default=True)
def churn(
    path: Path,
    db_path: Path | None,
    file_path: str | None,
    snapshot_from: int | None,
    snapshot_to: int | None,
    limit: int,
) -> None:
    """Print file or repository churn as JSON."""
    _run_store_query(
        _resolved_database(path, db_path),
        lambda store: store.get_churn(
            file_path=file_path,
            snapshot_from=snapshot_from,
            snapshot_to=snapshot_to,
            limit=limit,
        ),
    )


@cli.command()
@click.argument("path", default=".", type=click.Path(path_type=Path, exists=True, file_okay=False))
def metrics(path: Path) -> None:
    """Print workspace file and line totals as JSON."""
    from codegenome.workspace_metrics import WorkspaceMetricsScanner

    click.echo(json.dumps(asdict(WorkspaceMetricsScanner(path.resolve()).scan()), sort_keys=True))


@cli.command()
@click.option(
    "--path",
    default=".",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    show_default=True,
    help="Workspace whose runtime and database should be checked.",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Timeline database path (default: PATH/.genome/codegenome.db).",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the report as JSON.")
def doctor(path: Path, db_path: Path | None, json_output: bool) -> None:
    """Check loopback network defaults and SQLite multiedge integrity."""
    from codegenome.doctor import run_doctor

    report = run_doctor(path, db_path)
    if json_output:
        click.echo(json.dumps(report.as_dict(), sort_keys=True))
    else:
        for check in report.checks:
            status = "PASS" if check.passed else "FAIL"
            click.echo(f"[{status}] {check.name}: {check.detail}")
        click.echo("Doctor result: PASS" if report.passed else "Doctor result: FAIL")
    if not report.passed:
        raise click.exceptions.Exit(1)


@cli.command(name="install-mcp")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Timeline database path (default: PATH/.genome/codegenome.db).",
)
@click.option(
    "--python",
    "python_executable",
    default=sys.executable,
    show_default=True,
    help="Python executable written for stdio transport.",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"], case_sensitive=False),
    default="stdio",
    show_default=True,
)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=click.IntRange(min=1, max=65535), default=7331, show_default=True)
@click.option(
    "--client",
    multiple=True,
    type=click.Choice(
        ["claude", "cursor", "codex", "gemini", "aider", "windsurf", "copilot"],
        case_sensitive=False,
    ),
    help="Install only selected clients; repeat for multiple clients.",
)
@click.option("--dry-run", is_flag=True, help="Print target paths without writing files.")
@click.argument("path", default=".", type=click.Path(path_type=Path, exists=True, file_okay=False))
def install_mcp(
    db_path: Path | None,
    python_executable: str,
    transport: str,
    host: str,
    port: int,
    client: tuple[str, ...],
    dry_run: bool,
    path: Path,
) -> None:
    """Write CodeGenome MCP entries into supported client configs."""
    from codegenome.installer import (
        build_server_entry,
        client_targets,
        install_client,
    )

    resolved_db = _resolved_database(path, db_path)
    server_entry = build_server_entry(
        python_executable=python_executable,
        db_path=str(resolved_db),
        transport=transport.lower(),
        host=host,
        port=port,
    )
    selected = {name.lower() for name in client} if client else None
    installed: list[tuple[str, Path]] = []
    for target in client_targets():
        if selected is not None and target.key not in selected:
            continue
        output_path = install_client(target, server_entry=server_entry, dry_run=dry_run)
        installed.append((target.label, output_path))

    if not installed:
        raise click.ClickException("No clients selected.")
    action = "Would install" if dry_run else "Installed"
    for label, output_path in installed:
        click.echo(f"{action} {label}: {output_path}")


@cli.command()
@click.option(
    "--client",
    multiple=True,
    type=click.Choice(["cursor", "copilot", "windsurf", "agents", "all"], case_sensitive=False),
    help="Target agent client; repeat for multiple clients.",
)
@click.option("--port", type=click.IntRange(min=1, max=65535), default=7331, show_default=True)
@click.option("--dry-run", is_flag=True, help="Print target paths without writing files.")
@click.argument("path", default=".", type=click.Path(path_type=Path, exists=True, file_okay=False))
def rules(client: tuple[str, ...], port: int, dry_run: bool, path: Path) -> None:
    """Generate agent instruction files that point to the MCP server."""
    from codegenome.rules import generate_rules

    workspace = path.resolve()
    selected = list(client) if client else ["all"]
    try:
        results = generate_rules(
            selected_clients=selected,
            port=port,
            workspace=workspace,
            dry_run=dry_run,
        )
    except Exception as exc:
        raise click.ClickException(f"Rule generation failed: {exc}") from exc
    if not results:
        click.echo("No clients selected or found.")
        return

    action = "Would generate" if dry_run else "Generated"
    for label, output_path in results:
        try:
            display_path = output_path.relative_to(workspace)
        except ValueError:
            display_path = output_path
        click.echo(f"{action} {label} rules at: {display_path}")


@cli.command()
def tui() -> None:
    """Launch the interactive Textual dashboard."""
    from codegenome.tui import main as tui_main

    tui_main()


if __name__ == "__main__":
    cli()
