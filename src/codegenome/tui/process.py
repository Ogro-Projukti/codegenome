"""Background subprocess lifecycle management for the TUI.

The :class:`SubprocessController` owns the low-level, UI-independent mechanics of
tracking processes and tearing down their pipe transports cleanly (which avoids
noisy Windows Proactor warnings). The app delegates to it so the App class is no
longer responsible for raw transport plumbing.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass

from codegenome.tui.constants import LogChannel


@dataclass
class ActiveProcess:
    """Track a background subprocess and its log destination."""

    process: asyncio.subprocess.Process
    channel: LogChannel


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
