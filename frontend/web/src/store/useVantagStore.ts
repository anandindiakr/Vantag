import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';

// ─── Domain Interfaces ────────────────────────────────────────────────────────

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface Store {
  id: string;
  name: string;
  location: string;
  address: string;
  cameraCount: number;
  active: boolean;
  timezone: string;
  openHours: { open: string; close: string };
}

export interface Camera {
  id: string;
  storeId: string;
  name: string;
  location: string;
  streamUrl: string;
  online: boolean;
  fps: number;
  resolution: string;
  zones: Zone[];
}

export interface Zone {
  id: string;
  name: string;
  points: Array<{ x: number; y: number }>;
  type: 'entry' | 'exit' | 'restricted' | 'checkout' | 'shelf';
}

export interface RiskScore {
  storeId: string;
  score: number;             // 0–100
  severity: Severity;
  factors: RiskFactor[];
  history: Array<{ ts: number; score: number }>;
  computedAt: string;        // ISO timestamp
}

export interface RiskFactor {
  name: string;
  weight: number;
  value: number;
  description: string;
}

export type EventType =
  | 'sweep'
  | 'dwell'
  | 'empty_shelf'
  | 'watchlist_match'
  | 'queue_alert'
  | 'door_event'
  | 'loitering'
  | 'crowd'
  | 'theft_attempt'
  | 'system';

export interface VantagEvent {
  id: string;
  storeId: string;
  cameraId: string;
  cameraName: string;
  type: EventType;
  severity: Severity;
  description: string;
  confidence: number;        // 0–1
  ts: string;                // ISO timestamp
  metadata: Record<string, unknown>;
  thumbnailUrl?: string;
}

export interface QueueStatus {
  storeId: string;
  lanes: QueueLane[];
  updatedAt: string;
}

export interface QueueLane {
  laneId: string;
  name: string;
  depth: number;             // number of people in queue
  waitTimeSec: number;
  open: boolean;
}

export interface WatchlistEntry {
  id: string;
  name: string;
  alertLevel: Severity;
  faceImageUrl?: string;
  notes: string;
  addedAt: string;
  lastMatchAt?: string;
  matchCount: number;
  active: boolean;
}

export interface WatchlistMatch {
  id: string;
  entryId: string;
  entryName: string;
  storeId: string;
  cameraId: string;
  cameraName: string;
  confidence: number;
  thumbnailUrl?: string;
  ts: string;
}

export interface Incident {
  id: string;
  storeId: string;
  storeName: string;
  cameraId: string;
  cameraName: string;
  type: EventType;
  severity: Severity;
  riskScore: number;
  description: string;
  ts: string;
  resolvedAt?: string;
  resolved: boolean;
  reportUrl?: string;
}

export type DoorState = 'locked' | 'unlocked' | 'unknown';

export interface HeatmapData {
  storeId: string;
  grid: number[][];
  rows: number;
  cols: number;
  windowMinutes: number;
  generatedAt: string;
}

// ─── Store Interface ──────────────────────────────────────────────────────────

interface VantagStore {
  // State
  stores: Store[];
  cameras: Camera[];
  recentEvents: VantagEvent[];
  riskScores: Record<string, RiskScore>;
  doorStates: Record<string, DoorState>;
  queueStatus: Record<string, QueueStatus>;
  watchlist: WatchlistEntry[];
  watchlistMatches: WatchlistMatch[];
  incidents: Incident[];
  wsConnected: boolean;
  mqttConnected: boolean;

  // Actions
  setStores: (stores: Store[]) => void;
  setCameras: (cameras: Camera[]) => void;
  updateRiskScore: (storeId: string, score: RiskScore) => void;
  addEvent: (event: VantagEvent) => void;
  setDoorState: (doorId: string, state: DoorState) => void;
  setQueueStatus: (storeId: string, status: QueueStatus) => void;
  setWatchlist: (entries: WatchlistEntry[]) => void;
  addWatchlistEntry: (entry: WatchlistEntry) => void;
  removeWatchlistEntry: (id: string) => void;
  addWatchlistMatch: (match: WatchlistMatch) => void;
  setIncidents: (incidents: Incident[]) => void;
  addIncident: (incident: Incident) => void;
  resolveIncident: (id: string) => void;
  setWsConnected: (connected: boolean) => void;
  setMqttConnected: (connected: boolean) => void;
  clearEvents: () => void;
}

// ─── Store Implementation ─────────────────────────────────────────────────────

const MAX_EVENTS = 50;
const MAX_MATCHES = 100;

export const useVantagStore = create<VantagStore>()(
  devtools(
    subscribeWithSelector((set) => ({
      // ── Initial State ──
      stores: [],
      cameras: [],
      recentEvents: [],
      riskScores: {},
      doorStates: {},
      queueStatus: {},
      watchlist: [],
      watchlistMatches: [],
      incidents: [],
      wsConnected: false,
      mqttConnected: false,

      // ── Actions ──
      setStores: (stores) => set({ stores }, false, 'setStores'),

      setCameras: (cameras) => set({ cameras }, false, 'setCameras'),

      updateRiskScore: (storeId, score) =>
        set(
          (state) => ({
            riskScores: { ...state.riskScores, [storeId]: score },
          }),
          false,
          'updateRiskScore'
        ),

      addEvent: (event) =>
        set(
          (state) => ({
            recentEvents: [event, ...state.recentEvents].slice(0, MAX_EVENTS),
          }),
          false,
          'addEvent'
        ),

      setDoorState: (doorId, state) =>
        set(
          (prev) => ({
            doorStates: { ...prev.doorStates, [doorId]: state },
          }),
          false,
          'setDoorState'
        ),

      setQueueStatus: (storeId, status) =>
        set(
          (state) => ({
            queueStatus: { ...state.queueStatus, [storeId]: status },
          }),
          false,
          'setQueueStatus'
        ),

      setWatchlist: (entries) => set({ watchlist: entries }, false, 'setWatchlist'),

      addWatchlistEntry: (entry) =>
        set(
          (state) => ({ watchlist: [entry, ...state.watchlist] }),
          false,
          'addWatchlistEntry'
        ),

      removeWatchlistEntry: (id) =>
        set(
          (state) => ({ watchlist: state.watchlist.filter((e) => e.id !== id) }),
          false,
          'removeWatchlistEntry'
        ),

      addWatchlistMatch: (match) =>
        set(
          (state) => ({
            watchlistMatches: [match, ...state.watchlistMatches].slice(0, MAX_MATCHES),
          }),
          false,
          'addWatchlistMatch'
        ),

      setIncidents: (incidents) => set({ incidents }, false, 'setIncidents'),

      addIncident: (incident) =>
        set(
          (state) => ({ incidents: [incident, ...state.incidents] }),
          false,
          'addIncident'
        ),

      resolveIncident: (id) =>
        set(
          (state) => ({
            incidents: state.incidents.map((inc) =>
              inc.id === id
                ? { ...inc, resolved: true, resolvedAt: new Date().toISOString() }
                : inc
            ),
          }),
          false,
          'resolveIncident'
        ),

      setWsConnected: (connected) =>
        set({ wsConnected: connected }, false, 'setWsConnected'),

      setMqttConnected: (connected) =>
        set({ mqttConnected: connected }, false, 'setMqttConnected'),

      clearEvents: () => set({ recentEvents: [] }, false, 'clearEvents'),
    })),
    { name: 'VantagStore' }
  )
);
