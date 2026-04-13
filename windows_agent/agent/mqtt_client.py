"""
MQTT client for receiving door control commands from Vantag backend.
"""
import logging
import json
import paho.mqtt.client as mqtt

log = logging.getLogger("vantag.mqtt")


class VantagMqttClient:
    def __init__(self, host: str, port: int, tenant_id: str, api_key: str):
        self.host = host
        self.port = port
        self.tenant_id = tenant_id
        self._client = mqtt.Client(client_id=f"vantag-win-{tenant_id[:8]}", clean_session=True)
        self._client.username_pw_set(username="vantag", password=api_key)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=2, max_delay=60)

    def connect(self):
        try:
            self._client.connect(self.host, self.port, keepalive=60)
            self._client.loop_start()
            log.info(f"MQTT connecting to {self.host}:{self.port}")
        except Exception as e:
            log.error(f"MQTT connect failed: {e}")

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
