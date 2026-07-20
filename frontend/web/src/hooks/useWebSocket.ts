import { useEffect, useRef, useState, useCallback } from 'react';
import {
  useVantagStore,
  VantagEvent,
  RiskScore,
  QueueStatus,
  DoorState,
  EventType,
  Severity,
} from '../store/useVantagStore';

// Dynamically derive WS URL from the current page host so it works
// in dev (Vite proxy → localhost:8800) and production (nginx → backend) alike.
// Appends the JWT token as a query param for WebSocket authentication.
const _proto  = window.location.protocol === 'https:' ? 'wss' : 'ws';
const _BASE_WS_URL = `${_proto}://${window.location.host}/ws/events`;

function _getWsUrl(): string {
  const token = localStorage.getItem('vantag_token');
  if (token) {
    return `${_BASE_WS_URL}?token=${encodeURIComponent(token)}`;
  }
  return _BASE_WS_URL;
}

const INITIAL_RECONNECT_DELAY = 1000;   // 1 s
const MAX_RECONNECT_DELAY     = 30_000; // 30 s
const MAX_RECONNECT_ATTEMPTS  = 20;

interface UseWebSocketReturn {
  connected: boolean;
  lastEvent: VantagEvent | null;
  error: string | null;
  reconnectCount: number;
}

type IncomingMessage =
  | { type: 'event';        payload: VantagEvent }
  | { type: 'risk_score';   payload: RiskScore }
  | { type: 'queue_status'; payload: QueueStatus }
  | { type: 'door_state';   payload: { doorId: string; state: DoorState } }
  | { type: 'ping' }
  | IncidentMessage;

/**
 * Real backend incident broadcast (edge agent / pipeline / demo router).
 * Flat snake_case shape — mapped into a VantagEvent before hitting the store.
 */
interface IncidentMessage {
  type: 'incident';
  incident_id?: string;
  id?: string;
  store_id?: string;
  camera_id?: string;
  camera_name?: string;
  event_type?: string;
  severity?: string;
  description?: string;
  confidence?: number;
  occurred_at?: string;
  timestamp?: string;
  snapshot_url?: string | null;
  is_demo?: boolean;
  metadata?: Record<string, unknown>;
}

const _VALID_SEVERITIES: ReadonlySet<string> = new Set([
  'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'STAFF',
]);

function mapIncidentToEvent(m: IncidentMessage): VantagEvent {
  const sev = String(m.severity ?? 'MEDIUM').toUpperCase();
  return {
    id: m.incident_id ?? m.id ?? `inc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    storeId: m.store_id ?? '',
    cameraId: m.camera_id ?? '',
    cameraName: m.camera_name ?? m.camera_id ?? 'Camera',
    type: (m.event_type ?? 'tamper') as EventType,
    severity: (_VALID_SEVERITIES.has(sev) ? sev : 'MEDIUM') as Severity,
    description: m.description ?? `${(m.event_type ?? 'event').replace(/_/g, ' ')} detected`,
    confidence: typeof m.confidence === 'number' ? m.confidence : 0,
    ts: m.occurred_at ?? m.timestamp ?? new Date().toISOString(),
    metadata: { ...(m.metadata ?? {}), is_demo: Boolean(m.is_demo) },
    thumbnailUrl: m.snapshot_url ?? undefined,
  };
}

export function useWebSocket(): UseWebSocketReturn {
  const [connected, setConnected]           = useState(false);
  const [lastEvent, setLastEvent]           = useState<VantagEvent | null>(null);
  const [error, setError]                   = useState<string | null>(null);
  const [reconnectCount, setReconnectCount] = useState(0);

  const wsRef              = useRef<WebSocket | null>(null);
  const reconnectDelay     = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimer     = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptCount       = useRef(0);
  const unmounted          = useRef(false);

  const { addEvent, updateRiskScore, setQueueStatus, setDoorState, setWsConnected } =
    useVantagStore.getState();

  const handleMessage = useCallback((raw: string) => {
    try {
      const msg = JSON.parse(raw) as IncomingMessage;
      switch (msg.type) {
        case 'event': {
          addEvent(msg.payload);
          setLastEvent(msg.payload);
          break;
        }
        case 'incident': {
          const mapped = mapIncidentToEvent(msg);
          addEvent(mapped);
          setLastEvent(mapped);
          break;
        }
        case 'risk_score': {
          updateRiskScore(msg.payload.storeId, msg.payload);
          break;
        }
        case 'queue_status': {
          setQueueStatus(msg.payload.storeId, msg.payload);
          break;
        }
        case 'door_state': {
          setDoorState(msg.payload.doorId, msg.payload.state);
          break;
        }
        case 'ping':
          // server keepalive, no action needed
          break;
        default:
          break;
      }
    } catch {
      // malformed message — ignore
    }
  }, [addEvent, updateRiskScore, setQueueStatus, setDoorState]);

  const connect = useCallback(() => {
    if (unmounted.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(_getWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmounted.current) { ws.close(); return; }
        setConnected(true);
        setWsConnected(true);
        setError(null);
        reconnectDelay.current = INITIAL_RECONNECT_DELAY;
        attemptCount.current   = 0;
        setReconnectCount(0);
      };

      ws.onmessage = (ev: MessageEvent) => {
        handleMessage(ev.data as string);
      };

      ws.onerror = () => {
        setError('WebSocket connection error');
      };

      ws.onclose = (ev) => {
        if (unmounted.current) return;
        setConnected(false);
        setWsConnected(false);

        if (ev.code === 1000) return; // clean close
        if (ev.code === 1008) {
          // Policy Violation = auth failure — don't retry
          setError('WebSocket authentication failed. Please refresh the page.');
          return;
        }

        if (attemptCount.current >= MAX_RECONNECT_ATTEMPTS) {
          setError('Max reconnect attempts reached. Refresh to retry.');
          return;
        }

        // Exponential backoff
        const delay = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY);
        reconnectDelay.current = delay;
        attemptCount.current  += 1;
        setReconnectCount(attemptCount.current);

        reconnectTimer.current = setTimeout(connect, delay);
      };
    } catch (err) {
      setError(`Failed to create WebSocket: ${String(err)}`);
    }
  }, [handleMessage, setWsConnected]);

  useEffect(() => {
    unmounted.current = false;
    connect();

    return () => {
      unmounted.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close(1000, 'component unmounted');
    };
  }, [connect]);

  return { connected, lastEvent, error, reconnectCount };
}
