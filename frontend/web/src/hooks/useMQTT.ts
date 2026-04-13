import { useEffect, useRef, useState, useCallback } from 'react';
import mqtt, { MqttClient, IClientOptions } from 'mqtt';
import toast from 'react-hot-toast';
import { useVantagStore, DoorState } from '../store/useVantagStore';

// Mosquitto WebSocket listener on port 9001 (exposed by Docker).
// Path /mqtt is the standard WebSocket path for Mosquitto 2.x.
const MQTT_BROKER_URL  = 'ws://localhost:9001/mqtt';
const DOOR_STATUS_TOPIC = 'vantag/+/doors/+/status';
const DOOR_CMD_TOPIC    = (storeId: string, doorId: string) =>
  `vantag/${storeId}/doors/${doorId}/command`;

interface MqttOptions extends IClientOptions {
  clientId: string;
  keepalive: number;
  reconnectPeriod: number;
  connectTimeout: number;
}

interface UseMQTTReturn {
  connected: boolean;
  publishDoorCommand: (
    storeId: string,
    doorId: string,
    action: 'lock' | 'unlock'
  ) => void;
}

export function useMQTT(): UseMQTTReturn {
  const [connected, setConnected] = useState(false);
  const clientRef                 = useRef<MqttClient | null>(null);
  const { setDoorState, setMqttConnected } = useVantagStore.getState();

  useEffect(() => {
    const options: MqttOptions = {
      clientId:        `vantag-dashboard-${Math.random().toString(16).slice(2, 10)}`,
      keepalive:       60,
      reconnectPeriod: 3000,
      connectTimeout:  10_000,
      clean:           true,
    };

    const client = mqtt.connect(MQTT_BROKER_URL, options);
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

    client.on('reconnect', () => {
      setConnected(false);
    });

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
      // Topic pattern: vantag/<storeId>/doors/<doorId>/status
      const parts = topic.split('/');
      if (parts.length === 5 && parts[2] === 'doors' && parts[4] === 'status') {
        const doorId = `${parts[1]}:${parts[3]}`;
        try {
          const data = JSON.parse(payload.toString()) as { state: DoorState };
          setDoorState(doorId, data.state);
        } catch {
          // malformed payload
        }
      }
    });

    return () => {
      client.end(true);
    };
  }, [setDoorState, setMqttConnected]);

  const publishDoorCommand = useCallback(
    (storeId: string, doorId: string, action: 'lock' | 'unlock') => {
      const client = clientRef.current;
      if (!client || !client.connected) {
        toast.error('MQTT not connected — cannot send door command');
        return;
      }

      const topic   = DOOR_CMD_TOPIC(storeId, doorId);
      const payload = JSON.stringify({
        action,
        doorId,
        storeId,
        ts: new Date().toISOString(),
      });

      client.publish(topic, payload, { qos: 1, retain: false }, (err) => {
        if (err) {
          toast.error(`Door command failed: ${err.message}`);
        } else {
          toast.success(`Door ${doorId} ${action} command sent`);
        }
      });
    },
    []
  );

  return { connected, publishDoorCommand };
}
