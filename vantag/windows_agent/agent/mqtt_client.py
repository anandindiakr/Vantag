"""
MQTT client for receiving door control commands from Vantag backend.
"""
import logging
import json
import paho.mqtt.client as mqtt

log = logging.getLogger("vantag.mqtt")


class VantagMqttClient:
    def __init__(self, host: str, port: int, tenant_id: str, api_key: str,
                 username: str = "vantag_edge", password: str = "", tls: bool = None):
        self.host = host
        self.port = port
        self.tenant_id = tenant_id
        # TLS is required on the public broker port (8883). Auto-enable when the
        # caller doesn't specify and the port is the standard MQTTS port.
        self.tls = (port == 8883) if tls is None else tls
        self._client = mqtt.Client(client_id=f"vantag-win-{tenant_id[:8]}", clean_session=True)
        self._client.username_pw_set(username=username, password=(password or api_key))
        if self.tls:
            try:
                self._client.tls_set()  # use system CA bundle (broker has a valid LE cert)
            except Exception as e:  # noqa: BLE001
                log.warning(f"MQTT TLS setup failed: {e}")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=2, max_delay=60)

    def connect(self):
        try:
            self._client.connect(self.host, self.port, keepalive=60)
            self._client.loop_start()
            log.info(f"MQTT connecting to {self.host}:{self.port} (tls={self.tls})")
        except Exception as e:
            log.warning(f"MQTT connect failed ({e}) — door control disabled, monitoring continues")

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            topic = f"vantag/{self.tenant_id}/door/cmd"
            client.subscribe(topic)
            log.info(f"MQTT connected, subscribed to {topic}")
        else:
            log.error(f"MQTT connect error rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            log.warning(f"MQTT disconnected rc={rc}, will auto-reconnect")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            door_id = payload.get("door_id")
            action = payload.get("action")  # "lock" | "unlock"
            log.info(f"Door command received: door={door_id} action={action}")
            # TODO: trigger GPIO / relay / smart lock integration here
        except Exception as e:
            log.error(f"MQTT message parse error: {e}")
