"""Textual application class for CodeGenome.

``CodeGenomeTUI`` orchestrates the dashboard UI. Cohesive concerns have been
extracted into sibling modules: CSS (``styles``), the read-only log widget
(``widgets``), memory-mode helpers (``memory``), and subprocess plumbing
(``process``). In-process operations (analyze, export, rules) run through the
shared :class:`~codegenome.service.CodeGenomeService` instead of shelling out to
``codegenome ...``; only the MCP and live-evolve servers stay as subprocesses.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from functools import partial
from pathlib import Path

from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)
from textual.worker import Worker, WorkerState, get_current_worker

from codegenome.service import CodeGenomeService
from codegenome.tui.constants import (
    LogChannel,
    PAGE_INFO,
    PAGE_MAIN,
    PAGE_MEMORY,
    PAGE_SET,
)
from codegenome.tui.memory import (
    MEMORY_PRESETS,
    MEMORY_SWITCH_LABELS,
    MemoryModeSettings,
    analyze_mode_cli_args,
    evolve_mode_cli_args,
    format_memory_mode_preview,
    mcp_mode_cli_args,
    parse_max_working_files,
)
from codegenome.tui.process import ActiveProcess, SubprocessController
from codegenome.tui.styles import APP_CSS
from codegenome.tui.widgets import ReadOnlyRichLog
from codegenome.workspace_info import (
    WorkspaceInfo,
    collect_workspace_info,
    format_dashboard_summary,
    format_gitignore_files_panel,
    format_tracked_extensions_panel,
    format_tracked_folders_panel,
    load_graph_live_summary,
)


class CodeGenomeTUI(App):
    """A Textual app for managing CodeGenome."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._proc = SubprocessController()
        self.active_processes: list[ActiveProcess] = []
        self._service = CodeGenomeService()

    BINDINGS = [
        ("ctrl+q", "quit_app", "Quit"),
        ("ctrl+c", "copy_log_text", "Copy"),
    ]

    CSS = APP_CSS

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
        "btn-mcp-local",
        "btn-mcp-lan",
        "btn-evolve-local",
        "btn-evolve-lan",
        "btn-stop-mcp",
        "btn-stop-evolve",
    )

    MEMORY_SETUP_BUTTON_IDS: tuple[str, ...] = (
        "btn-preset-defaults",
        "btn-preset-all-bounded",
        "btn-preset-full-mcp-bounded-evolve",
        "btn-preset-bounded-mcp-full-analysis",
        "btn-memory-refresh",
        "btn-copy-memory-console",
        "btn-back-to-main",
    )

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        with ContentSwitcher(initial=PAGE_SET):
            with Container(id=PAGE_SET, classes="page"):
                with Vertical(classes="set-workspace-panel"):
                    yield Label("[bold]Set Workspace[/bold]")
                    yield Label("Enter the path to your project root:")
                    yield Input(
                        value=".", id="workspace-input", placeholder="Enter path to workspace..."
                    )
                    with Horizontal(classes="page-actions"):
                        yield Button("Set", id="btn-set-workspace", variant="primary")
                        yield Button("Quit", id="btn-quit", variant="default")

            with Container(id=PAGE_INFO, classes="page"):
                yield Label("[bold]Workspace Scan Results[/bold]")
                yield Static(id="workspace-scan-status", markup=True)
                with Horizontal(id="workspace-info-panels"):
                    with Vertical(classes="info-panel"):
                        with Horizontal(classes="panel-header"):
                            yield Label("[bold cyan]Tracked Folders[/bold cyan]")
                            yield Button(
                                "Copy", id="btn-copy-folders", variant="default", classes="copy-btn"
                            )
                        yield ReadOnlyRichLog(
                            id="info-folders", markup=True, highlight=False, wrap=True
                        )
                    with Vertical(classes="info-panel"):
                        with Horizontal(classes="panel-header"):
                            yield Label("[bold cyan]File Extensions[/bold cyan]")
                            yield Button(
                                "Copy",
                                id="btn-copy-extensions",
                                variant="default",
                                classes="copy-btn",
                            )
                        yield ReadOnlyRichLog(
                            id="info-extensions", markup=True, highlight=False, wrap=True
                        )
                    with Vertical(classes="info-panel"):
                        with Horizontal(classes="panel-header"):
                            yield Label("[bold cyan].gitignore Files[/bold cyan]")
                            yield Button(
                                "Copy",
                                id="btn-copy-gitignore",
                                variant="default",
                                classes="copy-btn",
                            )
                        yield ReadOnlyRichLog(
                            id="info-gitignore", markup=True, highlight=False, wrap=True
                        )
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
                        yield Button(
                            "Start MCP HTTP (Local)", id="btn-mcp-local", variant="success"
                        )
                        yield Button("Start MCP HTTP (LAN)", id="btn-mcp-lan", variant="warning")
                    with Horizontal(classes="command-row"):
                        yield Button(
                            "Live Evolve (Local)", id="btn-evolve-local", variant="success"
                        )
                        yield Button("Live Evolve (LAN)", id="btn-evolve-lan", variant="success")

                with Container(id="log-container"):
                    with TabbedContent(initial="tab-analyze"):
                        with TabPane("Analyze", id="tab-analyze"):
                            with Vertical(classes="log-pane"):
                                with Horizontal(classes="panel-header"):
                                    yield Label("[bold cyan]Analyze Log[/bold cyan]")
                                    yield Button(
                                        "Copy",
                                        id="btn-copy-analyze",
                                        variant="default",
                                        classes="copy-btn",
                                    )
                                yield ReadOnlyRichLog(id="log-analyze", markup=True, highlight=True)
                        with TabPane("MCP Server", id="tab-mcp"):
                            with Vertical(classes="log-pane"):
                                with Horizontal(classes="panel-header"):
                                    yield Label("[bold cyan]MCP Server Log[/bold cyan]")
                                    yield Button(
                                        "Copy",
                                        id="btn-copy-mcp",
                                        variant="default",
                                        classes="copy-btn",
                                    )
                                yield ReadOnlyRichLog(id="log-mcp", markup=True, highlight=True)
                        with TabPane("Live Evolve", id="tab-evolve"):
                            with Vertical(classes="log-pane"):
                                with Horizontal(classes="panel-header"):
                                    yield Label("[bold cyan]Live Evolve Log[/bold cyan]")
                                    yield Button(
                                        "Copy",
                                        id="btn-copy-evolve",
                                        variant="default",
                                        classes="copy-btn",
                                    )
                                yield ReadOnlyRichLog(id="log-evolve", markup=True, highlight=True)
                        with TabPane("General", id="tab-general"):
                            with Vertical(classes="log-pane"):
                                with Horizontal(classes="panel-header"):
                                    yield Label("[bold cyan]General Log[/bold cyan]")
                                    yield Button(
                                        "Copy",
                                        id="btn-copy-general",
                                        variant="default",
                                        classes="copy-btn",
                                    )
                                yield ReadOnlyRichLog(id="log-general", markup=True, highlight=True)

                with Horizontal(classes="page-actions"):
                    yield Button("Stop MCP Server", id="btn-stop-mcp", variant="error")
                    yield Button("Stop Live Evolve", id="btn-stop-evolve", variant="error")
                    yield Button(
                        "Memory Setup Console",
                        id="btn-memory-setup",
                        variant="warning",
                    )
                    yield Button("Quit", id="btn-quit-main", variant="default")

            with Container(id=PAGE_MEMORY, classes="page"):
                with Horizontal(id="memory-setup-topbar"):
                    with Horizontal(classes="memory-topbar-presets"):
                        yield Button("Defaults", id="btn-preset-defaults", variant="default")
                        yield Button(
                            "All Bounded",
                            id="btn-preset-all-bounded",
                            variant="default",
                        )
                        yield Button(
                            "Full MCP + Bounded Graph",
                            id="btn-preset-full-mcp-bounded-evolve",
                            variant="default",
                        )
                        yield Button(
                            "Bounded MCP + Full Analysis",
                            id="btn-preset-bounded-mcp-full-analysis",
                            variant="default",
                        )
                        yield Button(
                            "Refresh Preview",
                            id="btn-memory-refresh",
                            variant="default",
                        )
                    yield Button("Back to Dashboard", id="btn-back-to-main", variant="success")
                yield Label("[bold]Memory Setup Console[/bold]")
                yield Static(
                    "Control per-service RAM usage. Changes apply immediately to the next "
                    "Analyze, MCP, or Live Evolve command.",
                    classes="memory-mode-hint",
                )
                with Horizontal(id="memory-setup-columns"):
                    with Vertical(id="memory-setup-left", classes="memory-column"):
                        yield Label("[bold]Controls[/bold]", classes="memory-column-title")
                        with Container(id="memory-setup-controls"):
                            with Horizontal(classes="memory-setup-option"):
                                yield Switch(value=False, id="switch-mcp-memory-bounded")
                                yield Label("MCP server: memory-bounded")
                            with Horizontal(classes="memory-setup-option"):
                                yield Switch(value=False, id="switch-evolve-memory-bounded")
                                yield Label("Live Evolve / graph: memory-bounded")
                            with Horizontal(classes="memory-setup-option"):
                                yield Switch(value=False, id="switch-analyze-memory-bounded")
                                yield Label("Analyze: memory-bounded")
                            with Horizontal(classes="memory-setup-option"):
                                yield Label("Max working files (Analyze / Evolve):")
                                yield Input(
                                    value="64",
                                    id="input-max-working-files",
                                    placeholder="64",
                                    disabled=True,
                                )
                            with Horizontal(classes="memory-setup-option"):
                                yield Switch(
                                    value=False,
                                    id="switch-mcp-full-analysis",
                                    disabled=True,
                                )
                                yield Label(
                                    "MCP: full-graph analysis on demand (bounded MCP only)"
                                )
                            yield Label("[bold]Command preview[/bold]", classes="memory-column-title")
                            yield Static(id="memory-setup-summary", markup=True)
                    with Vertical(id="memory-setup-right", classes="memory-column"):
                        with Horizontal(classes="memory-console-header"):
                            yield Label("[bold cyan]Settings console[/bold cyan]")
                            yield Button(
                                "Copy",
                                id="btn-copy-memory-console",
                                variant="default",
                                classes="copy-btn",
                            )
                        yield ReadOnlyRichLog(
                            id="memory-setup-console",
                            markup=True,
                            highlight=False,
                            wrap=True,
                        )

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts. Initializes widgets and state."""
        self._workspace_poll_timer = None
        self.pages = self.query_one(ContentSwitcher)
        self.workspace_input = self.query_one("#workspace-input", Input)
        self.workspace_scan_status = self.query_one("#workspace-scan-status", Static)
        self.info_folders_log = self.query_one("#info-folders", ReadOnlyRichLog)
        self.info_extensions_log = self.query_one("#info-extensions", ReadOnlyRichLog)
        self.info_gitignore_log = self.query_one("#info-gitignore", ReadOnlyRichLog)
        self.workspace_summary = self.query_one("#workspace-summary", Static)
        self.continue_button = self.query_one("#btn-continue", Button)
        self.set_workspace_button = self.query_one("#btn-set-workspace", Button)
        self.log_tabs = self.query_one(TabbedContent)
        self.log_widgets: dict[LogChannel, ReadOnlyRichLog] = {
            channel: self.query_one(f"#{log_id}", ReadOnlyRichLog)
            for channel, log_id in self.LOG_IDS.items()
        }
        self.command_buttons: dict[str, Button] = {
            button_id: self.query_one(f"#{button_id}", Button)
            for button_id in self.COMMAND_BUTTON_IDS
        }
        self.mcp_memory_bounded_switch = self.query_one("#switch-mcp-memory-bounded", Switch)
        self.evolve_memory_bounded_switch = self.query_one(
            "#switch-evolve-memory-bounded", Switch
        )
        self.analyze_memory_bounded_switch = self.query_one(
            "#switch-analyze-memory-bounded", Switch
        )
        self.mcp_full_analysis_switch = self.query_one("#switch-mcp-full-analysis", Switch)
        self.max_working_files_input = self.query_one("#input-max-working-files", Input)
        self.memory_setup_summary = self.query_one("#memory-setup-summary", Static)
        self.memory_setup_console = self.query_one("#memory-setup-console", ReadOnlyRichLog)
        self._workspace_path: str | None = None
        self._pending_workspace_info: WorkspaceInfo | None = None
        self._main_initialized = False
        self._memory_console_initialized = False

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
                f"[bold]Root:[/bold] {info.root}  [bold red]Error:[/bold red] {info.error}"
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
        if (
            getattr(self, "_workspace_path", None)
            and getattr(self, "pages", None)
            and self.pages.current == PAGE_MAIN
        ):
            self.run_worker(
                self._do_background_refresh(self._workspace_path),
                exclusive=True,
                group="workspace-info-bg",
            )

    def refresh_dashboard_summary(self) -> None:
        """Update the dashboard header with workspace tracking and graph status."""
        if self._workspace_path is None:
            return
        root = Path(self._workspace_path)
        info = self._pending_workspace_info
        if info is None or info.root != str(root):
            info = collect_workspace_info(root)
        graph = load_graph_live_summary(root)
        self.workspace_summary.update(format_dashboard_summary(info, graph))

    async def _do_background_refresh(self, path: str) -> None:
        """Fetch updated info without blocking or changing UI state heavily."""
        worker = get_current_worker()
        info, graph = await asyncio.gather(
            asyncio.to_thread(collect_workspace_info, Path(path)),
            asyncio.to_thread(load_graph_live_summary, Path(path)),
        )
        if worker.is_cancelled:
            return

        self.workspace_summary.update(format_dashboard_summary(info, graph))

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
        self.refresh_dashboard_summary()
        self.show_page(PAGE_MAIN)

        if getattr(self, "_workspace_poll_timer", None) is None:
            self._workspace_poll_timer = self.set_interval(
                5.0, self.background_refresh_workspace_info
            )

        if not self._main_initialized:
            self._main_initialized = True
            self.write_log("general", "[bold green]CodeGenome TUI initialized.[/bold green]")
            self.write_log(
                "general",
                "Use Analyze, MCP, or Live Evolve from the command buttons. "
                "Open Memory Setup Console to configure per-service RAM usage.",
            )
            self.refresh_memory_setup_preview()
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

    def copy_panel_output(self, log_widget: ReadOnlyRichLog, panel_name: str) -> None:
        """Get the text from a ReadOnlyRichLog and copy it to clipboard."""
        text = "\n".join(line.text for line in log_widget.lines)
        if not text:
            self.notify(f"No content to copy in {panel_name}.", severity="warning")
            return
        self.copy_to_clipboard(text)
        self.notify(f"Copied {panel_name} output to clipboard!")

    def get_memory_mode_settings(self) -> MemoryModeSettings:
        """Read the current memory mode controls from the dashboard."""
        return MemoryModeSettings(
            mcp_memory_bounded=bool(self.mcp_memory_bounded_switch.value),
            evolve_memory_bounded=bool(self.evolve_memory_bounded_switch.value),
            analyze_memory_bounded=bool(self.analyze_memory_bounded_switch.value),
            max_working_files=parse_max_working_files(self.max_working_files_input.value),
            mcp_full_analysis_on_demand=bool(self.mcp_full_analysis_switch.value),
        )

    def log_memory_console(self, message: str) -> None:
        """Append a timestamped line to the Memory Setup console."""
        stamp = datetime.now().strftime("%H:%M:%S")
        self.memory_setup_console.write(f"[dim]{stamp}[/dim]  {message}")

    def apply_memory_settings(self, settings: MemoryModeSettings) -> None:
        """Push settings into the Memory Setup controls."""
        self._suppress_memory_switch_log = True
        try:
            self.mcp_memory_bounded_switch.value = settings.mcp_memory_bounded
            self.evolve_memory_bounded_switch.value = settings.evolve_memory_bounded
            self.analyze_memory_bounded_switch.value = settings.analyze_memory_bounded
            self.mcp_full_analysis_switch.value = settings.mcp_full_analysis_on_demand
            self.max_working_files_input.value = str(settings.max_working_files)
            self.update_memory_mode_controls()
        finally:
            self._suppress_memory_switch_log = False

    def refresh_memory_setup_preview(self) -> None:
        """Update the Memory Setup panel command preview."""
        self.memory_setup_summary.update(
            format_memory_mode_preview(self.get_memory_mode_settings())
        )

    def show_memory_setup_console(self) -> None:
        """Open the dedicated Memory Setup console page."""
        self.show_page(PAGE_MEMORY)
        if not self._memory_console_initialized:
            self._memory_console_initialized = True
            self.memory_setup_console.clear()
            self.log_memory_console(
                "[bold green]Memory Setup Console ready.[/bold green] "
                "Use switches, presets, or max-files input below."
            )
            self.log_memory_console(
                "Tip: choose [cyan]Full MCP + Bounded Graph[/cyan] for full MCP RAM "
                "with a bounded live graph."
            )
        self.refresh_memory_setup_preview()
        self.log_memory_console("Current settings loaded. Adjust controls to update.")

    def update_memory_mode_controls(self) -> None:
        """Enable or disable memory-bounded sub-options."""
        settings = self.get_memory_mode_settings()
        uses_working_set = (
            settings.analyze_memory_bounded or settings.evolve_memory_bounded
        )
        self.max_working_files_input.disabled = not uses_working_set
        self.mcp_full_analysis_switch.disabled = not settings.mcp_memory_bounded
        if not settings.mcp_memory_bounded:
            self.mcp_full_analysis_switch.value = False
        self.refresh_memory_setup_preview()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Keep dependent memory mode controls in sync."""
        switch_id = event.switch.id or ""
        if switch_id in MEMORY_SWITCH_LABELS:
            if getattr(self, "_suppress_memory_switch_log", False):
                self.update_memory_mode_controls()
                return
            label = MEMORY_SWITCH_LABELS[switch_id]
            state = "enabled" if event.value else "disabled"
            self.update_memory_mode_controls()
            if self.pages.current == PAGE_MEMORY:
                self.log_memory_console(f"{label}: [cyan]{state}[/cyan]")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Refresh preview when working-set limits change."""
        if event.input.id == "input-max-working-files":
            self.refresh_memory_setup_preview()
            if self.pages.current == PAGE_MEMORY:
                value = parse_max_working_files(event.value)
                self.log_memory_console(
                    f"Max working files: [cyan]{value}[/cyan]"
                )

    def _handle_memory_setup_button(self, button_id: str) -> None:
        """Handle buttons on the Memory Setup console page."""
        preset_map = {
            "btn-preset-defaults": ("default", "Defaults"),
            "btn-preset-all-bounded": ("all_bounded", "All Bounded"),
            "btn-preset-full-mcp-bounded-evolve": (
                "full_mcp_bounded_evolve",
                "Full MCP + Bounded Graph",
            ),
            "btn-preset-bounded-mcp-full-analysis": (
                "bounded_mcp_full_analysis",
                "Bounded MCP + Full Analysis",
            ),
        }
        if button_id in preset_map:
            preset_key, preset_label = preset_map[button_id]
            self.apply_memory_settings(MEMORY_PRESETS[preset_key])
            self.log_memory_console(f"Applied preset: [bold]{preset_label}[/bold]")
            self.notify(f"Memory preset applied: {preset_label}")
            return
        if button_id == "btn-memory-refresh":
            self.refresh_memory_setup_preview()
            self.log_memory_console("Preview refreshed.")
            settings = self.get_memory_mode_settings()
            self.log_memory_console(
                f"Analyze → {'bounded' if settings.analyze_memory_bounded else 'full graph'}; "
                f"MCP → {'bounded' if settings.mcp_memory_bounded else 'full graph'}; "
                f"Evolve → {'bounded' if settings.evolve_memory_bounded else 'full graph'}"
            )
            return
        if button_id == "btn-back-to-main":
            self.show_page(PAGE_MAIN)
            self.log_memory_console("Returned to dashboard. Settings are saved for next commands.")
            self.write_log(
                "general",
                "[cyan]Memory settings updated.[/cyan] "
                "Run Analyze, MCP, or Live Evolve to use them.",
            )
            self.focus_log_tab("general")

    def _copy_button_targets(self) -> dict[str, tuple[ReadOnlyRichLog, str]]:
        """Map copy-button ids to their (widget, panel-name) targets."""
        return {
            "btn-copy-folders": (self.info_folders_log, "Tracked Folders"),
            "btn-copy-extensions": (self.info_extensions_log, "File Extensions"),
            "btn-copy-gitignore": (self.info_gitignore_log, ".gitignore Files"),
            "btn-copy-analyze": (self.log_widgets["analyze"], "Analyze Log"),
            "btn-copy-mcp": (self.log_widgets["mcp"], "MCP Server Log"),
            "btn-copy-evolve": (self.log_widgets["evolve"], "Live Evolve Log"),
            "btn-copy-general": (self.log_widgets["general"], "General Log"),
            "btn-copy-memory-console": (self.memory_setup_console, "Memory Setup Console"),
        }

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle command button presses."""
        button_id = event.button.id
        if button_id in self.COMMAND_BUTTON_IDS and event.button.disabled:
            return

        copy_targets = self._copy_button_targets()
        if button_id in copy_targets:
            self.copy_panel_output(*copy_targets[button_id])
            return

        if button_id in self.MEMORY_SETUP_BUTTON_IDS:
            self._handle_memory_setup_button(button_id)
            return

        navigation = {
            "btn-set-workspace": self.refresh_workspace_info,
            "btn-back-to-set": lambda: self.show_page(PAGE_SET),
            "btn-continue": self.enter_main_dashboard,
            "btn-change-workspace": lambda: self.show_page(PAGE_SET),
            "btn-memory-setup": self.show_memory_setup_console,
        }
        if button_id in navigation:
            navigation[button_id]()
            return

        if button_id in ("btn-quit", "btn-quit-main"):
            self.quit_app()
            return

        self._dispatch_command_button(
            button_id,
            self.get_workspace_path(),
            self.get_memory_mode_settings(),
        )

    def _dispatch_command_button(
        self,
        button_id: str,
        workspace: str,
        memory_settings: MemoryModeSettings,
    ) -> None:
        """Run the engine operation behind a dashboard command button."""
        if button_id == "btn-analyze":
            self.run_service_task(
                "Analyze",
                "analyze",
                partial(self._analyze_task, workspace, memory_settings),
                refresh_summary=True,
            )
        elif button_id == "btn-export":
            self.run_service_task(
                "Export (json)",
                "general",
                partial(self._export_task, workspace),
            )
        elif button_id == "btn-rules":
            self.run_service_task(
                "Generate AI Rules",
                "general",
                partial(self._rules_task, workspace),
            )
        elif button_id == "btn-mcp-local":
            self.run_command(
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
            self.run_command(
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
            self.run_command(
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
            self.run_command(
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
            self.stop_processes_for_channel("mcp", "MCP server")
        elif button_id == "btn-stop-evolve":
            self.stop_processes_for_channel("evolve", "Live Evolve")

    # -- In-process service tasks -----------------------------------------

    def _analyze_task(
        self,
        workspace: str,
        settings: MemoryModeSettings,
        emit,
    ) -> None:
        """Run an in-process analyze and report node/edge totals."""
        result = self._service.analyze(
            workspace,
            memory_bounded=settings.analyze_memory_bounded,
            max_working_files=settings.max_working_files,
            on_progress=emit,
        )
        emit(
            f"Build complete: {result.graph.number_of_nodes()} nodes, "
            f"{result.graph.number_of_edges()} edges."
        )

    def _export_task(self, workspace: str, emit) -> None:
        """Run an in-process JSON export and report output paths."""
        result_paths = self._service.export(workspace, ["json"], on_progress=emit)
        for fmt, out_path in result_paths.items():
            emit(f"Exported {fmt} → {out_path}")

    def _rules_task(self, workspace: str, emit) -> None:
        """Generate AI rule files in-process and report output paths."""
        results = self._service.generate_rules(workspace, clients=["all"], on_progress=emit)
        if not results:
            emit("No clients selected or found.")
            return
        for label, out_path in results:
            emit(f"Generated {label} rules at: {out_path}")

    def run_service_task(
        self,
        label: str,
        channel: LogChannel,
        func,
        *,
        refresh_summary: bool = False,
    ) -> None:
        """Run a service callable in a thread worker, streaming output to a panel."""
        self.focus_log_tab(channel)
        self.write_log(channel, f"\n[bold blue]> {label}[/bold blue]")
        self.run_worker(
            partial(self._execute_service_task, label, channel, func, refresh_summary),
            thread=True,
            exclusive=False,
            exit_on_error=False,
            group="service",
        )

    def _execute_service_task(
        self,
        label: str,
        channel: LogChannel,
        func,
        refresh_summary: bool,
    ) -> None:
        """Worker body: invoke ``func`` and marshal log updates to the UI thread."""

        def emit(message: str) -> None:
            self.call_from_thread(self.write_log, channel, message)

        try:
            func(emit)
        except Exception as exc:  # noqa: BLE001 - surface failures in the log panel
            self.call_from_thread(
                self.write_log, channel, f"[bold red]{label} failed:[/bold red] {exc}"
            )
            return

        self.call_from_thread(
            self.write_log, channel, f"[[bold green]{label} complete[/bold green]]"
        )
        if refresh_summary:
            self.call_from_thread(self.refresh_dashboard_summary)

    # -- Background subprocesses (servers) --------------------------------

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
        self._proc.track(process)

    def _untrack_subprocess(self, process: asyncio.subprocess.Process) -> None:
        """Remove a subprocess after its pipes are closed."""
        self._proc.untrack(process)

    async def _close_subprocess(self, process: asyncio.subprocess.Process) -> None:
        """Terminate a subprocess and close its pipes."""
        await self._proc.close(process)

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
                if process.returncode == 0 and channel in ("analyze", "evolve"):
                    self.refresh_dashboard_summary()
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
            self._stop_processes(
                list(self.active_processes),
                completion_message="[yellow]All background processes stopped.[/yellow]",
            ),
            exclusive=False,
        )

    def stop_processes_for_channel(self, channel: LogChannel, label: str) -> None:
        """Stop active background processes for a specific log channel."""
        matching = [active for active in self.active_processes if active.channel == channel]
        if not matching:
            self.write_log(channel, f"[yellow]No active {label} process to stop.[/yellow]")
            self.focus_log_tab(channel)
            return

        self.run_worker(
            self._stop_processes(
                matching,
                completion_message=f"[yellow]{label} processes stopped.[/yellow]",
            ),
            exclusive=False,
        )

    async def _stop_processes(
        self,
        processes: list[ActiveProcess],
        *,
        completion_message: str,
    ) -> None:
        """Async cleanup for background subprocesses."""
        for active in processes:
            try:
                await self._close_subprocess(active.process)
                self._untrack_subprocess(active.process)
                self._remove_active_process(active.process)
                self.write_log(
                    active.channel,
                    f"[yellow]Terminated process (PID: {active.process.pid})[/yellow]",
                )
            except Exception as exc:
                self.write_log(
                    active.channel,
                    f"[red]Failed to terminate PID {active.process.pid}: {exc}[/red]",
                )
        self.write_log("general", completion_message)
        self.focus_log_tab("general")

    async def _cleanup_subprocesses(self) -> None:
        """Close every tracked subprocess and its pipes."""
        await self._proc.cleanup_all()
        if hasattr(self, "active_processes"):
            self.active_processes.clear()

    def action_copy_log_text(self) -> None:
        """Copy selected log text to the clipboard."""
        try:
            self.screen.action_copy_text()
        except SkipAction:
            self.notify(
                "Select text in a log panel first, then press Ctrl+C.",
                severity="warning",
            )

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
        if self._proc.tracked:
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
