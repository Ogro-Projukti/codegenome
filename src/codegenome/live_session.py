"""Live evolution session: build, serve, watch, and broadcast graph changes.

`LiveSession` encapsulates everything the ``codegenome evolve`` command used to
do inline: an initial graph build, an optional WebSocket broadcast server, an
embedded HTTP server (static graph viewer plus AI-chat endpoints), a filesystem
watcher that performs surgical graph updates, and the lifecycle wiring that ties
them together. Keeping it here leaves the CLI command a thin adapter.
"""

from __future__ import annotations

import json
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer
from typing import Any, Callable

from codegenome.core import (
    CodeGenomeConfig,
    CodeGenomeEngine,
    SurgicalUpdateHandler,
)

DEFAULT_HTTP_PORT = 8000
DEFAULT_WS_PORT = 8765

Emitter = Callable[[str], None]


@dataclass
class LiveSessionConfig:
    """Configuration for a :class:`LiveSession`.

    Attributes:
        workspace (Path): Workspace root to observe.
        live (bool): Enable the WebSocket real-time broadcast server.
        lan (bool): Bind HTTP/WebSocket on the local network (0.0.0.0).
        memory_bounded (bool): Keep only a bounded working set in memory.
        max_working_files (int): Maximum resident files when memory-bounded.
        http_port (int): Port for the static/AI HTTP server.
        ws_port (int): Port for the WebSocket broadcast server.
    """

    workspace: Path
    live: bool = False
    lan: bool = False
    memory_bounded: bool = False
    max_working_files: int = 64
    http_port: int = DEFAULT_HTTP_PORT
    ws_port: int = DEFAULT_WS_PORT


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_ai_request_handler(engine: CodeGenomeEngine) -> type[SimpleHTTPRequestHandler]:
    """Build an HTTP handler serving the graph viewer plus AI-chat endpoints.

    Args:
        engine (CodeGenomeEngine): Engine providing export/genome directories and
            the graph JSON consumed by the AI endpoints.

    Returns:
        type[SimpleHTTPRequestHandler]: A handler class bound to the engine.
    """
    from codegenome.ai_chat import (
        AIChatError,
        chat_completion,
        load_models,
        settings_payload,
    )

    class AIChatRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(engine.export_dir), **kwargs)

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            pass

        def do_GET(self):  # noqa: N802 - stdlib signature
            if self.path == "/ai/settings":
                self._send_json(settings_payload(engine.genome_dir))
                return
            super().do_GET()

        def do_POST(self):  # noqa: N802 - stdlib signature
            if self.path == "/ai/models":
                self._handle_models()
                return
            if self.path == "/ai/chat":
                self._handle_chat()
                return
            self.send_error(404, "Unknown AI endpoint")

        def _handle_models(self):
            try:
                payload = self._read_json_body()
                models = load_models(
                    engine.genome_dir,
                    str(payload.get("provider", "")),
                    _optional_string(payload.get("api_key")),
                    save_api_key=bool(payload.get("save_api_key")),
                )
                self._send_json({"models": models})
            except AIChatError as exc:
                self._send_json({"error": str(exc)}, status=400)
            except Exception as exc:  # noqa: BLE001 - keep live server responsive
                self._send_json(
                    {"error": f"AI model loading failed: {exc}"}, status=500
                )

        def _handle_chat(self):
            try:
                payload = self._read_json_body()
                answer = chat_completion(
                    engine.genome_dir,
                    engine.graph_json_path,
                    str(payload.get("provider", "")),
                    str(payload.get("model", "")),
                    payload.get("messages", []),
                    _optional_string(payload.get("api_key")),
                    _optional_string(payload.get("selected_node_id")),
                    _optional_string(payload.get("context_size")),
                    save_api_key=bool(payload.get("save_api_key")),
                )
                self._send_json({"message": answer})
            except AIChatError as exc:
                self._send_json({"error": str(exc)}, status=400)
            except Exception as exc:  # noqa: BLE001 - keep live server responsive
                self._send_json({"error": f"AI chat failed: {exc}"}, status=500)

        def _read_json_body(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _send_json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return AIChatRequestHandler


class LiveSession:
    """Coordinate the engine, live server, HTTP server, and file watcher."""

    def __init__(self, config: LiveSessionConfig, *, emit: Emitter = print) -> None:
        self._config = config
        self._emit = emit
        self.engine = CodeGenomeEngine(
            CodeGenomeConfig(
                workspace=config.workspace,
                export_formats=("json", "html"),
                memory_bounded=config.memory_bounded,
                max_working_files=max(1, config.max_working_files),
            )
        )
        self._live_server = None
        self._httpd: ThreadingTCPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._observer = None

    @property
    def bind_host(self) -> str:
        return "0.0.0.0" if self._config.lan else "127.0.0.1"

    def build_initial(self) -> None:
        """Run the initial full build before serving."""
        self._emit(f"Running initial build for {self._config.workspace}...")
        self.engine.build(full=True)

    def start_live_server(self):
        """Start the WebSocket broadcast server when ``live`` is enabled."""
        if not self._config.live:
            return None

        from codegenome.live_server import LiveGraphServer
        from codegenome.network_utils import get_lan_ip

        self._live_server = LiveGraphServer(
            host=self.bind_host, port=self._config.ws_port
        )
        self._live_server.start_background()
        if self._config.lan:
            lan_ip = get_lan_ip()
            self._emit(
                f"WebSocket server listening on ws://0.0.0.0:{self._config.ws_port}"
            )
            self._emit(f"  LAN clients connect to ws://{lan_ip}:{self._config.ws_port}")
        else:
            self._emit(
                f"WebSocket server initialized on ws://127.0.0.1:{self._config.ws_port}"
            )
        return self._live_server

    def start_http_server(self) -> None:
        """Start the static + AI-chat HTTP server in a daemon thread."""
        handler = build_ai_request_handler(self.engine)
        lan = self._config.lan
        listen_host = self.bind_host if lan else ""
        self._httpd = ThreadingTCPServer((listen_host, self._config.http_port), handler)

        def _serve() -> None:
            assert self._httpd is not None
            with self._httpd:
                self._httpd.serve_forever()

        self._http_thread = threading.Thread(target=_serve, daemon=True)
        self._http_thread.start()

    def open_browser(self) -> str:
        """Announce URLs and open the local live graph viewer."""
        from codegenome.network_utils import get_lan_ip

        http_port = self._config.http_port
        live_query = "?live=1"
        local_url = f"http://localhost:{http_port}/graph.html{live_query}"
        if self._config.lan:
            lan_ip = get_lan_ip()
            lan_url = f"http://{lan_ip}:{http_port}/graph.html{live_query}"
            self._emit(f"HTTP server listening on http://0.0.0.0:{http_port}")
            self._emit(f"  Open locally:  {local_url}")
            self._emit(f"  Share on LAN:  {lan_url}")
        else:
            self._emit(
                f"HTTP Server started. Opening live graph UI at {local_url}..."
            )
        webbrowser.open(local_url)
        return local_url

    def start_watch(self) -> None:
        """Watch the workspace and apply surgical updates on changes."""
        from watchdog.observers import Observer

        self._emit("Watching for .py file changes (Press Ctrl+C to stop)...")
        self._observer = Observer()
        handler = SurgicalUpdateHandler(self.engine, live_server=self._live_server)
        self._observer.schedule(handler, str(self._config.workspace), recursive=True)
        self._observer.start()

    def serve(self) -> None:
        """Run the full live session until interrupted, then clean up."""
        self.build_initial()
        self.start_live_server()
        self.start_http_server()
        self.open_browser()
        self.start_watch()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self._emit("\nStopping observer...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Tear down the watcher, servers, and engine."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
        self.engine.close()
        if self._live_server is not None:
            self._live_server.stop()
            self._live_server = None
