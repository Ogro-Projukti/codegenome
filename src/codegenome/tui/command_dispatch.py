"""Dashboard command dispatch helpers for the TUI."""

from __future__ import annotations

from functools import partial
from typing import Any, Callable

from codegenome.service import CodeGenomeService
from codegenome.tui.constants import LogChannel
from codegenome.tui.memory import (
    MemoryModeSettings,
    evolve_mode_cli_args,
    mcp_mode_cli_args,
)


Emit = Callable[[str], None]
ServiceTask = Callable[[Emit], None]


def dispatch_command_button(
    app: Any,
    service: CodeGenomeService,
    button_id: str,
    workspace: str,
    memory_settings: MemoryModeSettings,
) -> None:
    """Run the engine operation behind a dashboard command button."""
    if button_id == "btn-analyze":
        run_service_task(
            app,
            "Analyze",
            "analyze",
            partial(analyze_task, service, workspace, memory_settings),
            refresh_summary=True,
        )
    elif button_id == "btn-export":
        run_service_task(
            app,
            "Export (json)",
            "general",
            partial(export_task, service, workspace),
        )
    elif button_id == "btn-rules":
        run_service_task(
            app,
            "Generate AI Rules",
            "general",
            partial(rules_task, service, workspace),
        )
    elif button_id == "btn-mcp-local":
        app.run_command(
            [
                "codegenome",
                "mcp-start",
                "--path",
                workspace,
                "--transport",
                "http",
                "--port",
                "7331",
                *mcp_mode_cli_args(memory_settings),
            ],
            channel="mcp",
            is_background=True,
        )
    elif button_id == "btn-mcp-lan":
        app.run_command(
            [
                "codegenome",
                "mcp-start",
                "--path",
                workspace,
                "--transport",
                "http",
                "--port",
                "7331",
                "--lan",
                *mcp_mode_cli_args(memory_settings),
            ],
            channel="mcp",
            is_background=True,
        )
    elif button_id == "btn-evolve-local":
        app.run_command(
            [
                "codegenome",
                "evolve",
                "--live",
                *evolve_mode_cli_args(memory_settings),
                workspace,
            ],
            channel="evolve",
            is_background=True,
        )
    elif button_id == "btn-evolve-lan":
        app.run_command(
            [
                "codegenome",
                "evolve",
                "--live",
                "--lan",
                *evolve_mode_cli_args(memory_settings),
                workspace,
            ],
            channel="evolve",
            is_background=True,
        )
    elif button_id == "btn-stop-mcp":
        app.stop_processes_for_channel("mcp", "MCP server")
    elif button_id == "btn-stop-evolve":
        app.stop_processes_for_channel("evolve", "Live Evolve")


def analyze_task(
    service: CodeGenomeService,
    workspace: str,
    settings: MemoryModeSettings,
    emit: Emit,
) -> None:
    """Run an in-process analyze and report node/edge totals."""
    result = service.analyze(
        workspace,
        memory_bounded=settings.analyze_memory_bounded,
        max_working_files=settings.max_working_files,
        on_progress=emit,
    )
    emit(
        f"Build complete: {result.graph.number_of_nodes()} nodes, "
        f"{result.graph.number_of_edges()} edges."
    )


def export_task(service: CodeGenomeService, workspace: str, emit: Emit) -> None:
    """Run an in-process JSON export and report output paths."""
    result_paths = service.export(workspace, ["json"], on_progress=emit)
    for fmt, out_path in result_paths.items():
        emit(f"Exported {fmt} → {out_path}")


def rules_task(service: CodeGenomeService, workspace: str, emit: Emit) -> None:
    """Generate AI rule files in-process and report output paths."""
    results = service.generate_rules(workspace, clients=["all"], on_progress=emit)
    if not results:
        emit("No clients selected or found.")
        return
    for label, out_path in results:
        emit(f"Generated {label} rules at: {out_path}")


def run_service_task(
    app: Any,
    label: str,
    channel: LogChannel,
    func: ServiceTask,
    *,
    refresh_summary: bool = False,
) -> None:
    """Run a service callable in a thread worker, streaming output to a panel."""
    app.focus_log_tab(channel)
    app.write_log(channel, f"\n[bold blue]> {label}[/bold blue]")
    app.run_worker(
        partial(execute_service_task, app, label, channel, func, refresh_summary),
        thread=True,
        exclusive=False,
        exit_on_error=False,
        group="service",
    )


def execute_service_task(
    app: Any,
    label: str,
    channel: LogChannel,
    func: ServiceTask,
    refresh_summary: bool,
) -> None:
    """Worker body: invoke ``func`` and marshal log updates to the UI thread."""

    def emit(message: str) -> None:
        app.call_from_thread(app.write_log, channel, message)

    try:
        func(emit)
    except Exception as exc:  # noqa: BLE001 - surface failures in the log panel
        app.call_from_thread(
            app.write_log, channel, f"[bold red]{label} failed:[/bold red] {exc}"
        )
        return

    app.call_from_thread(app.write_log, channel, f"[[bold green]{label} complete[/bold green]]")
    if refresh_summary:
        app.call_from_thread(app.refresh_dashboard_summary)
