"""Unit tests for CodeGenome TUI command wiring."""

from __future__ import annotations

import asyncio

from rich.segment import Segment

from textual import events
from textual.geometry import Offset
from textual.selection import Selection
from textual.strip import Strip

from codegenome.tui import (
    MEMORY_PRESETS,
    ActiveProcess,
    CodeGenomeTUI,
    MemoryModeSettings,
    ReadOnlyRichLog,
    analyze_mode_cli_args,
    evolve_mode_cli_args,
    format_memory_mode_preview,
    mcp_mode_cli_args,
    parse_max_working_files,
    working_set_cli_args,
)


def test_working_set_cli_args_empty_when_disabled() -> None:
    assert working_set_cli_args(memory_bounded=False, max_working_files=64) == []


def test_working_set_cli_args_includes_flags_when_enabled() -> None:
    assert working_set_cli_args(memory_bounded=True, max_working_files=32) == [
        "--memory-bounded",
        "--max-working-files",
        "32",
    ]


def test_mcp_and_evolve_memory_modes_are_independent() -> None:
    """Full MCP with bounded Live Evolve graph (user's mixed mode)."""
    settings = MemoryModeSettings(
        mcp_memory_bounded=False,
        evolve_memory_bounded=True,
        max_working_files=48,
    )
    assert mcp_mode_cli_args(settings) == []
    assert evolve_mode_cli_args(settings) == [
        "--memory-bounded",
        "--max-working-files",
        "48",
    ]


def test_mcp_mode_cli_args_bounded_without_working_set_limit() -> None:
    settings = MemoryModeSettings(mcp_memory_bounded=True)
    assert mcp_mode_cli_args(settings) == ["--memory-bounded"]


def test_mcp_mode_cli_args_adds_full_analysis_flag() -> None:
    settings = MemoryModeSettings(
        mcp_memory_bounded=True,
        mcp_full_analysis_on_demand=True,
    )
    assert mcp_mode_cli_args(settings) == [
        "--memory-bounded",
        "--full-analysis-on-demand",
    ]


def test_mcp_mode_cli_args_ignores_full_analysis_when_not_bounded() -> None:
    settings = MemoryModeSettings(
        mcp_memory_bounded=False,
        mcp_full_analysis_on_demand=True,
    )
    assert mcp_mode_cli_args(settings) == []


def test_analyze_mode_cli_args_respects_analyze_toggle_only() -> None:
    settings = MemoryModeSettings(
        analyze_memory_bounded=True,
        evolve_memory_bounded=False,
        max_working_files=16,
    )
    assert analyze_mode_cli_args(settings) == [
        "--memory-bounded",
        "--max-working-files",
        "16",
    ]
    assert evolve_mode_cli_args(settings) == []


def test_memory_presets_include_mixed_mode() -> None:
    preset = MEMORY_PRESETS["full_mcp_bounded_evolve"]
    assert preset.mcp_memory_bounded is False
    assert preset.evolve_memory_bounded is True
    assert evolve_mode_cli_args(preset)
    assert mcp_mode_cli_args(preset) == []


def test_format_memory_mode_preview_shows_mixed_modes() -> None:
    preview = format_memory_mode_preview(
        MemoryModeSettings(
            mcp_memory_bounded=False,
            evolve_memory_bounded=True,
            analyze_memory_bounded=False,
            max_working_files=48,
        )
    )
    assert "MCP" in preview
    assert "(full graph)" in preview
    assert "--memory-bounded" in preview
    assert "48" in preview


def test_parse_max_working_files_clamps_and_defaults() -> None:
    assert parse_max_working_files("128") == 128
    assert parse_max_working_files("0") == 1
    assert parse_max_working_files("bad", default=64) == 64


def test_bindings_use_ctrl_c_for_copy_not_quit() -> None:
    binding_map = {key: action for key, action, _description in CodeGenomeTUI.BINDINGS}
    assert binding_map["ctrl+c"] == "copy_log_text"
    assert binding_map["ctrl+q"] == "quit_app"


def test_read_only_rich_log_get_selection_returns_plain_text() -> None:
    log = ReadOnlyRichLog()
    log.lines = [
        Strip([Segment("alpha")], 5),
        Strip([Segment("beta")], 4),
    ]
    selection = Selection(Offset(0, 0), Offset(4, 1))
    result = log.get_selection(selection)
    assert result is not None
    text, ending = result
    assert text == "alpha\nbeta"
    assert ending == "\n"


def test_read_only_rich_log_blocks_printable_keys() -> None:
    log = ReadOnlyRichLog()
    event = events.Key(key="x", character="x")
    log.on_key(event)
    assert event._stop_propagation is True


def test_command_button_ids_include_channel_specific_stop_buttons() -> None:
    assert "btn-stop-mcp" in CodeGenomeTUI.COMMAND_BUTTON_IDS
    assert "btn-stop-evolve" in CodeGenomeTUI.COMMAND_BUTTON_IDS
    assert "btn-stop" not in CodeGenomeTUI.COMMAND_BUTTON_IDS


def test_stop_processes_for_channel_schedules_only_matching_processes() -> None:
    app = CodeGenomeTUI()
    app.active_processes = [
        ActiveProcess(process=object(), channel="mcp"),
        ActiveProcess(process=object(), channel="evolve"),
    ]

    captured: dict[str, object] = {}

    async def fake_stop_processes(processes, *, completion_message: str):  # type: ignore[no-untyped-def]
        captured["processes"] = processes
        captured["message"] = completion_message

    def fake_run_worker(coro, *, exclusive: bool):  # type: ignore[no-untyped-def]
        captured["exclusive"] = exclusive
        asyncio.run(coro)

    app._stop_processes = fake_stop_processes  # type: ignore[method-assign]
    app.run_worker = fake_run_worker  # type: ignore[method-assign]

    app.stop_processes_for_channel("mcp", "MCP server")

    matching = captured["processes"]
    assert isinstance(matching, list)
    assert len(matching) == 1
    assert matching[0].channel == "mcp"
    assert captured["message"] == "[yellow]MCP server processes stopped.[/yellow]"
    assert captured["exclusive"] is False


def test_stop_processes_for_channel_logs_when_no_matching_processes() -> None:
    app = CodeGenomeTUI()
    app.active_processes = [ActiveProcess(process=object(), channel="evolve")]

    logs: list[tuple[str, str]] = []
    focused: list[str] = []

    def fake_write_log(channel: str, message: str) -> None:
        logs.append((channel, message))

    def fake_focus(channel: str) -> None:
        focused.append(channel)

    app.write_log = fake_write_log  # type: ignore[method-assign]
    app.focus_log_tab = fake_focus  # type: ignore[method-assign]

    app.stop_processes_for_channel("mcp", "MCP server")

    assert logs == [("mcp", "[yellow]No active MCP server process to stop.[/yellow]")]
    assert focused == ["mcp"]


def test_copy_panel_output_copies_text_to_clipboard() -> None:
    app = CodeGenomeTUI()
    log = ReadOnlyRichLog()
    log.lines = [
        Strip([Segment("line 1")], 6),
        Strip([Segment("line 2")], 6),
    ]

    copied: list[str] = []
    notifications: list[str] = []

    def fake_copy_to_clipboard(text: str) -> None:
        copied.append(text)

    def fake_notify(message: str, *, severity: str = "information") -> None:
        notifications.append(message)

    app.copy_to_clipboard = fake_copy_to_clipboard  # type: ignore[method-assign]
    app.notify = fake_notify  # type: ignore[method-assign]

    app.copy_panel_output(log, "Test Panel")

    assert copied == ["line 1\nline 2"]
    assert notifications == ["Copied Test Panel output to clipboard!"]


def test_copy_panel_output_notifies_if_empty() -> None:
    app = CodeGenomeTUI()
    log = ReadOnlyRichLog()
    log.lines = []

    copied: list[str] = []
    notifications: list[str] = []

    def fake_copy_to_clipboard(text: str) -> None:
        copied.append(text)

    def fake_notify(message: str, *, severity: str = "information") -> None:
        notifications.append(message)

    app.copy_to_clipboard = fake_copy_to_clipboard  # type: ignore[method-assign]
    app.notify = fake_notify  # type: ignore[method-assign]

    app.copy_panel_output(log, "Test Panel")

    assert not copied
    assert notifications == ["No content to copy in Test Panel."]
