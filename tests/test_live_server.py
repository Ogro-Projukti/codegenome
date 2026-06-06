"""Tests for WebSocket room subscriptions in LiveGraphServer."""

from __future__ import annotations

import asyncio
import json

import pytest

from codegenome.live_server import ClientSubscription, LiveGraphServer


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self._closed = False
        self._messages: asyncio.Queue[str | None] = asyncio.Queue()

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self._closed = True
        await self._messages.put(None)

    def enqueue(self, message: str) -> None:
        self._messages.put_nowait(message)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        message = await self._messages.get()
        if message is None:
            raise StopAsyncIteration
        return message


@pytest.mark.asyncio
async def test_subscribe_message_updates_client_room() -> None:
    server = LiveGraphServer()
    websocket = _FakeWebSocket()
    server.clients.add(websocket)
    server._subscriptions[websocket] = ClientSubscription()

    await server._handle_client_message(
        websocket,
        json.dumps({"action": "subscribe", "level": "helix", "module_id": "core"}),
    )

    subscription = server._subscriptions[websocket]
    assert subscription.level == "helix"
    assert subscription.module_id == "core"


@pytest.mark.asyncio
async def test_broadcast_targets_karyotype_and_helix_rooms() -> None:
    server = LiveGraphServer()
    karyotype_client = _FakeWebSocket()
    helix_client = _FakeWebSocket()
    other_module_client = _FakeWebSocket()

    server.clients.update({karyotype_client, helix_client, other_module_client})
    server._subscriptions[karyotype_client] = ClientSubscription(level="karyotype")
    server._subscriptions[helix_client] = ClientSubscription(level="helix", module_id="core")
    server._subscriptions[other_module_client] = ClientSubscription(level="helix", module_id="other")

    delta_payload = {
        "type": "graph_delta",
        "snapshot_id": 2,
        "added_nodes": ["symbol:core/main.py:run"],
        "removed_nodes": [],
        "modified_nodes": [],
        "added_edges": [],
        "removed_edges": [],
    }
    karyotype_updates = [
        {"module_id": "core", "gene_count": 1, "health_score": 0.91},
    ]

    await server.broadcast_graph_delta(
        delta_payload,
        changed_file="core/main.py",
        karyotype_updates=karyotype_updates,
        snapshot_id=2,
    )

    assert len(karyotype_client.sent) == 1
    karyotype_message = json.loads(karyotype_client.sent[0])
    assert karyotype_message["type"] == "karyotype_update"
    assert karyotype_message["modules"][0]["module_id"] == "core"

    assert len(helix_client.sent) == 1
    helix_message = json.loads(helix_client.sent[0])
    assert helix_message["type"] == "graph_delta"
    assert helix_message["module_id"] == "core"
    assert helix_message["added_nodes"] == ["symbol:core/main.py:run"]

    assert other_module_client.sent == []
