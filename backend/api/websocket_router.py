"""
backend/api/websocket_router.py
================================
WebSocket event streaming for the Vantag platform.

Endpoints
---------
GET /ws/events                      – broadcast stream of all events
GET /ws/store/{store_id}/events     – store-filtered event stream

Protocol
--------
* Server sends JSON-encoded ``WebSocketEvent`` objects.
* Server sends a ``{"type": "ping"}`` heartbeat every 30 seconds.
* Client should respond with ``{"type": "pong"}`` (ignored if absent).
* On normal close the server sends code 1000.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .models import WebSocketEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------

_PING_INTERVAL: float = 30.0  # seconds


class ConnectionManager:
    """
    Manages active WebSocket connections and broadcasts events.

    Connections are tracked in two sets:
    * ``_global_connections``  — receive every event.
    * ``_store_connections``   — receive events filtered by store_id.

    Thread/task safety: all mutation happens in the async event loop, so no
    additional locking is required beyond using standard asyncio primitives.
    """

    def __init__(self) -> None:
        self._global_connections: Set[WebSocket] = set()
        self._store_connections: Dict[str, Set[WebSocket]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket, store_id: Optional[str] = None) -> None:
        """Accept the WebSocket and register it for the appropriate stream."""
        await ws.accept()
        if store_id:
            self._store_connections.setdefault(store_id, set()).add(ws)
            logger.info(
                "WS client connected | store=%s total_store=%d",
                store_id,
                len(self._store_connections[store_id]),
            )
        else:
            self._global_connections.add(ws)
            logger.info(
                "WS client connected (global) | total=%d",
                len(self._global_connections),
            )

    async def disconnect(self, ws: WebSocket, store_id: Optional[str] = None) -> None:
        """Unregister a WebSocket (called on normal and abnormal close)."""
        if store_id:
            bucket = self._store_connections.get(store_id, set())
            bucket.discard(ws)
            if not bucket:
                self._store_connections.pop(store_id, None)
            logger.info("WS client disconnected | store=%s", store_id)
        else:
            self._global_connections.discard(ws)
            logger.info(
                "WS client disconnected (global) | remaining=%d",
                len(self._global_connections),
            )

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    async def broadcast(self, message: dict) -> None:
        """
        Send *message* as JSON to all connected clients (global + matching
        store-filtered connections).
        """
        raw = json.dumps(message, default=str)
        store_id: Optional[str] = message.get("store_id")

        await self._send_to_set(raw, self._global_connections)

        if store_id:
            bucket = self._store_connections.get(store_id, set())
            await self._send_to_set(raw, bucket)

    async def broadcast_event(self, event: WebSocketEvent) -> None:
        """Convenience wrapper that serialises a ``WebSocketEvent`` first."""
        await self.broadcast(event.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_to_set(self, raw: str, connections: Set[WebSocket]) -> None:
        """Send *raw* JSON string to every WebSocket in *connections*.

        Stale / closed connections are silently removed.
        """
        dead: Set[WebSocket] = set()
        for ws in list(connections):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(raw)
                else:
                    dead.add(ws)
            except Exception as exc:  # noqa: BLE001
                logger.debug("WS send failed | error=%s", exc)
                dead.add(ws)
        connections.difference_update(dead)

    @property
    def global_connection_count(self) -> int:
        return len(self._global_connections)

    @property
    def store_connection_count(self) -> int:
        return sum(len(v) for v in self._store_connections.values())


# ---------------------------------------------------------------------------
# Module-level singleton – shared with other modules via import.
# ---------------------------------------------------------------------------

manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Keepalive helper
# ---------------------------------------------------------------------------


async def _keepalive_loop(ws: WebSocket, store_id: Optional[str] = None) -> None:
    """Send ping frames every ``_PING_INTERVAL`` seconds until the socket closes."""
    ping_msg = json.dumps({"type": "ping", "timestamp": None})
    while True:
        await asyncio.sleep(_PING_INTERVAL)
        try:
            if ws.client_state != WebSocketState.CONNECTED:
                break
            # Update timestamp on each ping.
            await ws.send_text(
                json.dumps({"type": "ping", "timestamp": time.time()})
            )
        except Exception:  # noqa: BLE001
            break


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    """
    Global WebSocket stream – broadcasts every behavioral event in real-time.

    Messages are JSON-encoded ``WebSocketEvent`` objects.  A ``{"type": "ping"}``
    heartbeat is sent every 30 seconds to keep the connection alive through
    proxies and load balancers.
    """
    await manager.connect(ws)
    keepalive = asyncio.create_task(_keepalive_loop(ws))
    try:
        while True:
            # Keep the receive loop alive so disconnect events are detected.
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=_PING_INTERVAL + 5)
                # Handle pong / client-originated messages gracefully.
                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "pong":
                        logger.debug("Received pong from global client")
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                # No message from client – that's fine, server pushes events.
                pass
    except WebSocketDisconnect:
        logger.info("Global WS client disconnected normally.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Global WS client error | error=%s", exc)
    finally:
        keepalive.cancel()
        await manager.disconnect(ws)


@router.websocket("/ws/store/{store_id}/events")
async def ws_store_events(ws: WebSocket, store_id: str) -> None:
    """
    Store-filtered WebSocket stream.

    Only events whose ``store_id`` matches the path parameter are forwarded
    to this connection.
    """
    await manager.connect(ws, store_id=store_id)
    keepalive = asyncio.create_task(_keepalive_loop(ws, store_id=store_id))
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=_PING_INTERVAL + 5)
                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "pong":
                        logger.debug("Received pong from store client | store=%s", store_id)
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("Store WS client disconnected | store=%s", store_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Store WS client error | store=%s error=%s", store_id, exc)
    finally:
        keepalive.cancel()
        await manager.disconnect(ws, store_id=store_id)
