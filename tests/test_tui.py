"""Unit tests for CodeGenome TUI command wiring."""

from __future__ import annotations

import asyncio

from rich.segment import Segment

from textual import events
from textual.geometry import Offset
from textual.selection import Selection
from textual.strip import Strip

from codegenome.tui import ActiveProcess, CodeGenomeTUI, ReadOnlyRichLog


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
