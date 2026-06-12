"""
backend/mqtt/client.py
======================
Paho-MQTT wrapper for the Vantag platform.

Provides a thin, thread-safe abstraction over ``paho.mqtt.client.Client``
with the following features:
  * Automatic connection and reconnection with exponential back-off.
  * JSON serialisation / deserialisation on publish / subscribe.
  * Named topic-constant helpers.
  * Clean async-compatible shutdown.

Topic constants
---------------
  VANTAG_EVENTS  = "vantag/events/{store_id}"
  DOOR_COMMAND   = "vantag/stores/{store_id}/doors/{door_id}/command"
  DOOR_STATUS    = "vantag/stores/{store_id}/doors/{door_id}/status"
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as paho

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topic constants
# ---------------------------------------------------------------------------

VANTAG_EVENTS: str = "vantag/events/{store_id}"
DOOR_COMMAND: str = "vantag/stores/{store_id}/doors/{door_id}/command"
DOOR_STATUS: str = "vantag/stores/{store_id}/doors/{door_id}/status"

# ---------------------------------------------------------------------------
# Default configuration values
# ---------------------------------------------------------------------------

_DEFAULT_BROKER: str = "localhost"
_DEFAULT_PORT: int = 1883
_DEFAULT_KEEPALIVE: int = 60
_DEFAULT_QOS: int = 1
_DEFAULT_BACKOFF_MAX: float = 60.0  # seconds


# ---------------------------------------------------------------------------
# MQTTClient
# ---------------------------------------------------------------------------


class MQTTClient:
    """
    Thread-safe MQTT client wrapper with automatic reconnection.

    Parameters
    ----------
    broker:
        MQTT broker hostname or IP address.
    port:
        Broker port (default 1883; use 8883 for TLS).
    client_id:
        Unique client identifier.  Defaults to "vantag-backend".
    username / password:
        Optional broker credentials.
    keepalive:
        MQTT keepalive interval in seconds.
    backoff_max:
        Maximum reconnection back-off delay in seconds.

    Usage
    -----
    >>> client = MQTTClient(broker="localhost", port=1883)
    >>> client.connect()
    >>> client.publish("vantag/events/store-1", {"type": "loitering"})
    >>> client.disconnect()
    """

    def __init__(
        self,
        broker: str = _DEFAULT_BROKER,
        port: int = _DEFAULT_PORT,
        client_id: str = "vantag-backend",
        username: Optional[str] = None,
        password: Optional[str] = None,
        keepalive: int = _DEFAULT_KEEPALIVE,
        backoff_max: float = _DEFAULT_BACKOFF_MAX,
    ) -> None:
        self._broker = broker
        self._port = port
        self._keepalive = keepalive
        self._backoff_max = backoff_max

        self._subscriptions: Dict[str, Callable[[str, dict], None]] = {}
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._reconnecting = False  # guard: only one reconnect thread at a time

        self._client = paho.Client(client_id=client_id, protocol=paho.MQTTv311)
        if username:
            self._client.username_pw_set(username, password)

        # Wire paho callbacks.
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Start the MQTT network loop in a background thread and connect to
        the broker.  Returns immediately; use ``wait_connected()`` if you
        need to block until the connection is established.
        """
        self._stop.clear()
        # Let paho handle reconnection internally — this avoids the race-condition
        # where multiple manual reconnect threads each call client.connect() with
        # the same client_id, causing Mosquitto to kick off each previous session.
        self._client.reconnect_delay_set(
            min_delay=1, max_delay=int(self._backoff_max)
        )
        self._client.loop_start()
        self._attempt_connect()
        logger.info(
            "MQTTClient connecting | broker=%s port=%d", self._broker, self._port
        )

    def wait_connected(self, timeout: float = 10.0) -> bool:
        """Block until connected or *timeout* seconds elapse.  Returns True if connected."""
        return self._connected.wait(timeout=timeout)

    def disconnect(self) -> None:
        """Cleanly disconnect from the broker and stop the network loop."""
        self._stop.set()
        self._client.disconnect()
        self._client.loop_stop()
        self._connected.clear()
        logger.info("MQTTClient disconnected.")

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        qos: int = _DEFAULT_QOS,
        retain: bool = False,
    ) -> bool:
        """
        Publish *payload* as JSON to *topic*.

        Returns True if the message was successfully queued, False otherwise.
        """
        if not self._connected.is_set():
            logger.warning(
                "publish skipped – not connected | topic=%s", topic
            )
            return False

        try:
            raw = json.dumps(payload, default=str)
            result = self._client.publish(topic, raw, qos=qos, retain=retain)
            if result.rc != paho.MQTT_ERR_SUCCESS:
                logger.error(
                    "publish failed | topic=%s rc=%d", topic, result.rc
                )
                return False
            logger.debug("Published | topic=%s", topic)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("publish exception | topic=%s error=%s", topic, exc)
            return False

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        callback: Callable[[str, dict], None],
        qos: int = _DEFAULT_QOS,
    ) -> None:
        """
        Subscribe to *topic* and invoke *callback(topic, payload_dict)* on
        each incoming message.  Wildcard topics (+, #) are supported.
        """
        with self._lock:
            self._subscriptions[topic] = callback

        self._client.subscribe(topic, qos=qos)
        logger.info("Subscribed | topic=%s", topic)

    def unsubscribe(self, topic: str) -> None:
        """Remove a subscription."""
        with self._lock:
            self._subscriptions.pop(topic, None)
        self._client.unsubscribe(topic)
        logger.info("Unsubscribed | topic=%s", topic)

    # ------------------------------------------------------------------
    # Convenience topic builders
    # ------------------------------------------------------------------

    @staticmethod
    def events_topic(store_id: str) -> str:
        """Return the formatted events topic for a store."""
        return VANTAG_EVENTS.format(store_id=store_id)

    @staticmethod
    def door_command_topic(store_id: str, door_id: str) -> str:
        """Return the formatted door command topic."""
        return DOOR_COMMAND.format(store_id=store_id, door_id=door_id)

    @staticmethod
    def door_status_topic(store_id: str, door_id: str) -> str:
        """Return the formatted door status topic."""
        return DOOR_STATUS.format(store_id=store_id, door_id=door_id)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    # ------------------------------------------------------------------
    # Internal paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(
        self,
        client: paho.Client,
        userdata: Any,
        flags: dict,
        rc: int,
    ) -> None:
        if rc == paho.CONNACK_ACCEPTED:
            self._connected.set()
            logger.info(
                "MQTT connected | broker=%s port=%d", self._broker, self._port
            )
            # Re-subscribe to all previously registered topics.
            with self._lock:
                for topic in self._subscriptions:
                    client.subscribe(topic)
                    logger.debug("Re-subscribed | topic=%s", topic)
        else:
            logger.error(
                "MQTT connection refused | rc=%d broker=%s", rc, self._broker
            )

    def _on_disconnect(
        self,
        client: paho.Client,
        userdata: Any,
        rc: int,
    ) -> None:
        self._connected.clear()
        if self._stop.is_set():
            return  # Intentional disconnect – do not reconnect.

        if rc != 0:
            logger.warning(
                "MQTT disconnected unexpectedly | rc=%d | paho will auto-reconnect",
                rc,
            )
        # paho's loop_start() + reconnect_delay_set() handles reconnection
        # automatically — no manual reconnect thread needed.

    def _on_message(
        self,
        client: paho.Client,
        userdata: Any,
        msg: paho.MQTTMessage,
    ) -> None:
        topic: str = msg.topic
        try:
            payload: dict = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(
                "Failed to decode MQTT message | topic=%s error=%s", topic, exc
            )
            return

        with self._lock:
            # Match exact topic first, then try wildcard patterns.
            callback = self._subscriptions.get(topic)
            if callback is None:
                for pattern, cb in self._subscriptions.items():
                    if paho.topic_matches_sub(pattern, topic):
                        callback = cb
                        break

        if callback:
            try:
                callback(topic, payload)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "MQTT message callback raised | topic=%s error=%s", topic, exc
                )
        else:
            logger.debug("No handler for topic=%s", topic)

    # ------------------------------------------------------------------
    # Reconnection logic
    # ------------------------------------------------------------------

    def _attempt_connect(self) -> None:
        """Try once to connect; log any exception."""
        try:
            self._client.connect(
                self._broker, self._port, keepalive=self._keepalive
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MQTT connect attempt failed | error=%s", exc)

    def _reconnect_loop(self) -> None:
        """Back-off reconnection loop running in a daemon thread."""
        backoff: float = 1.0
        try:
            while not self._stop.is_set() and not self._connected.is_set():
                logger.info(
                    "MQTT reconnecting in %.1fs | broker=%s", backoff, self._broker
                )
                self._stop.wait(timeout=backoff)
                if self._stop.is_set():
                    break
                self._attempt_connect()
                backoff = min(backoff * 2, self._backoff_max)
        finally:
            with self._lock:
                self._reconnecting = False
