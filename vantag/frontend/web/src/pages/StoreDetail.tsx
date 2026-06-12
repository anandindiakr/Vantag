import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ChevronRight,
  Home,
  Camera,
  Clock,
  ShoppingCart,
  DoorClosed,
  AlertOctagon,
  CheckCircle2,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import {
  useStore,
  useRiskScore,
  useHeatmap,
  useIncidents,
  useQueueStatus,
  useCameras,
} from '../hooks/useApi';
import { useVantagStore, Severity } from '../store/useVantagStore';
import AlertFeed from '../components/AlertFeed';
import HeatmapCanvas from '../components/HeatmapCanvas';
import OneTapLock from '../components/OneTapLock';

const HEATMAP_WINDOWS = [15, 30, 60, 120] as const;

function SeverityBadge({ s }: { s: Severity }) {
  return (
    <span
      className={clsx(
        'px-2.5 py-1 rounded-lg text-sm font-bold border',
        s === 'HIGH' || s === 'CRITICAL'
          ? 'bg-vantag-red/15 text-vantag-red border-vantag-red/30'
          : s === 'MEDIUM'
          ? 'bg-vantag-amber/15 text-vantag-amber border-vantag-amber/30'
          : 'bg-vantag-green/15 text-vantag-green border-vantag-green/30'
      )}
    >
      {s}
    </span>
  );
}

export default function StoreDetail() {
  const { storeId = '' } = useParams<{ storeId: string }>();
  const [heatmapWindow, setHeatmapWindow] = useState<number>(30);
  const [incidentPage]                    = useState(1);

  const { data: store,     isLoading: storeLoading }    = useStore(storeId);
  const { data: risk,      isLoading: riskLoading }     = useRiskScore(storeId);
  const { data: heatmap,   isLoading: heatmapLoading }  = useHeatmap(storeId, heatmapWindow);
  const { data: incidents, isLoading: incLoading }      = useIncidents(storeId, incidentPage);
  const { data: queues }                                 = useQueueStatus();
  const { data: cameras = [] }                          = useCameras(storeId);
  const riskScores = useVantagStore((s) => s.riskScores);

  const liveRisk = riskScores[storeId] ?? risk;

  const queueStatus = queues?.find((q) => q.storeId === storeId);

  // Mock door IDs derived from cameras (real implementation uses store config)
  const doorIds = cameras.slice(0, 3).map((_, i) => ({
    doorId: `door-${i + 1}`,
    label:  `Door ${i + 1}`,
  }));

  if (storeLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 size={32} className="animate-spin text-vantag-red" />
      </div>
    );
  }

  if (!store) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 text-slate-400">
        <AlertOctagon size={40} />
        <p>Store not found</p>
        <Link to="/" className="text-vantag-red hover:underline text-sm">Back to Dashboard</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-vantag-dark pb-10">
      {/* ── Header / Breadcrumb ────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <nav className="flex items-center gap-1.5 text-sm text-slate-400 mb-1">
          <Link to="/" className="flex items-center gap-1 hover:text-slate-200 transition-colors">
            <Home size={14} /> Dashboard
          </Link>
          <ChevronRight size={12} />
          <span className="text-slate-100 font-medium">{store.name}</span>
        </nav>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-100">{store.name}</h1>
            <p className="text-xs text-slate-400">{store.address}</p>
          </div>
          {liveRisk && <SeverityBadge s={liveRisk.severity} />}
        </div>
      </header>

      <div className="px-6 py-6 space-y-8">
        {/* ── Risk Score Gauge ────────────────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Risk Assessment
          </h2>
          <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-6 flex items-center gap-8">
            {riskLoading ? (
              <Loader2 size={24} className="animate-spin text-slate-500" />
            ) : liveRisk ? (
              <>
                <div className="text-center">
                  <div
                    className={clsx(
                      'text-7xl font-extrabold tabular-nums',
                      liveRisk.severity === 'HIGH' || liveRisk.severity === 'CRITICAL'
                        ? 'text-vantag-red'
                        : liveRisk.severity === 'MEDIUM'
                        ? 'text-vantag-amber'
                        : 'text-vantag-green'
                    )}
                  >
                    {liveRisk.score}
                  </div>
                  <p className="text-xs text-slate-400 mt-1">/ 100</p>
                </div>
                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-2">
                    <SeverityBadge s={liveRisk.severity} />
                    <span className="text-xs text-slate-500">
                      Updated {new Date(liveRisk.computedAt).toLocaleTimeString()}
                    </span>
                  </div>
                  {/* Risk factors */}
                  <div className="space-y-1 mt-2">
                    {liveRisk.factors.slice(0, 4).map((f) => (
                      <div key={f.name} className="flex items-center gap-2">
                        <span className="text-xs text-slate-400 w-32 truncate">{f.name}</span>
                        <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-vantag-red rounded-full"
                            style={{ width: `${Math.min(100, f.value * 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-slate-500 w-10 text-right">
                          {(f.value * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <p className="text-slate-500 text-sm">No risk data available</p>
            )}
          </div>
        </section>

        {/* ── Camera Grid ─────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Camera size={14} /> Camera Feeds
            </h2>
            <span className="text-xs text-slate-500">{cameras.length} cameras</span>
          </div>
          {cameras.length === 0 ? (
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-8 text-center text-slate-500 text-sm">
              No cameras found for this store
            </div>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              {cameras.map((cam) => (
                <Link
                  key={cam.id}
                  to={`/store/${storeId}/camera/${cam.id}`}
                  className="group relative bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden aspect-video hover:border-vantag-red/50 transition-colors"
                >
                  {/* MJPEG stream */}
                  <img
                    src={`/api/cameras/${cam.id}/stream`}
                    alt={cam.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src =
                        'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180"><rect fill="%231E293B" width="320" height="180"/><text fill="%23475569" font-family="sans-serif" font-size="14" text-anchor="middle" x="160" y="95">No Signal</text></svg>';
                    }}
                  />
                  {/* Overlay */}
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-slate-200 truncate">{cam.name}</span>
                      <div className="flex items-center gap-1">
                        <div
                          className={clsx(
                            'w-1.5 h-1.5 rounded-full',
                            cam.online ? 'bg-vantag-green' : 'bg-slate-500'
                          )}
                        />
                        <span className="text-xs text-slate-400">{cam.online ? 'LIVE' : 'OFF'}</span>
                      </div>
                    </div>
                  </div>
                  {/* Hover overlay */}
                  <div className="absolute inset-0 bg-vantag-red/10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <span className="text-xs text-white font-medium bg-black/40 px-2 py-1 rounded">
                      Full View
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        {/* ── Heatmap + Queue row ───────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Heatmap */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
                Zone Heatmap
              </h2>
              <div className="flex gap-1">
                {HEATMAP_WINDOWS.map((w) => (
                  <button
                    key={w}
                    onClick={() => setHeatmapWindow(w)}
                    className={clsx(
                      'text-xs px-2 py-1 rounded transition-colors',
                      heatmapWindow === w
                        ? 'bg-vantag-red text-white'
                        : 'bg-slate-700/50 text-slate-400 hover:text-slate-200'
                    )}
                  >
                    {w}m
                  </button>
                ))}
              </div>
            </div>
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-4 flex items-center justify-center min-h-[220px]">
              {heatmapLoading ? (
                <Loader2 size={24} className="animate-spin text-slate-500" />
              ) : heatmap ? (
                <HeatmapCanvas
                  gridData={heatmap.grid}
                  width={380}
                  height={220}
                />
              ) : (
                <p className="text-slate-500 text-sm">No heatmap data</p>
              )}
            </div>
          </section>

          {/* Queue Monitor */}
          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <ShoppingCart size={14} /> Queue Monitor
            </h2>
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-4 space-y-3 min-h-[220px]">
              {!queueStatus ? (
                <p className="text-slate-500 text-sm text-center pt-8">No queue data</p>
              ) : (
                queueStatus.lanes.map((lane) => (
                  <div
                    key={lane.laneId}
                    className="flex items-center justify-between bg-slate-800/60 rounded-lg px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={clsx(
                          'w-2 h-2 rounded-full',
                          lane.open ? 'bg-vantag-green' : 'bg-slate-600'
                        )}
                      />
                      <span className="text-sm text-slate-200">{lane.name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1">
                        <Clock size={12} className="text-slate-500" />
                        <span className="text-xs text-slate-400">
                          {Math.round(lane.waitTimeSec / 60)}m wait
                        </span>
                      </div>
                      <span
                        className={clsx(
                          'text-xs font-bold px-2 py-0.5 rounded',
                          lane.depth > 5
                            ? 'bg-vantag-red/20 text-vantag-red'
                            : lane.depth > 2
                            ? 'bg-vantag-amber/20 text-vantag-amber'
                            : 'bg-vantag-green/20 text-vantag-green'
                        )}
                      >
                        {lane.depth} in queue
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* ── Door Controls ────────────────────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <DoorClosed size={14} /> Door Controls
          </h2>
          {doorIds.length === 0 ? (
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-6 text-slate-500 text-sm text-center">
              No door controllers found
            </div>
          ) : (
            <div className="flex flex-wrap gap-4">
              {doorIds.map(({ doorId, label }) => (
                <OneTapLock key={doorId} storeId={storeId} doorId={doorId} doorLabel={label} />
              ))}
            </div>
          )}
        </section>

        {/* ── Event Timeline + Incidents ───────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Live event feed */}
          <AlertFeed storeId={storeId} maxItems={50} />

          {/* Recent incidents */}
          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Recent Incidents
            </h2>
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden">
              {incLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 size={20} className="animate-spin text-slate-500" />
                </div>
              ) : (incidents?.items ?? []).length === 0 ? (
                <div className="flex items-center justify-center py-10 gap-2 text-slate-500 text-sm">
                  <CheckCircle2 size={16} className="text-vantag-green" />
                  No incidents recorded
                </div>
              ) : (
                <div className="divide-y divide-slate-700/40">
                  {(incidents?.items ?? []).slice(0, 10).map((inc) => (
                    <div key={inc.id} className="flex items-start gap-3 px-4 py-3">
                      <div
                        className={clsx(
                          'w-2 h-2 rounded-full mt-2 shrink-0',
                          inc.severity === 'HIGH' || inc.severity === 'CRITICAL'
                            ? 'bg-vantag-red'
                            : inc.severity === 'MEDIUM'
                            ? 'bg-vantag-amber'
                            : 'bg-vantag-green'
                        )}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-slate-200 truncate">{inc.description}</p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {inc.cameraName} · {new Date(inc.ts).toLocaleString()}
                        </p>
                      </div>
                      <span
                        className={clsx(
                          'text-xs font-semibold px-2 py-0.5 rounded shrink-0',
                          inc.severity === 'HIGH' || inc.severity === 'CRITICAL'
                            ? 'bg-vantag-red/20 text-vantag-red'
                            : inc.severity === 'MEDIUM'
                            ? 'bg-vantag-amber/20 text-vantag-amber'
                            : 'bg-vantag-green/20 text-vantag-green'
                        )}
                      >
                        {inc.severity}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
