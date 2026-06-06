"""MCP server subprocess lifecycle management."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading

from codegenome.engine.context import EngineContext

LOG = logging.getLogger(__name__)


class McpProcessManager:
    """Start, supervise, and stop the MCP server subprocess."""

    def __init__(self, ctx: EngineContext) -> None:
        self.ctx = ctx
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> subprocess.Popen[str]:
        """Start the MCP server as a subprocess (idempotent while running)."""
        if self._process and self._process.poll() is None:
            return self._process

        ctx = self.ctx
        if getattr(sys, "frozen", False):
            command = [
                sys.executable,
                "--run-mcp-server",
                "--db-path",
                str(ctx.db_path),
                "--host",
                ctx.config.mcp_host,
                "--port",
                str(ctx.config.mcp_port),
                "--transport",
                "http",
            ]
        else:
            command = [
                sys.executable,
                "-m",
                "codegenome.mcp_server",
                "--db-path",
                str(ctx.db_path),
                "--host",
                ctx.config.mcp_host,
                "--port",
                str(ctx.config.mcp_port),
                "--transport",
                "http",
            ]
        LOG.info("Starting MCP server: %s", " ".join(command))
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._start_stderr_forwarder(self._process)
        return self._process

    def _start_stderr_forwarder(self, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return

        def forward() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                sys.stderr.write(line)
                sys.stderr.flush()

        thread = threading.Thread(
            target=forward, name="codegenome-mcp-stderr", daemon=True
        )
        thread.start()

    def stop(self) -> None:
        """Stop the MCP server subprocess if it is running."""
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
