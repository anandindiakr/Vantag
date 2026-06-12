"""
backend/audio/intercom.py
==========================
Two-way audio intercom via WebRTC signaling for the Vantag platform.

This module implements a WebSocket-based WebRTC signaling server.  It does
NOT handle media directly; it relays SDP offer/answer messages and ICE
candidates between the dashboard browser client and the on-premises edge
device (Jetson / IP camera) that runs the corresponding WebRTC peer.

WebSocket endpoint
------------------
GET /ws/intercom/{camera_id}

Protocol (JSON messages)
------------------------
Client → Server:
  {"type": "offer",  "sdp": "<SDP string>"}
  {"type": "answer", "sdp": "<SDP string>"}
  {"type": "ice",    "candidate": {...}}
  {"type": "end"}

Server → Client:
  {"type": "offer",   "sdp": "<SDP string>"}
  {"type": "answer",  "sdp": "<SDP string>"}
  {"type": "ice",     "candidate": {...}}
  {"type": "ended",   "camera_id": "..."}
  {"type": "error",   "detail": "..."}
  {"type": "status",  "state": "waiting" | "connected" | "ended"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Audio / Intercom"])

# ---------------------------------------------------------------------------
# Session model
# ---------------------------------------------------------------------------


@dataclass
class IntercomSession:
    """Tracks a single intercom session between dashboard and edge device."""

    camera_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    state: str = "waiting"              # waiting | connected | ended
    dashboard_ws: Optional[WebSocket] = None
    edge_ws: Optional[WebSocket] = None
    sdp_offer: Optional[str] = None
    sdp_answer: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.state not in ("ended",)


# ---------------------------------------------------------------------------
# IntercomSignalingServer
# ---------------------------------------------------------------------------


class IntercomSignalingServer:
    """
    Manages active WebRTC intercom sessions.

    Conventions
    -----------
    * The first WebSocket to connect for a given ``camera_id`` is treated as
      the **dashboard** (caller side).
    * The second connection is treated as the **edge device** (callee side).
    * SDP and ICE messages are relayed between the two peers transparently.
    * If either peer disconnects the session is ended and the other peer is
      notified.

    All public methods are coroutines and are safe to call from the
    asyncio event loop.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, IntercomSession] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def get_or_create_session(self, camera_id: str) -> IntercomSession:
        """Return an existing active session or create a new one."""
        async with self._lock:
            session = self._sessions.get(camera_id)
            if session is None or not session.is_active:
                session = IntercomSession(camera_id=camera_id)
                self._sessions[camera_id] = session
                logger.info("Intercom session created | camera=%s", camera_id)
            return session

    async def end_session(self, camera_id: str) -> None:
        """
        Terminate an active session and notify both peers.

        Safe to call even if the session does not exist.
        """
        async with self._lock:
            session = self._sessions.get(camera_id)
            if session is None:
                return
            session.state = "ended"

        end_msg = json.dumps({"type": "ended", "camera_id": camera_id})

        for ws in (session.dashboard_ws, session.edge_ws):
            if ws and ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_text(end_msg)
                    await ws.close(code=1000)
                except Exception:  # noqa: BLE001
                    pass

        logger.info("Intercom session ended | camera=%s", camera_id)

    # ------------------------------------------------------------------
    # Signal relay
    # ------------------------------------------------------------------

    async def handle_offer(self, camera_id: str, sdp: str) -> None:
        """Store the SDP offer and relay it to the edge peer if connected."""
        session = self._sessions.get(camera_id)
        if session is None:
            return
        session.sdp_offer = sdp
        offer_msg = json.dumps({"type": "offer", "sdp": sdp})
        if session.edge_ws and session.edge_ws.client_state == WebSocketState.CONNECTED:
            await session.edge_ws.send_text(offer_msg)
            logger.debug("SDP offer relayed to edge | camera=%s", camera_id)

    async def handle_answer(self, camera_id: str, sdp: str) -> None:
        """Store the SDP answer and relay it to the dashboard peer if connected."""
        session = self._sessions.get(camera_id)
        if session is None:
            return
        session.sdp_answer = sdp
        answer_msg = json.dumps({"type": "answer", "sdp": sdp})
        if session.dashboard_ws and session.dashboard_ws.client_state == WebSocketState.CONNECTED:
            await session.dashboard_ws.send_text(answer_msg)
            logger.debug("SDP answer relayed to dashboard | camera=%s", camera_id)

    async def relay_ice(
        self,
        camera_id: str,
        candidate: dict,
        from_dashboard: bool,
    ) -> None:
        """Relay an ICE candidate to the opposite peer."""
        session = self._sessions.get(camera_id)
        if session is None:
            return
        ice_msg = json.dumps({"type": "ice", "candidate": candidate})
        target_ws = session.edge_ws if from_dashboard else session.dashboard_ws
        if target_ws and target_ws.client_state == WebSocketState.CONNECTED:
            await target_ws.send_text(ice_msg)

    # ------------------------------------------------------------------
    # Connection registration
    # ------------------------------------------------------------------

    async def register_dashboard(self, camera_id: str, ws: WebSocket) -> None:
        """Register the dashboard WebSocket for a session."""
        session = await self.get_or_create_session(camera_id)
        session.dashboard_ws = ws
        if session.edge_ws and session.edge_ws.client_state == WebSocketState.CONNECTED:
            session.state = "connected"
        await ws.send_text(
            json.dumps({"type": "status", "state": session.state})
        )
        # If an offer is already cached (edge connected first), send it now.
        if session.sdp_offer and session.state == "connected":
            await ws.send_text(json.dumps({"type": "offer", "sdp": session.sdp_offer}))

    async def register_edge(self, camera_id: str, ws: WebSocket) -> None:
        """Register the edge device WebSocket for a session."""
        session = await self.get_or_create_session(camera_id)
        session.edge_ws = ws
        if session.dashboard_ws and session.dashboard_ws.client_state == WebSocketState.CONNECTED:
            session.state = "connected"
        await ws.send_text(
            json.dumps({"type": "status", "state": session.state})
        )

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        camera_id: str,
        raw: str,
        from_dashboard: bool,
    ) -> None:
        """
        Parse a raw JSON message from a peer and take the appropriate action.
        """
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON message | camera=%s", camera_id)
            return

        msg_type = msg.get("type")

        if msg_type == "offer":
            await self.handle_offer(camera_id, msg.get("sdp", ""))
        elif msg_type == "answer":
            await self.handle_answer(camera_id, msg.get("sdp", ""))
        elif msg_type == "ice":
            await self.relay_ice(camera_id, msg.get("candidate", {}), from_dashboard)
        elif msg_type == "end":
            await self.end_session(camera_id)
        else:
            logger.debug(
                "Unknown intercom message type=%s | camera=%s", msg_type, camera_id
            )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def active_session_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_active)

    def get_session(self, camera_id: str) -> Optional[IntercomSession]:
        return self._sessions.get(camera_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

signaling_server = IntercomSignalingServer()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/intercom/{camera_id}")
async def intercom_ws(ws: WebSocket, camera_id: str) -> None:
    """
    WebRTC signaling WebSocket for intercom sessions.

    Query parameter ``role`` controls the peer type:
      * ``dashboard`` (default) – browser / operator console
      * ``edge``                – on-premises Jetson / camera device

    Messages conform to the protocol documented at the top of this module.
    """
    await ws.accept()

    # Determine peer role from query params.
    role = (ws.query_params.get("role") or "dashboard").lower()
    from_dashboard = role != "edge"

    logger.info(
        "Intercom WS connected | camera=%s role=%s", camera_id, role
    )

    try:
        if from_dashboard:
            await signaling_server.register_dashboard(camera_id, ws)
        else:
            await signaling_server.register_edge(camera_id, ws)

        while True:
            data = await ws.receive_text()
            await signaling_server.dispatch(camera_id, data, from_dashboard)

    except WebSocketDisconnect:
        logger.info(
            "Intercom WS disconnected | camera=%s role=%s", camera_id, role
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Intercom WS error | camera=%s role=%s error=%s", camera_id, role, exc
        )
        try:
            await ws.send_text(
                json.dumps({"type": "error", "detail": str(exc)})
            )
        except Exception:  # noqa: BLE001
            pass
    finally:
        # If one peer drops, clean up the session.
        await signaling_server.end_session(camera_id)
