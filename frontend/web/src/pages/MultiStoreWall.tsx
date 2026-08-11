import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  MonitorPlay,
  Plus,
  X,
  Check,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Wifi,
  LayoutGrid,
  Video,
  Store as StoreIcon,
  Camera as CameraIcon,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useStores, useCameras } from '../hooks/useApi';
import { useVantagStore } from '../store/useVantagStore';
import type { Camera } from '../store/useVantagStore';
import CameraTile from '../components/CameraTile';

/* ── Types ─────────────────────────────────────────────────────────────────── */

interface WallTile {
  cameraId: string;
  storeId: string;
}

/* ── Constants ─────────────────────────────────────────────────────────────── */

const STORAGE_KEY = 'vantag_wall_layout_v1';

/** Static Tailwind class per grid size — dynamic class names don't compile. */
const GRID_CLASSES: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4',
};

const LAYOUT_OPTIONS = [1, 2, 3, 4] as const;

/* ── Helpers ───────────────────────────────────────────────────────────────── */

function loadWall(): WallTile[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (t): t is WallTile =>
        !!t && typeof (t as WallTile).cameraId === 'string' && typeof (t as WallTile).storeId === 'string'
    );
  } catch {
    return [];
  }
}

function prettifyStoreId(id: string): string {
  return id.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── Store → camera picker modal ───────────────────────────────────────────── */

interface PickerModalProps {
  stores: { id: string; name: string }[];
  cameras: Camera[];
  /** cameraIds already on the wall (shown as selected) */
  existing: Set<string>;
  onAdd: (cameraIds: string[]) => void;
  onClose: () => void;
}

function PickerModal({ stores, cameras, existing, onAdd, onClose }: PickerModalProps) {
  const [picked, setPicked] = useState<Set<string>>(new Set(existing));
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id ?? '');

  const storeById = useMemo(() => new Map(stores.map((s) => [s.id, s.name])), [stores]);

  useEffect(() => {
    if (selectedStoreId && stores.some((store) => store.id === selectedStoreId)) return;
    setSelectedStoreId(stores[0]?.id ?? '');
  }, [selectedStoreId, stores]);

  const selectedStoreCameras = useMemo(
    () => cameras.filter((camera) => camera.storeId === selectedStoreId),
    [cameras, selectedStoreId]
  );

  const selectStoreCameras = () => {
    if (selectedStoreCameras.length === 0) return;
    setPicked((current) => {
      const next = new Set(current);
      selectedStoreCameras.forEach((camera) => next.add(camera.id));
      return next;
    });
  };

  const selectedStoreName = storeById.get(selectedStoreId) ?? 'this store';
  const selectedStoreUnpickedCount = selectedStoreCameras.filter((camera) => !picked.has(camera.id)).length;

  // Group cameras by their store id for a store → camera tree in the picker.
  const grouped = useMemo(() => {
    const map = new Map<string, { label: string; cameras: Camera[] }>();
    for (const cam of cameras) {
      const sid = cam.storeId || 'unassigned';
      let entry = map.get(sid);
      if (!entry) {
        entry = { label: storeById.get(sid) ?? prettifyStoreId(sid), cameras: [] };
        map.set(sid, entry);
      }
      entry.cameras.push(cam);
    }
    return [...map.entries()].sort((a, b) => a[1].label.localeCompare(b[1].label));
  }, [cameras, storeById]);

  const toggle = (id: string) =>
    setPicked((p) => {
      const next = new Set(p);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const submit = () => {
    const ids = [...picked];
    if (ids.length === 0) return;
    onAdd(ids);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-vantag-card border border-slate-700/60 rounded-2xl w-full max-w-lg shadow-2xl flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/60">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <CameraIcon size={17} className="text-vantag-green" />
            Add Cameras to Wall
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-4 overflow-y-auto space-y-4 scrollbar-thin">
          {stores.length > 0 && (
            <div className="rounded-xl border border-vantag-green/30 bg-vantag-green/5 p-3 space-y-3">
              <div>
                <p className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <StoreIcon size={13} className="text-vantag-green" /> Add an entire store
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Select a store to add all of its cameras at once.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={selectedStoreId}
                  onChange={(event) => setSelectedStoreId(event.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-vantag-green/60"
                  aria-label="Select a store"
                >
                  {stores.map((store) => (
                    <option key={store.id} value={store.id}>{store.name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={selectStoreCameras}
                  disabled={selectedStoreCameras.length === 0 || selectedStoreUnpickedCount === 0}
                  className="shrink-0 rounded-lg bg-vantag-green px-3 py-2 text-xs font-semibold text-slate-900 transition-colors hover:bg-vantag-green/90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Select all ({selectedStoreCameras.length})
                </button>
              </div>
              <p className="text-[11px] text-slate-500">
                {selectedStoreCameras.length === 0
                  ? `${selectedStoreName} has no cameras assigned.`
                  : selectedStoreUnpickedCount > 0
                    ? `${selectedStoreUnpickedCount} camera${selectedStoreUnpickedCount === 1 ? '' : 's'} still need to be selected.`
                    : 'All cameras from this store are already on the wall.'}
              </p>
            </div>
          )}

          {cameras.length === 0 ? (
            <p className="text-sm text-slate-400">
              No cameras yet. Add cameras first, then build your wall.
            </p>
          ) : (
            grouped.map(([sid, group]) => (
              <div key={sid}>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <StoreIcon size={12} /> {group.label}
                  <span className="text-slate-600 font-normal normal-case">({group.cameras.length})</span>
                </p>
                <div className="space-y-1.5">
                  {group.cameras.map((cam) => {
                    const on = picked.has(cam.id);
                    return (
                      <button
                        key={cam.id}
                        onClick={() => toggle(cam.id)}
                        className={clsx(
                          'w-full flex items-center justify-between px-3 py-2.5 rounded-lg border text-left transition-colors',
                          on
                            ? 'bg-vantag-green/10 border-vantag-green/40'
                            : 'bg-slate-800/40 border-slate-700 hover:border-slate-500'
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Video size={14} className={cam.online ? 'text-vantag-green shrink-0' : 'text-slate-600 shrink-0'} />
                          <div className="min-w-0">
                            <p className="text-sm text-slate-100 truncate">{cam.name}</p>
                            <p className="text-xs text-slate-500 truncate">{cam.id}</p>
                          </div>
                        </div>
                        {on && <Check size={16} className="text-vantag-green shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t border-slate-700/60">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-300 hover:text-slate-100">
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={picked.size === 0}
            className="px-4 py-2 text-sm rounded-lg bg-vantag-green text-slate-900 font-medium disabled:opacity-50 flex items-center gap-2"
          >
            Add {picked.size > 0 ? `${picked.size} camera${picked.size > 1 ? 's' : ''}` : ''} to Wall
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Page ──────────────────────────────────────────────────────────────────── */

export default function MultiStoreWall() {
  const wsConnected = useVantagStore((s) => s.wsConnected);
  const riskScores  = useVantagStore((s) => s.riskScores);

  const { data: stores = [], isLoading: storesLoading } = useStores();
  const { data: cameras = [], isLoading: camerasLoading } = useCameras();

  // Persisted wall layout: [{cameraId, storeId}]
  const [tiles, setTiles] = useState<WallTile[]>(loadWall);
  const [cols, setCols]   = useState<number>(3);
  const [showPicker, setShowPicker] = useState(false);
  const [expanded, setExpanded]     = useState<string | null>(null);

  // Persist whenever the wall changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tiles));
    } catch {
      /* storage unavailable — wall just won't persist */
    }
  }, [tiles]);

  // Drop tiles whose camera no longer exists (camera deleted / tenant changed)
  useEffect(() => {
    if (cameras.length === 0) return;
    const valid = new Set(cameras.map((c) => c.id));
    const next  = tiles.filter((t) => valid.has(t.cameraId));
    if (next.length !== tiles.length) setTiles(next);
  }, [cameras, tiles]);

  // Lookups for rendering
  const cameraById = useMemo(() => new Map(cameras.map((c) => [c.id, c])), [cameras]);
  const storeById  = useMemo(() => new Map(stores.map((s) => [s.id, s.name])), [stores]);

  const effectiveCols = Math.min(cols, Math.max(1, tiles.length));
  const gridClass     = GRID_CLASSES[effectiveCols] ?? GRID_CLASSES[3];

  const activeAlerts = useMemo(
    () =>
      Object.values(riskScores).filter(
        (r) => r.severity === 'HIGH' || r.severity === 'CRITICAL'
      ).length,
    [riskScores]
  );

  const camerasOnline = useMemo(() => cameras.filter((c) => c.online).length, [cameras]);
  const allClear      = activeAlerts === 0 && stores.length > 0;

  const addCameras = (cameraIds: string[]) => {
    const existing = new Set(tiles.map((t) => t.cameraId));
    const added: WallTile[] = [];
    for (const id of cameraIds) {
      if (existing.has(id)) continue;
      const cam = cameraById.get(id);
      if (!cam) continue;
      added.push({ cameraId: id, storeId: cam.storeId });
      existing.add(id);
    }
    if (added.length === 0) {
      toast('Those cameras are already on the wall', { icon: 'ℹ️' });
      return;
    }
    setTiles((prev) => [...prev, ...added]);
    toast.success(`${added.length} camera${added.length > 1 ? 's' : ''} added to wall`);
  };

  const removeCamera = (cameraId: string) => {
    setTiles((prev) => prev.filter((t) => t.cameraId !== cameraId));
    if (expanded === cameraId) setExpanded(null);
    toast('Camera removed from wall', { icon: '🗑️' });
  };

  const expandedCamera = expanded ? cameraById.get(expanded) : undefined;

  return (
    <div className="min-h-screen bg-vantag-dark">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
              <MonitorPlay size={20} className="text-vantag-red" /> Multi-Store Live Wall
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">Watch cameras from every store on one screen · Real-time</p>
          </div>
          <div className="flex items-center gap-2">
            <div
              className={clsx(
                'w-2.5 h-2.5 rounded-full',
                wsConnected ? 'bg-vantag-green animate-pulse' : 'bg-slate-600'
              )}
            />
            <span className="text-sm font-medium text-slate-300">
              {wsConnected ? 'LIVE' : 'Disconnected'}
            </span>
            <Wifi size={16} className={wsConnected ? 'text-vantag-green' : 'text-slate-600'} />
          </div>
        </div>
      </header>

      <div className="px-6 py-6 space-y-6">
        {/* ── Alert banner ────────────────────────────────────────────── */}
        {stores.length > 0 && (
          <div
            className={clsx(
              'flex items-center gap-3 px-5 py-3 rounded-xl border text-sm font-medium',
              allClear
                ? 'bg-vantag-green/10 border-vantag-green/30 text-vantag-green'
                : 'bg-vantag-red/10 border-vantag-red/30 text-vantag-red'
            )}
          >
            {allClear ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} className="animate-pulse" />}
            {allClear
              ? 'All Clear — No active high-risk alerts across all stores'
              : `${activeAlerts} store${activeAlerts !== 1 ? 's' : ''} with active HIGH / CRITICAL alerts`}
          </div>
        )}

        {/* ── Toolbar ─────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          {/* Layout selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <LayoutGrid size={13} /> Layout
            </span>
            <div className="flex gap-1 bg-slate-800/60 border border-slate-700/60 rounded-lg p-1">
              {LAYOUT_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => setCols(n)}
                  className={clsx(
                    'px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                    effectiveCols === n
                      ? 'bg-vantag-green text-slate-900'
                      : 'text-slate-400 hover:text-slate-100'
                  )}
                  title={`${n}×${n} grid`}
                >
                  {n}×{n}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={() => setShowPicker(true)}
            className="px-4 py-2 text-sm rounded-lg bg-vantag-green text-slate-900 font-medium flex items-center gap-2 hover:bg-vantag-green/90 transition-colors"
          >
            <Plus size={15} /> Add Cameras
          </button>
        </div>

        {/* ── Stats strip ─────────────────────────────────────────────── */}
        {tiles.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl px-5 py-4 flex items-center gap-4">
              <StoreIcon size={22} className="text-slate-400" />
              <div>
                <p className="text-2xl font-bold tabular-nums text-slate-100">{stores.length}</p>
                <p className="text-xs text-slate-400 mt-0.5">Stores</p>
              </div>
            </div>
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl px-5 py-4 flex items-center gap-4">
              <CameraIcon size={22} className="text-slate-400" />
              <div>
                <p className={clsx('text-2xl font-bold tabular-nums', camerasOnline < cameras.length ? 'text-vantag-amber' : 'text-vantag-green')}>
                  {camerasOnline} / {cameras.length}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">Cameras Online</p>
              </div>
            </div>
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl px-5 py-4 flex items-center gap-4">
              <AlertTriangle size={22} className={activeAlerts > 0 ? 'text-vantag-red' : 'text-slate-400'} />
              <div>
                <p className={clsx('text-2xl font-bold tabular-nums', activeAlerts > 0 ? 'text-vantag-red' : 'text-vantag-green')}>
                  {activeAlerts}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">Active Alerts</p>
              </div>
            </div>
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl px-5 py-4 flex items-center gap-4">
              <MonitorPlay size={22} className="text-slate-400" />
              <div>
                <p className="text-2xl font-bold tabular-nums text-slate-100">{tiles.length}</p>
                <p className="text-xs text-slate-400 mt-0.5">Cameras on Wall</p>
              </div>
            </div>
          </div>
        )}

        {/* ── Wall grid ───────────────────────────────────────────────── */}
        {storesLoading || camerasLoading ? (
          <div className="flex items-center justify-center h-64 gap-2 text-slate-500">
            <Loader2 size={22} className="animate-spin" /> Loading wall…
          </div>
        ) : cameras.length === 0 ? (
          <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-10 text-center">
            <Video size={30} className="text-slate-600 mx-auto mb-3" />
            <p className="text-sm text-slate-300">No cameras configured yet.</p>
            <p className="text-xs text-slate-500 mt-1">
              Add cameras first, then build your multi-store wall.
            </p>
            <Link
              to="/cameras"
              className="inline-block mt-4 text-xs px-3 py-2 rounded-lg bg-slate-700/50 text-slate-200 hover:bg-slate-700 transition-colors"
            >
              Go to Cameras
            </Link>
          </div>
        ) : tiles.length === 0 ? (
          <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-10 text-center">
            <MonitorPlay size={30} className="text-slate-600 mx-auto mb-3" />
            <p className="text-sm text-slate-300">Your wall is empty.</p>
            <p className="text-xs text-slate-500 mt-1">
              Add cameras from any of your {stores.length} store{stores.length === 1 ? '' : 's'} to watch them all on one screen.
            </p>
            <button
              onClick={() => setShowPicker(true)}
              className="inline-flex items-center gap-2 mt-4 text-xs px-3 py-2 rounded-lg bg-vantag-green text-slate-900 font-medium hover:bg-vantag-green/90 transition-colors"
            >
              <Plus size={14} /> Add Cameras
            </button>
          </div>
        ) : (
          <div className={clsx('grid gap-3', gridClass)}>
            {tiles.map((t) => {
              const cam = cameraById.get(t.cameraId);
              if (!cam) return null;
              return (
                <CameraTile
                  key={t.cameraId}
                  camera={cam}
                  storeName={storeById.get(t.storeId) ?? prettifyStoreId(t.storeId)}
                  onRemove={() => removeCamera(t.cameraId)}
                  onExpand={() => setExpanded(t.cameraId)}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* ── Fullscreen overlay ────────────────────────────────────────── */}
      {expanded && expandedCamera && (
        <CameraTile
          camera={expandedCamera}
          storeName={storeById.get(expandedCamera.storeId) ?? prettifyStoreId(expandedCamera.storeId)}
          onExpand={() => setExpanded(null)}
          expanded
        />
      )}

      {/* ── Picker modal ──────────────────────────────────────────────── */}
      {showPicker && (
        <PickerModal
          stores={stores.map((s) => ({ id: s.id, name: s.name }))}
          cameras={cameras}
          existing={new Set(tiles.map((t) => t.cameraId))}
          onAdd={addCameras}
          onClose={() => setShowPicker(false)}
        />
      )}
    </div>
  );
}
