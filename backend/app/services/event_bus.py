"""Real-time fan-out.

Every API replica publishes domain events to one Redis Pub/Sub channel and every replica
subscribes, pushing messages to the WebSocket clients connected to *it*. This lets the API tier
scale horizontally behind a load balancer without sticky sessions for real-time delivery.
"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from prometheus_client import Gauge

from app.services.redis_client import get_redis

log = logging.getLogger(__name__)
CHANNEL = "netra:realtime"
WS_CONNECTIONS = Gauge("netra_ws_connections", "Open WebSocket connections on this replica")


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, dict] = {}
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket, user: dict) -> None:
        async with self._lock:
            self._clients[ws] = user
        WS_CONNECTIONS.set(len(self._clients))

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(ws, None)
        WS_CONNECTIONS.set(len(self._clients))

    async def broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=2)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.remove(ws)

    @property
    def count(self) -> int:
        return len(self._clients)


manager = ConnectionManager()


async def publish(event_type: str, data: Any) -> None:
    message = json.dumps({"type": event_type, "ts": datetime.now(UTC).isoformat(), "data": jsonable_encoder(data)})
    r = get_redis()
    if r is None:
        await manager.broadcast(message)
        return
    try:
        await r.publish(CHANNEL, message)
    except Exception:  # Redis blip: still deliver locally rather than drop the event
        log.exception("redis publish failed; delivering locally")
        await manager.broadcast(message)


async def run_subscriber(stop: asyncio.Event) -> None:
    r = get_redis()
    if r is None:
        return
    while not stop.is_set():
        try:
            pubsub = r.pubsub()
            await pubsub.subscribe(CHANNEL)
            log.info("realtime subscriber attached to %s", CHANNEL)
            while not stop.is_set():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    await manager.broadcast(msg["data"])
            await pubsub.aclose()
        except Exception:
            log.exception("realtime subscriber error; reconnecting")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=2)
