import { useMemo } from 'react';
import { Store, Camera, Monitor, AlertTriangle, CheckCircle2, Wifi } from 'lucide-react';
import clsx from 'clsx';
import { useVantagStore } from '../store/useVantagStore';
import { useStores, useCameras } from '../hooks/useApi';
import RiskScoreCard from '../components/RiskScoreCard';
import AlertFeed from '../components/AlertFeed';

function StatCard({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  accent?: 'red' | 'amber' | 'green' | 'default';
}) {
  const accentCls =
    accent === 'red'
      ? 'text-vantag-red'
      : accent === 'amber'
      ? 'text-vantag-amber'
      : accent === 'green'
      ? 'text-vantag-green'
      : 'text-slate-100';

  return (
    <div className="bg-vantag-card border border-slate-700/60 rounded-xl px-5 py-4 flex items-center gap-4">
      <div className="text-slate-400">{icon}</div>
      <div>
        <p className={clsx('text-2xl font-bold tabular-nums', accentCls)}>{value}</p>
        <p className="text-xs text-slate-400 mt-0.5">{label}</p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const wsConnected  = useVantagStore((s) => s.wsConnected);
  const riskScores   = useVantagStore((s) => s.riskScores);
  const recentEvents = useVantagStore((s) => s.recentEvents);

  const { data: stores = [], isLoading: storesLoading } = useStores();
  const { data: cameras = [] }                          = useCameras();

  // Sorted stores: highest risk first
  const sortedStores = useMemo(() => {
    return [...stores].sort((a, b) => {
      const scoreA = riskScores[a.id]?.score ?? 0;
      const scoreB = riskScores[b.id]?.score ?? 0;
      return scoreB - scoreA;
    });
  }, [stores, riskScores]);

  const activeAlerts = useMemo(
    () => Object.values(riskScores).filter((r) => r.severity === 'HIGH' || r.severity === 'CRITICAL').length,
    [riskScores]
  );

  const camerasOnline = useMemo(() => (cameras as { online: boolean }[]).filter((c) => c.online).length, [cameras]);

  const allClear = activeAlerts === 0 && stores.length > 0;

  return (
    <div className="min-h-screen bg-vantag-dark">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-100">Operations Dashboard</h1>
            <p className="text-xs text-slate-400 mt-0.5">Multi-store overview · Real-time</p>
          </div>

          {/* Live indicator */}
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
        {/* ── Alert Banner ───────────────────────────────────────────────── */}
        {stores.length > 0 && (
          <div
            className={clsx(
              'flex items-center gap-3 px-5 py-3 rounded-xl border text-sm font-medium',
              allClear
                ? 'bg-vantag-green/10 border-vantag-green/30 text-vantag-green'
                : 'bg-vantag-red/10 border-vantag-red/30 text-vantag-red'
            )}
          >
            {allClear ? (
              <CheckCircle2 size={18} />
            ) : (
              <AlertTriangle size={18} className="animate-pulse" />
            )}
            {allClear
              ? 'All Clear — No active high-risk alerts across all stores'
              : `${activeAlerts} store${activeAlerts !== 1 ? 's' : ''} with active HIGH / CRITICAL alerts`}
          </div>
        )}

        {/* ── Stats Bar ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard icon={<Store size={22} />}   label="Total Stores"   value={stores.length} />
          <StatCard
            icon={<AlertTriangle size={22} />}
            label="Active Alerts"
            value={activeAlerts}
            accent={activeAlerts > 0 ? 'red' : 'green'}
          />
          <StatCard
            icon={<Camera size={22} />}
            label="Cameras Online"
            value={`${camerasOnline} / ${cameras.length}`}
            accent={camerasOnline < cameras.length ? 'amber' : 'green'}
          />
          <StatCard
            icon={<Monitor size={22} />}
            label="Live Events"
            value={recentEvents.length}
            accent="default"
          />
        </div>

        {/* ── Main Grid ──────────────────────────────────────────────────── */}
        <div className="flex gap-6">
          {/* Store cards */}
          <div className="flex-1 min-w-0">
            {storesLoading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div
                    key={i}
                    className="bg-vantag-card border border-slate-700/60 rounded-xl h-60 animate-pulse"
                  />
                ))}
              </div>
            ) : sortedStores.length === 0 ? (
              <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
                No stores configured. Check backend connection.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {sortedStores.map((store) => (
                  <RiskScoreCard
                    key={store.id}
                    store={store}
                    riskScore={riskScores[store.id]}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Event feed sidebar */}
          <div className="hidden lg:block w-80 shrink-0">
            <AlertFeed maxItems={20} className="h-full" />
          </div>
        </div>
      </div>
    </div>
  );
}
