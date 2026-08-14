"""
MQTT client for the Vantag Edge Agent (door / access control).

Receives door lock/unlock commands from the backend on the canonical topic
namespace, actuates a pluggable relay (see ``agent/relay.py``), and publishes
the resulting door state back so the dashboard reflects real state.

Canonical topic namespace (matches ``backend/mqtt/client.py``):

    vantag/stores/{store_id}/doors/{door_id}/command   <- backend publishes
    vantag/stores/{store_id}/doors/{door_id}/status    <- agent publishes

The agent subscribes with a wildcard (``vantag/stores/+/doors/+/command``) so
a command reaches it regardless of how the backend derives ``store_id``.
``store_id`` / ``door_id`` are parsed from the topic; ``tenant_id`` is added
to the status payload so the backend can route the update to the right
dashboard.
"""

import json
import logging
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from .relay import build_relay

log = logging.getLogger("vantag.mqtt")

COMMAND_TOPIC = "vantag/stores/+/doors/+/command"


def _status_topic(store_id: str, door_id: str) -> str:
    return f"vantag/stores/{store_id}/doors/{door_id}/status"


class VantagMqttClient:
    """Subscribes to door commands, actuates the relay, publishes status."""

    def __init__(
        self,
        host: str,
        port: int,
        tenant_id: str,
        api_key: str,
        username: str = "vantag_edge",
        password: str = "",
        tls: bool = None,
        door_control: dict = None,
    ):
        self.host = host
        self.port = port
        self.tenant_id = tenant_id
        self.door_control = dict(door_control or {})
        self._relay = build_relay(self.door_control)
        # TLS is required on the public MQTTS port (8883). Auto-enable when the
        # caller doesn't specify and the port is the standard MQTTS port.
        self.tls = (port == 8883) if tls is None else bool(tls)
        self._client = mqtt.Client(
            client_id=f"vantag-win-{tenant_id[:8]}", clean_session=True
        )
        self._client.username_pw_set(username=username, password=(password or api_key))
        if self.tls:
            try:
                self._client.tls_set()  # system CA bundle (broker has a valid cert)
            except Exception as exc:  # noqa: BLE001
                log.warning("MQTT TLS setup failed: %s", exc)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=2, max_delay=60)
        self._connected = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self):
        try:
            self._client.connect(self.host, self.port, keepalive=60)
            self._client.loop_start()
            log.info(
                "MQTT connecting to %s:%d (tls=%s) — door control",
                self.host, self.port, self.tls,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "MQTT connect failed (%s) — door control disabled, monitoring continues",
                exc,
            )

    def disconnect(self):
        self._connected.clear()
        self._client.loop_stop()
        self._client.disconnect()

    # ------------------------------------------------------------------
    # Paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(COMMAND_TOPIC, qos=1)
            self._connected.set()
            log.info("MQTT connected, subscribed to %s", COMMAND_TOPIC)
        else:
            log.error("MQTT connect error rc=%d", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected.clear()
        if rc != 0:
            log.warning("MQTT disconnected rc=%d, will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception as exc:  # noqa: BLE001
            log.error("MQTT message parse error: %s", exc)
            return

        # Topic: vantag/stores/{store_id}/doors/{door_id}/command
        parts = msg.topic.split("/")
        store_id = parts[2] if len(parts) > 2 else None
        door_id = parts[4] if len(parts) > 4 else None

        # Backwards-compatible payload fallback when door_id isn't in the topic.
        action = payload.get("action")
        if not door_id:
            door_id = payload.get("door_id")
        if not store_id:
            store_id = payload.get("store_id", self.tenant_id)
        if action not in ("lock", "unlock"):
            log.warning("Ignoring MQTT message with unknown action | topic=%s", msg.topic)
            return
        if not door_id:
            log.warning("Ignoring MQTT door command without door_id | topic=%s", msg.topic)
            return

        log.info("Door command received: store=%s door=%s action=%s", store_id, door_id, action)

        ok = self._relay.actuate(door_id, action)
        self._publish_status(store_id, door_id, action if ok else "error")

    # ------------------------------------------------------------------
    # Status publishing
    # ------------------------------------------------------------------

    def _publish_status(self, store_id: str, door_id: str, state: str):
        payload = {
            "state": state,
            "door_id": door_id,
            "store_id": store_id,
            "tenant_id": self.tenant_id,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            self._client.publish(
                _status_topic(store_id, door_id),
                json.dumps(payload),
                qos=1,
                retain=False,
            )
            log.info("Door status published: store=%s door=%s state=%s", store_id, door_id, state)
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to publish door status: %s", exc)
