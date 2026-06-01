"""Unit tests for CodeGenome TUI command wiring."""

from __future__ import annotations

import asyncio

from codegenome.tui import ActiveProcess, CodeGenomeTUI


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
