"""
backend/api/websocket_router.py
================================
WebSocket event streaming for the Vantag platform.

Endpoints
---------
GET /ws/events                      – broadcast stream of all events (JWT required)
GET /ws/store/{store_id}/events     – store-filtered event stream (JWT required)

Authentication
--------------
Clients MUST pass a valid JWT via the ``?token=<jwt>`` query parameter.
Connections with a missing or invalid token are rejected with close code
1008 (Policy Violation) before ``ws.accept()`` is called.

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
import os
import time
from typing import Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .models import WebSocketEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

# ---------------------------------------------------------------------------
# JWT validation (reuses the same secret as HTTP middleware)
# ---------------------------------------------------------------------------

_JWT_SECRET = os.getenv("VANTAG_JWT_SECRET", "change-me")
_JWT_ALGORITHM = "HS256"


def _validate_ws_token(token: str) -> dict | None:
    """Validate a JWT token string; return claims dict or None on failure."""
    try:
        from jose import jwt
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------

_PING_INTERVAL: float = 30.0  # seconds


class ConnectionManager:
    """
    Manages active WebSocket connections and broadcasts events.

    Connections are tracked in two sets:
    * ``_global_connections``  — receive every event (keyed by ws → tenant_id).
    * ``_store_connections``   — receive events filtered by store_id.

    All broadcast methods filter events by ``tenant_id`` so that tenants only
    receive their own events.
    """

    def __init__(self) -> None:
        # ws → tenant_id mapping for global connections
        self._global_connections: Dict[WebSocket, str] = {}
        # store_id → {ws → tenant_id}
        self._store_connections: Dict[str, Dict[WebSocket, str]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self, ws: WebSocket, tenant_id: str, store_id: Optional[str] = None
    ) -> None:
        """Accept the WebSocket and register it for the appropriate stream."""
        await ws.accept()
        if store_id:
            self._store_connections.setdefault(store_id, {})[ws] = tenant_id
            logger.info(
                "WS client connected | store=%s tenant=%s total_store=%d",
                store_id,
                tenant_id,
                len(self._store_connections[store_id]),
            )
        else:
            self._global_connections[ws] = tenant_id
            logger.info(
                "WS client connected (global) | tenant=%s total=%d",
                tenant_id,
                len(self._global_connections),
            )

    async def disconnect(self, ws: WebSocket, store_id: Optional[str] = None) -> None:
        """Unregister a WebSocket (called on normal and abnormal close)."""
        if store_id:
            bucket = self._store_connections.get(store_id, {})
            bucket.pop(ws, None)
            if not bucket:
                self._store_connections.pop(store_id, None)
            logger.info("WS client disconnected | store=%s", store_id)
        else:
            self._global_connections.pop(ws, None)
            logger.info(
                "WS client disconnected (global) | remaining=%d",
                len(self._global_connections),
            )

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    async def broadcast(self, message: dict) -> None:
        """
        Send *message* as JSON to all connected clients whose ``tenant_id``
        matches the event's ``tenant_id`` field (or all global clients if the
        event carries no ``tenant_id``).
        """
        raw = json.dumps(message, default=str)
        event_tenant_id: Optional[str] = message.get("tenant_id")
        store_id: Optional[str] = message.get("store_id")

        await self._send_to_tenant_map(raw, self._global_connections, event_tenant_id)

        if store_id:
            bucket = self._store_connections.get(store_id, {})
            await self._send_to_tenant_map(raw, bucket, event_tenant_id)

    async def broadcast_event(self, event: WebSocketEvent) -> None:
        """Convenience wrapper that serialises a ``WebSocketEvent`` first."""
        await self.broadcast(event.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_to_tenant_map(
        self,
        raw: str,
        connections: Dict[WebSocket, str],
        event_tenant_id: Optional[str],
    ) -> None:
        """Send *raw* to each WebSocket whose tenant matches *event_tenant_id*.

        If *event_tenant_id* is None/empty, send to all connections (backward
        compat for internal pipeline events that don't carry a tenant).
        Stale / closed connections are silently removed.
        """
        dead: list[WebSocket] = []
        for ws, ws_tenant in list(connections.items()):
            # Tenant filtering: skip if event belongs to a different tenant
            if event_tenant_id and ws_tenant != event_tenant_id:
                continue
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(raw)
                else:
                    dead.append(ws)
            except Exception as exc:  # noqa: BLE001
                logger.debug("WS send failed | error=%s", exc)
                dead.append(ws)
        for ws in dead:
            connections.pop(ws, None)

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
    while True:
        await asyncio.sleep(_PING_INTERVAL)
        try:
            if ws.client_state != WebSocketState.CONNECTED:
                break
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
    Global WebSocket stream — authenticated, tenant-scoped.

    Requires ``?token=<jwt>`` query parameter.  Connections with a missing or
    invalid token are rejected with close code 1008 before accept().
    """
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=1008, reason="Authentication required: missing ?token=")
        return

    claims = _validate_ws_token(token)
    if not claims:
        await ws.close(code=1008, reason="Authentication failed: invalid or expired token")
        return

    tenant_id: str = claims.get("tenant_id", "")
    if not tenant_id:
        await ws.close(code=1008, reason="Authentication failed: token missing tenant_id")
        return

    await manager.connect(ws, tenant_id=tenant_id)
    keepalive = asyncio.create_task(_keepalive_loop(ws))
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=_PING_INTERVAL + 5)
                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "pong":
                        logger.debug("Received pong from global client | tenant=%s", tenant_id)
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("Global WS client disconnected normally | tenant=%s", tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Global WS client error | tenant=%s error=%s", tenant_id, exc)
    finally:
        keepalive.cancel()
        await manager.disconnect(ws)


@router.websocket("/ws/store/{store_id}/events")
async def ws_store_events(ws: WebSocket, store_id: str) -> None:
    """
    Store-filtered WebSocket stream — authenticated, tenant-scoped.

    Requires ``?token=<jwt>`` query parameter.  Only events whose ``store_id``
    matches the path parameter AND whose ``tenant_id`` matches the JWT are
    forwarded to this connection.
    """
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=1008, reason="Authentication required: missing ?token=")
        return

    claims = _validate_ws_token(token)
    if not claims:
        await ws.close(code=1008, reason="Authentication failed: invalid or expired token")
        return

    tenant_id: str = claims.get("tenant_id", "")
    if not tenant_id:
        await ws.close(code=1008, reason="Authentication failed: token missing tenant_id")
        return

    await manager.connect(ws, tenant_id=tenant_id, store_id=store_id)
    keepalive = asyncio.create_task(_keepalive_loop(ws, store_id=store_id))
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=_PING_INTERVAL + 5)
                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "pong":
                        logger.debug("Received pong from store client | store=%s tenant=%s", store_id, tenant_id)
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("Store WS client disconnected | store=%s tenant=%s", store_id, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Store WS client error | store=%s tenant=%s error=%s", store_id, tenant_id, exc)
    finally:
        keepalive.cancel()
        await manager.disconnect(ws, store_id=store_id)

