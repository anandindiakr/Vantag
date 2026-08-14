"""
MQTT client for the Vantag Edge Agent (door / access control).

Receives door lock/unlock commands from the backend on the canonical topic
namespace and actuates a configurable relay, then publishes the resulting
door state back so the dashboard's One-Tap Lock reflects real state.

Canonical topic namespace (matches ``backend/mqtt/client.py``):

    vantag/stores/{store_id}/doors/{door_id}/command   <- backend publishes
    vantag/stores/{store_id}/doors/{door_id}/status    <- agent publishes

The agent subscribes with a wildcard (``vantag/stores/+/doors/+/command``) so
a command reaches it regardless of how the backend derives ``store_id``
(site id vs legacy location slug). ``store_id`` and ``door_id`` are parsed
from the topic; the payload only needs ``action``.

Relay backends
--------------
Configured via ``AgentConfig.door_control``:

    {"relay_type": "simulate" | "http" | "gpio",
     "http_url": "http://192.168.1.50/relay",   # for relay_type=http
     "gpio_pin": 17}                             # for relay_type=gpio

* ``simulate`` (default) — logs the command and publishes the resulting
  state back after a short delay. Used when no physical relay is wired yet.
* ``http`` — POSTs ``{door_id, action}`` to ``http_url``. Treats any 2xx as
  success.
* ``gpio`` — drives a relay pin via ``RPi.GPIO`` (Linux/SBC only; best-effort,
  falls back to simulate when the library/pin isn't available).
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("vantag.mqtt")

COMMAND_TOPIC = "vantag/stores/+/doors/+/command"


def _status_topic(store_id: str, door_id: str) -> str:
    return f"vantag/stores/{store_id}/doors/{door_id}/status"


class _SimulateRelay:
    """Logs commands and pretends the relay actuated (no hardware)."""

    def actuate(self, door_id: str, action: str) -> bool:
        log.info("Relay (simulate) | door=%s action=%s", door_id, action)
        return True


class _HttpRelay:
    """Drives a LAN/Wi-Fi relay board via a simple HTTP endpoint."""

    def __init__(self, url: str, timeout: float = 5.0):
        self._url = url
        self._timeout = timeout

    def actuate(self, door_id: str, action: str) -> bool:
        import urllib.request

        req = urllib.request.Request(
            self._url,
            data=json.dumps({"door_id": door_id, "action": action}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return 200 <= resp.status < 300
        except Exception as exc:  # noqa: BLE001
            log.error("Relay (http) request failed | url=%s error=%s", self._url, exc)
            return False


class _GpioRelay:
    """Drives a relay via RPi.GPIO (SBCs only). Falls back to simulate."""

    def __init__(self, pin: int):
        self._pin = int(pin)
        self._gpio = None
        try:
            import RPi.GPIO as GPIO  # type: ignore[import]

            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.OUT)
            self._gpio = GPIO
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Relay (gpio) unavailable (%s) — falling back to simulate.", exc
            )
            self._gpio = None

    def actuate(self, door_id: str, action: str) -> bool:
        if self._gpio is None:
            log.info("Relay (gpio->simulate) | door=%s action=%s", door_id, action)
            return True
        try:
            self._gpio.output(self._pin, self._gpio.HIGH if action == "unlock" else self._gpio.LOW)
            log.info("Relay (gpio) | door=%s action=%s pin=%d", door_id, action, self._pin)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Relay (gpio) failed: %s", exc)
            return False


def _build_relay(door_control: dict):
    cfg = door_control or {}
    kind = str(cfg.get("relay_type", "simulate")).lower()
    if kind == "http":
        url = cfg.get("http_url")
        if url:
            return _HttpRelay(str(url))
        log.warning("door_control.relay_type=http but no http_url — using simulate.")
    elif kind == "gpio":
        return _GpioRelay(cfg.get("gpio_pin", 17))
    return _SimulateRelay()


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
        self._relay = _build_relay(self.door_control)
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
