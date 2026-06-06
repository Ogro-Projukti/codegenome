"""Background subprocess lifecycle management for the TUI.

The :class:`SubprocessController` owns the low-level, UI-independent mechanics of
tracking processes and tearing down their pipe transports cleanly (which avoids
noisy Windows Proactor warnings). The app delegates to it so the App class is no
longer responsible for raw transport plumbing.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from textual.worker import get_current_worker

from codegenome.tui.constants import LogChannel


@dataclass
class ActiveProcess:
    """Track a background subprocess and its log destination."""

    process: asyncio.subprocess.Process
    channel: LogChannel


def remove_active_process(
    active_processes: list[ActiveProcess],
    process: asyncio.subprocess.Process,
) -> LogChannel | None:
    """Remove a process from the active list and return its log channel."""
    for index, active in enumerate(active_processes):
        if active.process is process:
            active_processes.pop(index)
            return active.channel
    return None


async def execute_process(
    app: Any,
    controller: "SubprocessController",
    active_processes: list[ActiveProcess],
    cmd: list[str],
    *,
    channel: LogChannel,
    is_background: bool,
) -> None:
    """Execute a subprocess asynchronously and route output to the app log panel."""
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
        controller.track(process)

        if is_background:
            active_processes.append(ActiveProcess(process=process, channel=channel))
            app.write_log(
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
            app.write_log(channel, text)

    except asyncio.CancelledError:
        cancelled = True
        raise
    except Exception as exc:
        app.write_log(channel, f"[bold red]Error:[/bold red] {exc}")
        if process is not None:
            removed_channel = remove_active_process(active_processes, process)
            if removed_channel is not None:
                app.write_log(
                    removed_channel,
                    f"[bold red]Process failed:[/bold red] {exc}",
                )
    else:
        removed_channel = (
            remove_active_process(active_processes, process)
            if process is not None
            else None
        )
        if removed_channel is not None:
            channel = removed_channel

        if process is not None and not cancelled:
            status_color = "green" if process.returncode == 0 else "red"
            app.write_log(
                channel,
                f"[[bold {status_color}]Process exited with code {process.returncode}[/bold {status_color}]]",
            )
            if process.returncode == 0 and channel in ("analyze", "evolve"):
                app.refresh_dashboard_summary()
    finally:
        if process is not None:
            controller.untrack(process)
            remove_active_process(active_processes, process)
            await asyncio.shield(controller.close(process))


class SubprocessController:
    """Track background subprocesses and close them and their pipes safely."""

    def __init__(self) -> None:
        self._subprocesses: set[asyncio.subprocess.Process] = set()

    @property
    def tracked(self) -> set[asyncio.subprocess.Process]:
        """Return the set of currently tracked subprocesses."""
        return self._subprocesses

    def track(self, process: asyncio.subprocess.Process) -> None:
        """Register a subprocess so shutdown can close its pipes."""
        self._subprocesses.add(process)

    def untrack(self, process: asyncio.subprocess.Process) -> None:
        """Remove a subprocess after its pipes are closed."""
        self._subprocesses.discard(process)

    async def close(self, process: asyncio.subprocess.Process) -> None:
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

        self._close_pipes(process)

    def _close_pipes(self, process: asyncio.subprocess.Process) -> None:
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

    async def cleanup_all(self) -> None:
        """Close every tracked subprocess and its pipes."""
        for process in list(self._subprocesses):
            with suppress(Exception):
                await asyncio.shield(self.close(process))
        self._subprocesses.clear()
