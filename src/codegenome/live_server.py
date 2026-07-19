"""WebSocket server for real-time architectural observer graph updates."""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Set

import websockets

from codegenome.network_utils import LOOPBACK_HOST

from codegenome.serializers.genome_provider import (
    filter_graph_delta_for_module,
    module_id_for_file,
    resolve_changed_file_paths,
)
from codegenome.serializers.genome_schemas import KaryotypeUpdateMessage

LOG = logging.getLogger(__name__)


@dataclass
class ClientSubscription:
    """Per-client view subscription for progressive disclosure."""

    level: str = "karyotype"
    module_id: str | None = None


class LiveGraphServer:
    """Manage WebSocket connections and broadcast real-time graph updates."""

    def __init__(self, host: str = LOOPBACK_HOST, port: int = 8765):
        """Initialize the LiveGraphServer.

        Args:
            host (str, optional): The host address to bind to. Defaults to "127.0.0.1".
            port (int, optional): The port to listen on. Defaults to 8765.
        """
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self._subscriptions: dict[websockets.WebSocketServerProtocol, ClientSubscription] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    async def register(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Register a new client connection and process subscription messages.

        Args:
            websocket (websockets.WebSocketServerProtocol): The connected client websocket.
        """
        self.clients.add(websocket)
        self._subscriptions[websocket] = ClientSubscription()
        LOG.info(f"WebSocket client connected. Total clients: {len(self.clients)}")
        try:
            async for raw_message in websocket:
                await self._handle_client_message(websocket, raw_message)
        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            self._subscriptions.pop(websocket, None)
            LOG.info(f"WebSocket client disconnected. Total clients: {len(self.clients)}")

    async def _handle_client_message(
        self,
        websocket: websockets.WebSocketServerProtocol,
        raw_message: str | bytes,
    ) -> None:
        """Apply a client subscription message such as ``subscribe``."""
        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")
            payload = json.loads(raw_message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            LOG.debug("Ignoring non-JSON WebSocket message from client.")
            return

        if payload.get("action") != "subscribe":
            return

        level = str(payload.get("level", "karyotype"))
        module_id = payload.get("module_id")
        if level not in {"karyotype", "helix", "structure"}:
            LOG.debug("Ignoring subscribe with unknown level: %s", level)
            return
        if level in {"helix", "structure"} and not module_id:
            LOG.debug("Ignoring %s subscribe without module_id.", level)
            return

        self._subscriptions[websocket] = ClientSubscription(
            level=level,
            module_id=str(module_id) if module_id is not None else None,
        )
        LOG.info(
            "Client subscribed to %s%s",
            level,
            f" ({module_id})" if module_id else "",
        )

    async def _handler(self, websocket, *args, **kwargs) -> None:
        """Handle an incoming WebSocket connection.

        Args:
            websocket (websockets.WebSocketServerProtocol): The incoming websocket connection.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        await self.register(websocket)

    async def _start_server(self) -> None:
        """Start the WebSocket server and wait indefinitely."""
        LOG.info(f"Starting WebSocket server on ws://{self.host}:{self.port}")
        async with websockets.serve(self._handler, self.host, self.port):
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)

    def start_background(self) -> None:
        """Start the asyncio event loop and WebSocket server in a daemon thread."""
        def _run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._start_server())
            except Exception as e:
                LOG.error(f"WebSocket server error: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=_run_loop, daemon=True, name="WebSocketServer")
        self._thread.start()

    def stop(self) -> None:
        """Stop the WebSocket server and its daemon thread if running."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    async def broadcast_graph_delta(
        self,
        delta_payload: dict[str, Any],
        *,
        changed_file: str | None = None,
        karyotype_updates: list[dict[str, Any]] | None = None,
        snapshot_id: int | None = None,
    ) -> None:
        """Push graph deltas only to clients subscribed to the relevant rooms.

        Args:
            delta_payload (dict): Full graph delta from the timeline.
            changed_file (str | None): Relative path of the file that triggered the update.
            karyotype_updates (list[dict[str, Any]] | None): Lightweight module summaries.
            snapshot_id (int | None): Current snapshot id for karyotype subscribers.
        """
        if not self.clients:
            return

        changed_files = resolve_changed_file_paths(delta_payload, fallback=changed_file)
        affected_modules = sorted({module_id_for_file(path) for path in changed_files})

        for websocket in list(self.clients):
            subscription = self._subscriptions.get(websocket, ClientSubscription())
            try:
                if subscription.level == "karyotype":
                    if not karyotype_updates:
                        continue
                    message = KaryotypeUpdateMessage(
                        modules=karyotype_updates,
                        snapshot_id=snapshot_id,
                    )
                    await websocket.send(message.model_dump_json())
                    continue

                if subscription.level in {"helix", "structure"} and subscription.module_id:
                    if subscription.module_id not in affected_modules:
                        continue
                    room_delta = filter_graph_delta_for_module(
                        delta_payload,
                        subscription.module_id,
                    )
                    room_delta["type"] = "graph_delta"
                    room_delta["module_id"] = subscription.module_id
                    await websocket.send(json.dumps(room_delta))
            except websockets.ConnectionClosed:
                self.clients.discard(websocket)
                self._subscriptions.pop(websocket, None)

    def sync_broadcast_graph_delta(
        self,
        delta_payload: dict[str, Any],
        *,
        changed_file: str | None = None,
        karyotype_updates: list[dict[str, Any]] | None = None,
        snapshot_id: int | None = None,
    ) -> None:
        """A thread-safe wrapper to broadcast from a synchronous context.

        Args:
            delta_payload (dict): A dictionary representing the graph delta.
            changed_file (str | None): Relative path of the changed file.
            karyotype_updates (list[dict[str, Any]] | None): Lightweight module summaries.
            snapshot_id (int | None): Current snapshot id.
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.broadcast_graph_delta(
                    delta_payload,
                    changed_file=changed_file,
                    karyotype_updates=karyotype_updates,
                    snapshot_id=snapshot_id,
                ),
                self._loop,
            )
