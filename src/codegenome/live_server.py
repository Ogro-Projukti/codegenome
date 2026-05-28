"""WebSocket server for real-time architectural observer graph updates."""

import asyncio
import json
import logging
import threading
from typing import Set

import websockets

LOG = logging.getLogger(__name__)


class LiveGraphServer:
    """Manage WebSocket connections and broadcast real-time graph updates."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    async def register(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Register a new client connection."""
        self.clients.add(websocket)
        LOG.info(f"WebSocket client connected. Total clients: {len(self.clients)}")
        try:
            await websocket.wait_closed()
        finally:
            self.clients.remove(websocket)
            LOG.info(f"WebSocket client disconnected. Total clients: {len(self.clients)}")

    async def _handler(self, websocket, *args, **kwargs) -> None:
        """Handle an incoming WebSocket connection."""
        await self.register(websocket)

    async def _start_server(self) -> None:
        """Start the WebSocket server and wait indefinitely."""
        LOG.info(f"Starting WebSocket server on ws://{self.host}:{self.port}")
        async with websockets.serve(self._handler, self.host, self.port):
            # Wait until the stop event is set
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
        """Stop the WebSocket server."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    async def broadcast_graph_delta(self, delta_payload: dict) -> None:
        """Push a JSON-serializable graph delta to all connected clients."""
        if not self.clients:
            return
            
        message = json.dumps(delta_payload)
        websockets.broadcast(self.clients, message)

    def sync_broadcast_graph_delta(self, delta_payload: dict) -> None:
        """A thread-safe wrapper to broadcast from a synchronous context."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.broadcast_graph_delta(delta_payload), 
                self._loop
            )
