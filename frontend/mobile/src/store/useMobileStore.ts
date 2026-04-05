/**
 * src/store/useMobileStore.ts
 * ===========================
 * Zustand global store for the Vantag mobile app.
 *
 * Mirrors the shape of the web store but with mobile-specific additions:
 *  - Persistent offline cache via expo-secure-store (last known risk scores)
 *  - Settings for backend / MQTT URLs
 *  - Read-state tracking for alert badges
 */

import { create } from "zustand";
import * as SecureStore from "expo-secure-store";

// ─── Type Definitions ────────────────────────────────────────────────────────

export type Severity = "LOW" | "MEDIUM" | "HIGH";

export interface Store {
  store_id: string;
  name: string;
  location: string;
  camera_count: number;
  active_cameras: number;
  risk_score: number;
  risk_severity: Severity;
  last_event_at: string | null;
}

export interface Camera {
  camera_id: string;
  name: string;
  location: string;
  store_id: string;
  rtsp_url: string;
  resolution_width: number;
  resolution_height: number;
  fps_target: number;
  enabled: boolean;
  status: "online" | "offline" | "degraded";
}

export interface VantagEvent {
  id: string;
  type: string;
  camera_id: string;
  store_id: string;
  timestamp: string;
  severity: Severity;
  description: string;
  payload: Record<string, unknown>;
  read: boolean;
}

export interface RiskScore {
  store_id: string;
  score: number;
  severity: Severity;
  event_counts: Record<string, number>;
  computed_at: string;
}

export interface DoorState {
  door_id: string;
  store_id: string;
  state: "locked" | "unlocked" | "unknown" | "error";
  last_command_at: string | null;
}

export interface QueueStatus {
  lane_id: string;
  camera_id: string;
  store_id: string;
  queue_depth: number;
  avg_wait_seconds: number;
  status: "normal" | "busy" | "critical";
}

export interface AppSettings {
  backendUrl: string;
  mqttBrokerUrl: string;
  pushNotificationsEnabled: boolean;
}

// ─── Secure Store key ────────────────────────────────────────────────────────

const SECURE_STORE_RISK_KEY = "vantag_risk_scores_cache";

// ─── Store State & Actions ────────────────────────────────────────────────────

interface MobileStoreState {
  // Data
  stores: Store[];
  cameras: Camera[];
  recentEvents: VantagEvent[];
  riskScores: Record<string, RiskScore>;
  doorStates: Record<string, DoorState>;
  queueStatuses: QueueStatus[];

  // Connection state
  wsConnected: boolean;
  wsError: string | null;

  // Settings
  settings: AppSettings;

  // Actions
  setStores: (stores: Store[]) => void;
  setCameras: (cameras: Camera[]) => void;
  updateRiskScore: (score: RiskScore) => void;
  addEvent: (event: VantagEvent) => void;
  markEventRead: (id: string) => void;
  markAllRead: () => void;
  setDoorState: (doorState: DoorState) => void;
  setQueueStatuses: (statuses: QueueStatus[]) => void;
  setWsConnected: (connected: boolean) => void;
  setWsError: (error: string | null) => void;
  updateSettings: (partial: Partial<AppSettings>) => void;

  // Persistence
  loadCachedRiskScores: () => Promise<void>;
  persistRiskScores: () => Promise<void>;
}

// ─── Default Settings ─────────────────────────────────────────────────────────

const DEFAULT_SETTINGS: AppSettings = {
  backendUrl: "http://192.168.1.10:8000",
  mqttBrokerUrl: "ws://192.168.1.10:9001",
  pushNotificationsEnabled: true,
};

// ─── Max events retained in memory ───────────────────────────────────────────

const MAX_EVENTS = 200;

// ─── Store Implementation ─────────────────────────────────────────────────────

export const useMobileStore = create<MobileStoreState>((set, get) => ({
  stores: [],
  cameras: [],
  recentEvents: [],
  riskScores: {},
  doorStates: {},
  queueStatuses: [],
  wsConnected: false,
  wsError: null,
  settings: DEFAULT_SETTINGS,

  // ── Data setters ──────────────────────────────────────────────────────────

  setStores: (stores) => set({ stores }),

  setCameras: (cameras) => set({ cameras }),

  updateRiskScore: (score) =>
    set((state) => ({
      riskScores: { ...state.riskScores, [score.store_id]: score },
    })),

  addEvent: (event) =>
    set((state) => {
      const events = [event, ...state.recentEvents].slice(0, MAX_EVENTS);
      return { recentEvents: events };
    }),

  markEventRead: (id) =>
    set((state) => ({
      recentEvents: state.recentEvents.map((e) =>
        e.id === id ? { ...e, read: true } : e
      ),
    })),

  markAllRead: () =>
    set((state) => ({
      recentEvents: state.recentEvents.map((e) => ({ ...e, read: true })),
    })),

  setDoorState: (doorState) =>
    set((state) => ({
      doorStates: {
        ...state.doorStates,
        [`${doorState.store_id}/${doorState.door_id}`]: doorState,
      },
    })),

  setQueueStatuses: (statuses) => set({ queueStatuses: statuses }),

  // ── WebSocket ─────────────────────────────────────────────────────────────

  setWsConnected: (wsConnected) => set({ wsConnected }),
  setWsError: (wsError) => set({ wsError }),

  // ── Settings ──────────────────────────────────────────────────────────────

  updateSettings: (partial) =>
    set((state) => ({ settings: { ...state.settings, ...partial } })),

  // ── SecureStore persistence ───────────────────────────────────────────────

  loadCachedRiskScores: async () => {
    try {
      const raw = await SecureStore.getItemAsync(SECURE_STORE_RISK_KEY);
      if (raw) {
        const cached: Record<string, RiskScore> = JSON.parse(raw);
        set({ riskScores: cached });
      }
    } catch {
      // Cache miss or parse error — silently ignore
    }
  },

  persistRiskScores: async () => {
    try {
      const { riskScores } = get();
      await SecureStore.setItemAsync(
        SECURE_STORE_RISK_KEY,
        JSON.stringify(riskScores)
      );
    } catch {
      // Storage failure — non-fatal
    }
  },
}));
