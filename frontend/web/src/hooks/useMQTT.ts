import { useEffect, useRef, useState } from 'react';
import mqtt, { MqttClient, IClientOptions } from 'mqtt';
import { useVantagStore, DoorState } from '../store/useVantagStore';

// Canonical door status topic (matches backend/mqtt/client.py).
const DOOR_STATUS_TOPIC = 'vantag/stores/+/doors/+/status';

// In local development Mosquitto exposes its WebSocket listener on port 9001.
// In production the browser connects over the same origin (wss://) and nginx
// proxies `/mqtt` to the broker — this avoids the mixed-content block that
// broke the old hardcoded `ws://localhost:9001/mqtt` URL.
function resolveBrokerUrl(): string {
  const host = window.location.hostname;
  const isLocal =
    host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0';
  if (isLocal) {
    return 'ws://localhost:9001/mqtt';
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/mqtt`;
}

interface MqttOptions extends IClientOptions {
  clientId: string;
  keepalive: number;
  reconnectPeriod: number;
  connectTimeout: number;
}

export interface UseMQTTReturn {
  connected: boolean;
}

export function useMQTT(): UseMQTTReturn {
  const [connected, setConnected] = useState(false);
  const clientRef = useRef<MqttClient | null>(null);

  useEffect(() => {
    const { setDoorState, setMqttConnected } = useVantagStore.getState();

    const options: MqttOptions = {
      clientId: `vantag-dashboard-${Math.random().toString(16).slice(2, 10)}`,
      keepalive: 60,
      reconnectPeriod: 3000,
      connectTimeout: 10_000,
      clean: true,
    };

    let client: MqttClient;
    try {
      client = mqtt.connect(resolveBrokerUrl(), options);
    } catch {
      setConnected(false);
      return;
    }
    clientRef.current = client;

    client.on('connect', () => {
      setConnected(true);
      setMqttConnected(true);
      client.subscribe(DOOR_STATUS_TOPIC, { qos: 1 }, (err) => {
        if (err) {
          console.error('[MQTT] Failed to subscribe to door status:', err);
        }
      });
    });

    client.on('reconnect', () => setConnected(false));
    client.on('offline', () => {
      setConnected(false);
      setMqttConnected(false);
    });
    client.on('error', (err) => {
      console.error('[MQTT] Error:', err);
      setConnected(false);
      setMqttConnected(false);
    });

    client.on('message', (topic: string, payload: Buffer) => {
      // Topic: vantag/stores/{storeId}/doors/{doorId}/status
      const parts = topic.split('/');
      if (parts.length === 6 && parts[1] === 'stores' && parts[3] === 'doors' && parts[5] === 'status') {
        const doorId = `${parts[2]}:${parts[4]}`;
        try {
          const data = JSON.parse(payload.toString()) as { state: DoorState };
          if (data.state) setDoorState(doorId, data.state);
        } catch {
          // malformed payload
        }
      }
    });

    return () => {
      client.end(true);
    };
  }, []);

  return { connected };
}
