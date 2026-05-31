"""Textual TUI for CodeGenome."""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, Footer, Header, Input, Label, RichLog, Static, TabbedContent, TabPane
from textual.worker import Worker, WorkerState, get_current_worker

from codegenome.workspace_info import (
    WorkspaceInfo,
    collect_workspace_info,
    format_gitignore_files_panel,
    format_tracked_extensions_panel,
    format_tracked_folders_panel,
    format_workspace_summary,
)

LogChannel = Literal["analyze", "mcp", "evolve", "general"]

PAGE_SET = "page-set-workspace"
PAGE_INFO = "page-workspace-info"
PAGE_MAIN = "page-main"


@dataclass
class ActiveProcess:
    """Track a background subprocess and its log destination."""

    process: asyncio.subprocess.Process
    channel: LogChannel


class CodeGenomeTUI(App):
    """A Textual app for managing CodeGenome."""

    BINDINGS = [
        ("ctrl+q", "quit_app", "Quit"),
        ("ctrl+c", "quit_app", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    ContentSwitcher {
        height: 1fr;
    }

    .page {
        height: 1fr;
        layout: vertical;
    }

    #page-set-workspace {
        align: center middle;
        padding: 2 4;
    }

    .set-workspace-panel {
        width: 60;
        max-width: 100%;
        height: auto;
        padding: 2 3;
        border: solid green;
    }

    .set-workspace-panel Label {
        margin-bottom: 1;
    }

    .set-workspace-panel Input {
        margin-bottom: 1;
    }

    .page-actions {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #page-workspace-info {
        padding: 1 2;
    }

    #workspace-scan-status {
        height: auto;
        margin-bottom: 1;
    }

    #workspace-info-panels {
        height: 1fr;
        layout: horizontal;
    }

    .info-panel {
        width: 1fr;
        height: 1fr;
        layout: vertical;
        border: solid $surface-lighten-1;
        margin: 0 1;
        padding: 1;
    }

    .info-panel Label {
        height: auto;
        margin-bottom: 1;
    }

    .info-panel RichLog {
        height: 1fr;
        min-height: 6;
    }

    #workspace-summary-bar {
        height: auto;
        padding: 0 2;
        margin: 1 1 0 1;
        border: solid green;
    }

    #commands-container {
        height: auto;
        padding: 1 2;
        border: solid blue;
        margin: 1 1 0 1;
        layout: vertical;
    }

    .command-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin: 0 0 1 0;
    }

    .command-row:last-child {
        margin-bottom: 0;
    }

    Button {
        margin: 0 1;
    }

    #log-container {
        height: 1fr;
        padding: 0 1 1 1;
        margin: 0 1 1 1;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 0 1;
    }

    .log-pane {
        height: 1fr;
        layout: vertical;
    }

    .log-pane RichLog {
        height: 1fr;
        width: 1fr;
        border: solid $surface-lighten-1;
    }

    #tab-analyze RichLog {
        border: solid cyan;
    }

    #tab-mcp RichLog {
        border: solid green;
    }

    #tab-evolve RichLog {
        border: solid magenta;
    }

    #tab-general RichLog {
        border: solid white;
    }
    """

    LOG_IDS: dict[LogChannel, str] = {
        "analyze": "log-analyze",
        "mcp": "log-mcp",
        "evolve": "log-evolve",
        "general": "log-general",
    }

    TAB_IDS: dict[LogChannel, str] = {
        "analyze": "tab-analyze",
        "mcp": "tab-mcp",
        "evolve": "tab-evolve",
        "general": "tab-general",
    }

    COMMAND_BUTTON_IDS: tuple[str, ...] = (
        "btn-analyze",
        "btn-export",
        "btn-rules",
        "btn-mcp",
        "btn-evolve-local",
        "btn-evolve-lan",
        "btn-stop",
    )

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        with ContentSwitcher(initial=PAGE_SET):
            with Container(id=PAGE_SET, classes="page"):
                with Vertical(classes="set-workspace-panel"):
                    yield Label("[bold]Set Workspace[/bold]")
                    yield Label("Enter the path to your project root:")
                    yield Input(value=".", id="workspace-input", placeholder="Enter path to workspace...")
                    with Horizontal(classes="page-actions"):
                        yield Button("Set", id="btn-set-workspace", variant="primary")
                        yield Button("Quit", id="btn-quit", variant="default")

            with Container(id=PAGE_INFO, classes="page"):
                yield Label("[bold]Workspace Scan Results[/bold]")
                yield Static(id="workspace-scan-status", markup=True)
                with Horizontal(id="workspace-info-panels"):
                    with Vertical(classes="info-panel"):
                        yield Label("[bold cyan]Tracked Folders[/bold cyan]")
                        yield RichLog(id="info-folders", markup=True, highlight=False, wrap=True)
                    with Vertical(classes="info-panel"):
                        yield Label("[bold cyan]File Extensions[/bold cyan]")
                        yield RichLog(id="info-extensions", markup=True, highlight=False, wrap=True)
                    with Vertical(classes="info-panel"):
                        yield Label("[bold cyan].gitignore Files[/bold cyan]")
                        yield RichLog(id="info-gitignore", markup=True, highlight=False, wrap=True)
                with Horizontal(classes="page-actions"):
                    yield Button("Back", id="btn-back-to-set", variant="default")
                    yield Button("Continue", id="btn-continue", variant="primary", disabled=True)

            with Container(id=PAGE_MAIN, classes="page"):
                with Horizontal(id="workspace-summary-bar"):
                    yield Static(id="workspace-summary", markup=True)
                    yield Button("Change Workspace", id="btn-change-workspace", variant="default")

                with Container(id="commands-container"):
                    with Horizontal(classes="command-row"):
                        yield Button("Analyze", id="btn-analyze", variant="primary")
                        yield Button("Export", id="btn-export", variant="primary")
                        yield Button("Generate AI Rules", id="btn-rules", variant="primary")
                        yield Button("Start MCP", id="btn-mcp", variant="success")
                    with Horizontal(classes="command-row"):
                        yield Button("Live Evolve (Local)", id="btn-evolve-local", variant="success")
                        yield Button("Live Evolve (LAN)", id="btn-evolve-lan", variant="success")

                with Container(id="log-container"):
                    with TabbedContent(initial="tab-analyze"):
                        with TabPane("Analyze", id="tab-analyze"):
                            with Vertical(classes="log-pane"):
                                yield RichLog(id="log-analyze", markup=True, highlight=True)
                        with TabPane("MCP Server", id="tab-mcp"):
                            with Vertical(classes="log-pane"):
                                yield RichLog(id="log-mcp", markup=True, highlight=True)
                        with TabPane("Live Evolve", id="tab-evolve"):
                            with Vertical(classes="log-pane"):
                                yield RichLog(id="log-evolve", markup=True, highlight=True)
                        with TabPane("General", id="tab-general"):
                            with Vertical(classes="log-pane"):
                                yield RichLog(id="log-general", markup=True, highlight=True)

                with Horizontal(classes="page-actions"):
                    yield Button("Stop Active Processes", id="btn-stop", variant="error")
                    yield Button("Quit", id="btn-quit-main", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts. Initializes widgets and state."""
        self._workspace_poll_timer = None
        self.pages = self.query_one(ContentSwitcher)
        self.workspace_input = self.query_one("#workspace-input", Input)
        self.workspace_scan_status = self.query_one("#workspace-scan-status", Static)
        self.info_folders_log = self.query_one("#info-folders", RichLog)
        self.info_extensions_log = self.query_one("#info-extensions", RichLog)
        self.info_gitignore_log = self.query_one("#info-gitignore", RichLog)
        self.workspace_summary = self.query_one("#workspace-summary", Static)
        self.continue_button = self.query_one("#btn-continue", Button)
        self.set_workspace_button = self.query_one("#btn-set-workspace", Button)
        self.log_tabs = self.query_one(TabbedContent)
        self.log_widgets: dict[LogChannel, RichLog] = {
            channel: self.query_one(f"#{log_id}", RichLog)
            for channel, log_id in self.LOG_IDS.items()
        }
        self.command_buttons: dict[str, Button] = {
            button_id: self.query_one(f"#{button_id}", Button)
            for button_id in self.COMMAND_BUTTON_IDS
        }
        self.active_processes: list[ActiveProcess] = []
        self._subprocesses: set[asyncio.subprocess.Process] = set()
        self._workspace_path: str | None = None
        self._pending_workspace_info: WorkspaceInfo | None = None
        self._main_initialized = False

        self.set_commands_enabled(False)

    def show_page(self, page_id: str) -> None:
        """Switch to the given page."""
        self.pages.current = page_id

    def get_workspace_path(self) -> str:
        """Return the active workspace path."""
        if self._workspace_path is not None:
            return self._workspace_path
        return self.workspace_input.value.strip() or "."

    def set_commands_enabled(self, enabled: bool) -> None:
        """Enable or disable command buttons while a workspace scan runs."""
        for button in self.command_buttons.values():
            button.disabled = not enabled

    def set_workspace_flow_enabled(self, enabled: bool) -> None:
        """Enable or disable workspace setup controls during a scan."""
        self.set_workspace_button.disabled = not enabled
        self.workspace_input.disabled = not enabled

    def clear_workspace_scan_panels(self, message: str = "") -> None:
        """Clear the three scan result panels."""
        for panel in (self.info_folders_log, self.info_extensions_log, self.info_gitignore_log):
            panel.clear()
            if message:
                panel.write(message)

    def update_workspace_scan_panels(self, info: WorkspaceInfo) -> None:
        """Populate the three scan result panels from workspace info."""
        if info.error:
            self.workspace_scan_status.update(
                f"[bold]Root:[/bold] {info.root}  "
                f"[bold red]Error:[/bold red] {info.error}"
            )
        else:
            dir_count = len(info.tracked_directories)
            file_count = len(info.tracked_files)
            self.workspace_scan_status.update(
                f"[bold]Root:[/bold] {info.root}  "
                f"[dim]|[/dim]  "
                f"{file_count} file{'s' if file_count != 1 else ''} in "
                f"{dir_count} director{'ies' if dir_count != 1 else 'y'}"
            )

        self.info_folders_log.clear()
        self.info_folders_log.write(format_tracked_folders_panel(info))

        self.info_extensions_log.clear()
        self.info_extensions_log.write(format_tracked_extensions_panel(info))

        self.info_gitignore_log.clear()
        self.info_gitignore_log.write(format_gitignore_files_panel(info))

    def refresh_workspace_info(self, *, on_page: str = PAGE_INFO) -> None:
        """Load ignore rules and tracked paths for the current workspace input."""
        path = self.workspace_input.value.strip() or "."
        self.set_workspace_flow_enabled(False)
        self.continue_button.disabled = True
        self.workspace_scan_status.update("[dim]Scanning workspace...[/dim]")
        self.clear_workspace_scan_panels("[dim]Scanning...[/dim]")
        self.show_page(on_page)
        self.run_worker(
            self._load_workspace_info(path),
            exclusive=True,
            group="workspace-info",
        )

    async def _load_workspace_info(self, path: str) -> None:
        """Collect workspace info off the UI thread and update the panel."""
        worker = get_current_worker()
        if worker.is_cancelled:
            return

        info = await asyncio.to_thread(collect_workspace_info, Path(path))
        if worker.is_cancelled:
            return

        self._pending_workspace_info = info
        self.update_workspace_scan_panels(info)

    def background_refresh_workspace_info(self) -> None:
        """Periodically refresh workspace counts in the background."""
        if getattr(self, "_workspace_path", None) and getattr(self, "pages", None) and self.pages.current == PAGE_MAIN:
            self.run_worker(
                self._do_background_refresh(self._workspace_path),
                exclusive=True,
                group="workspace-info-bg",
            )

    async def _do_background_refresh(self, path: str) -> None:
        """Fetch updated info without blocking or changing UI state heavily."""
        worker = get_current_worker()
        info = await asyncio.to_thread(collect_workspace_info, Path(path))
        if worker.is_cancelled:
            return
        
        # Only update the summary bar to avoid flashing the UI
        self.workspace_summary.update(format_workspace_summary(info))

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Re-enable controls and surface workspace scan failures."""
        if event.worker.group != "workspace-info":
            return

        self.set_workspace_flow_enabled(True)

        if event.state == WorkerState.SUCCESS:
            info = self._pending_workspace_info
            self.continue_button.disabled = info is None or info.error is not None
            return

        if event.state == WorkerState.ERROR:
            self.continue_button.disabled = True
            self.workspace_scan_status.update(
                f"[bold red]Failed to scan workspace:[/bold red] {event.worker.error}"
            )
            self.clear_workspace_scan_panels("[bold red]Scan failed[/bold red]")

    def enter_main_dashboard(self) -> None:
        """Show the main dashboard after workspace confirmation."""
        info = self._pending_workspace_info
        if info is None or info.error is not None:
            return

        self._workspace_path = info.root
        self.workspace_summary.update(format_workspace_summary(info))
        self.show_page(PAGE_MAIN)

        if getattr(self, "_workspace_poll_timer", None) is None:
            self._workspace_poll_timer = self.set_interval(5.0, self.background_refresh_workspace_info)

        if not self._main_initialized:
            self._main_initialized = True
            self.write_log("general", "[bold green]CodeGenome TUI initialized.[/bold green]")
            self.write_log("general", "Use Analyze, MCP, or Live Evolve from the command buttons.")
            self.write_log("analyze", "[dim]Analyze output appears here.[/dim]")
            self.write_log("mcp", "[dim]MCP server output appears here.[/dim]")
            self.write_log("evolve", "[dim]Live Evolve output appears here.[/dim]")

        self.set_commands_enabled(True)

    def write_log(self, channel: LogChannel, message: str) -> None:
        """Append a line to the log panel for the given channel."""
        self.log_widgets[channel].write(message)

    def focus_log_tab(self, channel: LogChannel) -> None:
        """Switch the visible tab to the given log channel."""
        self.log_tabs.active = self.TAB_IDS[channel]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle command button presses."""
        button_id = event.button.id
        if button_id in self.COMMAND_BUTTON_IDS and event.button.disabled:
            return

        if button_id == "btn-set-workspace":
            self.refresh_workspace_info()
            return

        if button_id == "btn-back-to-set":
            self.show_page(PAGE_SET)
            return

        if button_id == "btn-continue":
            self.enter_main_dashboard()
            return

        if button_id == "btn-change-workspace":
            self.show_page(PAGE_SET)
            return

        workspace = self.get_workspace_path()

        if button_id == "btn-analyze":
            self.run_command(
                ["codegenome", "analyze", workspace],
                channel="analyze",
            )
        elif button_id == "btn-export":
            self.run_command(
                ["codegenome", "export", "--format", "json", "--path", workspace],
                channel="general",
            )
        elif button_id == "btn-rules":
            self.run_command(
                ["codegenome", "rules", "--client", "all", workspace],
                channel="general",
            )
        elif button_id == "btn-mcp":
            self.run_command(
                ["codegenome", "mcp-start", "--path", workspace, "--transport", "http", "--port", "7331"],
                channel="mcp",
                is_background=True,
            )
        elif button_id == "btn-evolve-local":
            self.run_command(
                ["codegenome", "evolve", "--live", workspace],
                channel="evolve",
                is_background=True,
            )
        elif button_id == "btn-evolve-lan":
            self.run_command(
                ["codegenome", "evolve", "--live", "--lan", workspace],
                channel="evolve",
                is_background=True,
            )
        elif button_id == "btn-stop":
            self.stop_all_processes()
        elif button_id in ("btn-quit", "btn-quit-main"):
            self.quit_app()

    def run_command(
        self,
        cmd: list[str],
        *,
        channel: LogChannel,
        is_background: bool = False,
    ) -> None:
        """Run a CLI command and stream output to the matching log panel."""
        command_str = " ".join(cmd)
        self.focus_log_tab(channel)
        self.write_log(channel, f"\n[bold blue]> Running:[/bold blue] {command_str}")
        self.run_worker(
            self._execute_process(cmd, channel=channel, is_background=is_background),
            exclusive=False,
            exit_on_error=False,
            group="command",
        )

    def _track_subprocess(self, process: asyncio.subprocess.Process) -> None:
        """Register a subprocess so shutdown can close its pipes."""
        self._subprocesses.add(process)

    def _untrack_subprocess(self, process: asyncio.subprocess.Process) -> None:
        """Remove a subprocess after its pipes are closed."""
        self._subprocesses.discard(process)

    async def _close_subprocess(self, process: asyncio.subprocess.Process) -> None:
        """Terminate a subprocess and close pipes (avoids Windows Proactor warnings)."""
        if process.returncode is None:
            process.terminate()
            with suppress(asyncio.TimeoutError, ProcessLookupError):
                await asyncio.wait_for(process.wait(), timeout=5.0)
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                    with suppress(asyncio.TimeoutError, ProcessLookupError):
                        await asyncio.wait_for(process.wait(), timeout=5.0)

        self._close_process_pipes(process)

    def _close_process_pipes(self, process: asyncio.subprocess.Process) -> None:
        """Close subprocess pipe transports without using StreamReader.wait_closed()."""
        transport = process._transport
        if transport is None:
            return

        for stream in (process.stdout, process.stderr):
            if stream is not None:
                with suppress(Exception):
                    if not stream.at_eof():
                        stream.feed_eof()

        for fd in (1, 2):
            with suppress(Exception):
                pipe_transport = transport.get_pipe_transport(fd)
                if pipe_transport is not None and not pipe_transport.is_closing():
                    pipe_transport.close()

        if process.stdin is not None:
            with suppress(Exception):
                process.stdin.close()

        with suppress(Exception):
            if not transport.is_closing():
                transport.close()

    def _remove_active_process(self, process: asyncio.subprocess.Process) -> LogChannel | None:
        """Remove a process from the active list and return its log channel."""
        for index, active in enumerate(self.active_processes):
            if active.process is process:
                self.active_processes.pop(index)
                return active.channel
        return None

    async def _execute_process(
        self,
        cmd: list[str],
        *,
        channel: LogChannel,
        is_background: bool,
    ) -> None:
        """Execute subprocess asynchronously and route output to the log panel."""
        worker = get_current_worker()
        process: asyncio.subprocess.Process | None = None
        cancelled = False

        try:
            if cmd[0] == "codegenome":
                cmd = [sys.executable, "-m", "codegenome.cli"] + cmd[1:]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._track_subprocess(process)

            if is_background:
                self.active_processes.append(ActiveProcess(process=process, channel=channel))
                self.write_log(
                    channel,
                    f"[italic]Started background process (PID: {process.pid})[/italic]",
                )

            while True:
                if worker.is_cancelled:
                    cancelled = True
                    break

                if process.stdout is None:
                    break

                line = await process.stdout.readline()
                if not line:
                    break

                text = line.decode(errors="replace").rstrip()
                self.write_log(channel, text)

        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            self.write_log(channel, f"[bold red]Error:[/bold red] {exc}")
            if process is not None:
                removed_channel = self._remove_active_process(process)
                if removed_channel is not None:
                    self.write_log(
                        removed_channel,
                        f"[bold red]Process failed:[/bold red] {exc}",
                    )
        else:
            removed_channel = self._remove_active_process(process)
            if removed_channel is not None:
                channel = removed_channel

            if process is not None and not cancelled:
                status_color = "green" if process.returncode == 0 else "red"
                self.write_log(
                    channel,
                    f"[[bold {status_color}]Process exited with code {process.returncode}[/bold {status_color}]]",
                )
        finally:
            if process is not None:
                self._untrack_subprocess(process)
                self._remove_active_process(process)
                await asyncio.shield(self._close_subprocess(process))

    def stop_all_processes(self) -> None:
        """Stop all active background processes."""
        if not self.active_processes:
            self.write_log("general", "[yellow]No active background processes to stop.[/yellow]")
            self.focus_log_tab("general")
            return

        self.run_worker(
            self._stop_processes(list(self.active_processes)),
            exclusive=False,
        )

    async def _stop_processes(self, processes: list[ActiveProcess]) -> None:
        """Async cleanup for background subprocesses."""
        for active in processes:
            try:
                await self._close_subprocess(active.process)
                self._untrack_subprocess(active.process)
                self.write_log(
                    active.channel,
                    f"[yellow]Terminated process (PID: {active.process.pid})[/yellow]",
                )
            except Exception as exc:
                self.write_log(
                    active.channel,
                    f"[red]Failed to terminate PID {active.process.pid}: {exc}[/red]",
                )
        self.active_processes.clear()
        self.write_log("general", "[yellow]All background processes stopped.[/yellow]")
        self.focus_log_tab("general")

    async def _cleanup_subprocesses(self) -> None:
        """Close every tracked subprocess and its pipes."""
        for process in list(self._subprocesses):
            with suppress(Exception):
                await asyncio.shield(self._close_subprocess(process))
        self._subprocesses.clear()
        self.active_processes.clear()

    def action_quit_app(self) -> None:
        """Handle quit action from bindings."""
        self.quit_app()

    def quit_app(self) -> None:
        """Stop running subprocesses and exit the TUI."""
        self.run_worker(
            self._shutdown_and_exit(),
            exclusive=True,
            group="shutdown",
            exit_on_error=False,
        )

    async def _shutdown_and_exit(self) -> None:
        """Terminate subprocesses, close pipes, then exit cleanly."""
        if self._subprocesses:
            self.write_log("general", "[yellow]Stopping running commands...[/yellow]")

        await self._cleanup_subprocesses()
        self.exit()

    async def on_unmount(self) -> None:
        """Ensure subprocess pipes are closed when the app exits."""
        await self._cleanup_subprocesses()


def main() -> None:
    """Entry point for the CodeGenome TUI."""
    app = CodeGenomeTUI()
    app.run()


if __name__ == "__main__":
    main()
