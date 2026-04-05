"""
backend/mqtt/door_controller.py
================================
MQTT-based door access controller for the Vantag platform.

Publishes lock / unlock commands to the physical door controllers via MQTT
and maintains an in-memory state dict of every door's last known status.

Command payload (published to DOOR_COMMAND topic)
--------------------------------------------------
{
    "action": "lock" | "unlock",
    "issued_by": "<operator_id>",
    "timestamp": "<ISO-8601 UTC>",
    "correlation_id": "<uuid4>"
}

Status payload (received on DOOR_STATUS topic)
----------------------------------------------
{
    "state": "locked" | "unlocked" | "error",
    "door_id": "...",
    "store_id": "...",
    "timestamp": "..."
}

FastAPI REST helpers
--------------------
POST /api/doors/{store_id}/{door_id}/lock
POST /api/doors/{store_id}/{door_id}/unlock
GET  /api/doors/{store_id}/{door_id}/status
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, status

from ..api.models import DoorAction, DoorCommandRequest, DoorState, DoorStatusResponse
from .client import MQTTClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory door state
# ---------------------------------------------------------------------------

_DoorStateEntry = Dict  # keys: state, last_command, last_command_by, last_command_at, correlation_id


# ---------------------------------------------------------------------------
# DoorController
# ---------------------------------------------------------------------------


class DoorController:
    """
    Manages door lock / unlock commands over MQTT and tracks door state.

    Parameters
    ----------
    mqtt_client:
        A connected (or connecting) ``MQTTClient`` instance.
    """

    def __init__(self, mqtt_client: MQTTClient) -> None:
        self._mqtt = mqtt_client
        self._state: Dict[str, _DoorStateEntry] = {}  # key: "{store_id}/{door_id}"
        self._lock = threading.Lock()

        # Subscribe to all door status topics using MQTT wildcard.
        self._mqtt.subscribe(
            "vantag/stores/+/doors/+/status",
            self._handle_status_message,
        )
        logger.info("DoorController initialised and subscribed to status topics.")

    # ------------------------------------------------------------------
    # Public command API
    # ------------------------------------------------------------------

    def lock_door(
        self,
        store_id: str,
        door_id: str,
        issued_by: str = "dashboard",
    ) -> bool:
        """
        Publish a lock command to the specified door.

        Returns True if the MQTT publish succeeded, False otherwise.
        """
        return self._send_command(store_id, door_id, DoorAction.LOCK, issued_by)

    def unlock_door(
        self,
        store_id: str,
        door_id: str,
        issued_by: str = "dashboard",
    ) -> bool:
        """
        Publish an unlock command to the specified door.

        Returns True if the MQTT publish succeeded, False otherwise.
        """
        return self._send_command(store_id, door_id, DoorAction.UNLOCK, issued_by)

    def get_door_status(self, store_id: str, door_id: str) -> dict:
        """
        Return the last known state of a door from the in-memory cache.

        If no status has been received yet, returns state='unknown'.
        """
        key = self._key(store_id, door_id)
        with self._lock:
            entry = self._state.get(key)

        if entry is None:
            return {
                "store_id": store_id,
                "door_id": door_id,
                "state": DoorState.UNKNOWN,
                "last_command": None,
                "last_command_by": None,
                "last_command_at": None,
                "correlation_id": None,
            }
        return dict(entry)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_command(
        self,
        store_id: str,
        door_id: str,
        action: DoorAction,
        issued_by: str,
    ) -> bool:
        correlation_id = str(uuid.uuid4())
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        topic = MQTTClient.door_command_topic(store_id, door_id)
        payload = {
            "action": action.value,
            "issued_by": issued_by,
            "timestamp": timestamp,
            "correlation_id": correlation_id,
        }
        success = self._mqtt.publish(topic, payload)
        if success:
            logger.info(
                "Door command sent | store=%s door=%s action=%s correlation_id=%s",
                store_id,
                door_id,
                action.value,
                correlation_id,
            )
            # Optimistically update state with the command details.
            key = self._key(store_id, door_id)
            with self._lock:
                prev = self._state.get(key, {"state": DoorState.UNKNOWN})
                self._state[key] = {
                    "store_id": store_id,
                    "door_id": door_id,
                    "state": prev.get("state", DoorState.UNKNOWN),
                    "last_command": action.value,
                    "last_command_by": issued_by,
                    "last_command_at": timestamp,
                    "correlation_id": correlation_id,
                }
        else:
            logger.error(
                "Failed to send door command | store=%s door=%s action=%s",
                store_id,
                door_id,
                action.value,
            )
        return success

    def _handle_status_message(self, topic: str, payload: dict) -> None:
        """Callback invoked when a status message arrives on MQTT."""
        store_id = payload.get("store_id")
        door_id = payload.get("door_id")
        raw_state = payload.get("state", "unknown")

        if not store_id or not door_id:
            # Attempt to parse store_id / door_id from the topic pattern:
            # vantag/stores/{store_id}/doors/{door_id}/status
            parts = topic.split("/")
            if len(parts) >= 6:
                store_id = parts[2]
                door_id = parts[4]
            else:
                logger.warning(
                    "Received status message with missing identifiers | topic=%s", topic
                )
                return

        try:
            state = DoorState(raw_state)
        except ValueError:
            state = DoorState.UNKNOWN

        key = self._key(store_id, door_id)
        with self._lock:
            prev = self._state.get(key, {})
            self._state[key] = {
                "store_id": store_id,
                "door_id": door_id,
                "state": state,
                "last_command": prev.get("last_command"),
                "last_command_by": prev.get("last_command_by"),
                "last_command_at": prev.get("last_command_at"),
                "correlation_id": prev.get("correlation_id"),
            }

        logger.info(
            "Door status updated | store=%s door=%s state=%s",
            store_id,
            door_id,
            state.value,
        )

    @staticmethod
    def _key(store_id: str, door_id: str) -> str:
        return f"{store_id}/{door_id}"


# ---------------------------------------------------------------------------
# FastAPI router helper
# ---------------------------------------------------------------------------


_door_controller_ref: DoorController | None = None


def set_controller(controller: DoorController) -> None:
    """Inject the DoorController instance used by the static door_router."""
    global _door_controller_ref  # noqa: PLW0603
    _door_controller_ref = controller


def _get_controller() -> DoorController:
    if _door_controller_ref is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Door controller not yet initialised.",
        )
    return _door_controller_ref


def create_door_router(controller: DoorController) -> APIRouter:  # kept for compat
    """Thin wrapper — now delegates to the module-level ``door_router``."""
    set_controller(controller)
    return door_router


# ---------------------------------------------------------------------------
# Module-level router (registered at app creation, controller injected later)
# ---------------------------------------------------------------------------

door_router = APIRouter(prefix="/api/doors", tags=["Doors"])


@door_router.post(
    "/{store_id}/{door_id}/lock",
    response_model=DoorStatusResponse,
    summary="Lock a door (One-Tap Lock)",
)
async def lock_door(
    store_id: str,
    door_id: str,
    body: DoorCommandRequest,
) -> DoorStatusResponse:
    controller = _get_controller()
    ok = controller.lock_door(store_id, door_id, issued_by=body.issued_by)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to publish lock command to MQTT broker.",
        )
    raw = controller.get_door_status(store_id, door_id)
    return DoorStatusResponse(**raw)


@door_router.post(
    "/{store_id}/{door_id}/unlock",
    response_model=DoorStatusResponse,
    summary="Unlock a door",
)
async def unlock_door(
    store_id: str,
    door_id: str,
    body: DoorCommandRequest,
) -> DoorStatusResponse:
    controller = _get_controller()
    ok = controller.unlock_door(store_id, door_id, issued_by=body.issued_by)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to publish unlock command to MQTT broker.",
        )
    raw = controller.get_door_status(store_id, door_id)
    return DoorStatusResponse(**raw)


@door_router.get(
    "/{store_id}/{door_id}/status",
    response_model=DoorStatusResponse,
    summary="Get current door status",
)
async def get_door_status(store_id: str, door_id: str) -> DoorStatusResponse:
    controller = _get_controller()
    raw = controller.get_door_status(store_id, door_id)
    return DoorStatusResponse(**raw)


def _build_door_router() -> APIRouter:
    """Kept for backwards compatibility — returns the module-level router."""
    return door_router
