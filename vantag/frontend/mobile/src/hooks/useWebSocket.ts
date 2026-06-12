/**
 * src/hooks/useWebSocket.ts
 * =========================
 * Mobile WebSocket hook for real-time event streaming.
 *
 * Features:
 *  - Connects to the backend WebSocket at `{backendUrl}/ws`
 *  - Auto-reconnect with exponential back-off (1 s → 2 s → 4 s … max 30 s)
 *  - Parses incoming JSON messages and updates the Zustand store
 *  - Returns `{ connected: boolean, error: string | null }`
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { AppState, AppStateStatus } from "react-native";
import { useMobileStore, VantagEvent, RiskScore } from "../store/useMobileStore";

const MAX_BACKOFF_MS = 30_000;

function buildWsUrl(backendUrl: string): string {
  // Replace http(s):// with ws(s)://
  return backendUrl.replace(/^http/, "ws") + "/ws";
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function useWebSocket(backendUrl: string): {
  connected: boolean;
  error: string | null;
  lastEvent: VantagEvent | null;
} {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState<VantagEvent | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef<number>(1000);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);

  const { addEvent, updateRiskScore, setDoorState, setWsConnected, setWsError } =
    useMobileStore.getState();

  // ── Message parser ──────────────────────────────────────────────────────────

  const handleMessage = useCallback((data: string) => {
    try {
      const msg = JSON.parse(data) as Record<string, unknown>;
      const type = msg.type as string | undefined;

      if (!type) return;

      if (type === "risk_score") {
        const score = msg as unknown as RiskScore;
        updateRiskScore(score);
        useMobileStore.getState().persistRiskScores();
        return;
      }

      if (type === "door_status") {
        const payload = msg.payload as Record<string, unknown> | undefined;
        if (payload) {
          setDoorState({
            door_id: (payload.door_id as string) ?? "",
            store_id: (payload.store_id as string) ?? (msg.store_id as string) ?? "",
            state: (payload.state as "locked" | "unlocked" | "unknown" | "error") ?? "unknown",
            last_command_at: (payload.last_command_at as string) ?? null,
          });
        }
        return;
      }

      // All other event types → add to event feed
      const event: VantagEvent = {
        id: (msg.id as string) ?? generateId(),
        type: type,
        camera_id: (msg.camera_id as string) ?? "",
        store_id: (msg.store_id as string) ?? "",
        timestamp: (msg.timestamp as string) ?? new Date().toISOString(),
        severity: (msg.severity as "LOW" | "MEDIUM" | "HIGH") ?? "LOW",
        description: (msg.description as string) ?? describeEvent(type),
        payload: (msg.payload as Record<string, unknown>) ?? {},
        read: false,
      };
      addEvent(event);
      setLastEvent(event);
    } catch {
      // Malformed message — ignore
    }
  }, []);

  // ── Connection logic ────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    const url = buildWsUrl(backendUrl);
    let ws: WebSocket;

    try {
      ws = new WebSocket(url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setWsError(msg);
      scheduleReconnect();
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) {
        ws.close();
        return;
      }
      backoffRef.current = 1000; // reset backoff on successful connect
      setConnected(true);
      setError(null);
      setWsConnected(true);
      setWsError(null);
    };

    ws.onmessage = (event) => {
      handleMessage(event.data as string);
    };

    ws.onerror = () => {
      // onclose fires after onerror — handle reconnect there
    };

    ws.onclose = (event) => {
      if (unmountedRef.current) return;
      setConnected(false);
      setWsConnected(false);
      const reason = event.reason || `Code ${event.code}`;
      setError(`Disconnected: ${reason}`);
      setWsError(`Disconnected: ${reason}`);
      scheduleReconnect();
    };
  }, [backendUrl, handleMessage]);

  const scheduleReconnect = useCallback(() => {
    if (unmountedRef.current) return;
    const delay = backoffRef.current;
    backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
    reconnectTimerRef.current = setTimeout(() => {
      if (!unmountedRef.current) connect();
    }, delay);
  }, [connect]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  // ── App state handler (pause WS when app backgrounded) ───────────────────

  useEffect(() => {
    unmountedRef.current = false;

    // Load cached risk scores before connecting
    useMobileStore.getState().loadCachedRiskScores();

    connect();

    const sub = AppState.addEventListener(
      "change",
      (nextState: AppStateStatus) => {
        if (nextState === "active") {
          if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
            backoffRef.current = 1000;
            connect();
          }
        } else if (nextState === "background") {
          // Keep connection alive but stop reconnect timer to save battery
          if (reconnectTimerRef.current)
            clearTimeout(reconnectTimerRef.current);
        }
      }
    );

    return () => {
      unmountedRef.current = true;
      disconnect();
      sub.remove();
    };
  }, [backendUrl]);

  return { connected, error, lastEvent };
}

// ─── Helper ──────────────────────────────────────────────────────────────────

function describeEvent(type: string): string {
  const descriptions: Record<string, string> = {
    sweeping: "Product sweeping detected",
    dwell: "Prolonged dwell time detected",
    empty_shelf: "Empty shelf detected",
    watchlist_match: "Watchlist face match",
    queue: "Queue depth threshold exceeded",
    accident: "Slip / fall accident detected",
    staff_alert: "Staff behaviour alert",
    tamper: "Camera tamper detected",
    pos_anomaly: "POS anomaly detected",
  };
  return descriptions[type] ?? `Event: ${type}`;
}
