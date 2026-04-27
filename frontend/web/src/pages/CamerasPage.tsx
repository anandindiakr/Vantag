// frontend/web/src/pages/CamerasPage.tsx
// Grid of all cameras with auto-refreshing live snapshots and real-time alerts.

import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Camera, Wifi, WifiOff, AlertTriangle, Maximize2, RefreshCw, Plus } from 'lucide-react';
import clsx from 'clsx';
import { useCameras } from '../hooks/useApi';
import { useVantagStore } from '../store/useVantagStore';

// Auto-refresh snapshot every N ms
const SNAPSHOT_REFRESH_MS = 3000;

function CameraCard({ cam }: { cam: ReturnType<typeof useCameras>['data'] extends (infer T)[] | undefined ? T : never }) {
  const nav = useNavigate();
  const [tick, setTick]         = useState(0);
  const [imgError, setImgError] = useState(false);

  // Refresh snapshot periodically
  useEffect(() => {
    if (!cam.online) return;
    const id = setInterval(() => setTick((t) => t + 1), SNAPSHOT_REFRESH_MS);
    return () => clearInterval(id);
  }, [cam.online]);

  const recentEvents = useVantagStore((s) =>
    s.recentEvents.filter((e) => e.cameraId === cam.id).slice(0, 3)
  );

  const snapshotUrl = `/api/cameras/${cam.id}/snapshot?t=${tick}`;
  const hasAlert    = recentEvents.some((e) => e.severity === 'HIGH' || e.severity === 'CRITICAL');

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'bg-white/3 border rounded-2xl overflow-hidden transition-all cursor-pointer hover:border-violet-500/40 hover:shadow-lg hover:shadow-violet-900/20',
        hasAlert ? 'border-red-500/50 shadow-red-900/20 shadow-lg' : 'border-white/8'
      )}
      onClick={() => nav(`/cameras/${cam.storeId || 'default'}/${cam.id}`)}
    >
      {/* Snapshot / stream */}
      <div className="relative aspect-video bg-black">
        {cam.online && !imgError ? (
          <img
            key={tick}
            src={snapshotUrl}
            alt={cam.name}
            className="w-full h-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-white/20">
            <Camera className="w-10 h-10" />
            <span className="text-xs">{cam.online ? 'No preview' : 'Offline'}</span>
          </div>
        )}

        {/* Live badge */}
        <div className="absolute top-2 left-2 flex items-center gap-1.5">
          {cam.online ? (
            <span className="flex items-center gap-1 bg-black/60 backdrop-blur-sm text-emerald-400 text-[10px] font-bold px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              LIVE
            </span>
          ) : (
            <span className="bg-black/60 text-white/40 text-[10px] px-2 py-0.5 rounded-full">
              OFFLINE
            </span>
          )}
        </div>

        {/* Alert badge */}
        {hasAlert && (
          <div className="absolute top-2 right-2 bg-red-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1 animate-pulse">
            <AlertTriangle className="w-3 h-3" /> ALERT
          </div>
        )}

        {/* Fullscreen hint */}
        <div className="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <Maximize2 className="w-4 h-4 text-white/40" />
        </div>
      </div>

      {/* Info */}
      <div className="p-4">
        <div className="flex items-start justify-between mb-2">
          <div>
            <h3 className="font-semibold text-sm text-white">{cam.name}</h3>
            <p className="text-xs text-white/40 mt-0.5">{cam.location || 'No location set'}</p>
          </div>
          {cam.online
            ? <Wifi className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            : <WifiOff className="w-4 h-4 text-white/20 flex-shrink-0" />}
        </div>

        {/* Stats */}
        <div className="flex gap-3 text-xs text-white/40 mb-3">
          <span>{cam.resolution}</span>
          <span>{cam.fps} FPS target</span>
        </div>

        {/* Recent events */}
        {recentEvents.length > 0 ? (
          <div className="space-y-1">
            {recentEvents.map((ev) => (
              <div key={ev.id} className={clsx(
                'flex items-center justify-between text-xs rounded-lg px-2 py-1',
                ev.severity === 'CRITICAL' ? 'bg-red-500/15 text-red-400' :
                ev.severity === 'HIGH'     ? 'bg-orange-500/15 text-orange-400' :
                                             'bg-white/5 text-white/50'
              )}>
                <span className="capitalize">{ev.type.replace(/_/g, ' ')}</span>
                <span className="font-semibold">{ev.severity}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-white/20 italic">No recent events</p>
        )}
      </div>
    </motion.div>
  );
}

export default function CamerasPage() {
  const { data: cameras = [], isLoading, refetch } = useCameras();
  const online  = cameras.filter((c) => c.online).length;
  const offline = cameras.filter((c) => !c.online).length;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Live Cameras</h1>
          <p className="text-white/40 text-sm mt-1">
            {online} online · {offline} offline · snapshots refresh every {SNAPSHOT_REFRESH_MS / 1000}s
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/cameras/manage"
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 rounded-xl text-sm font-semibold text-white transition-all"
          >
            <Plus className="w-4 h-4" /> Add Camera
          </Link>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-sm transition-all"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>
      </div>

      {/* Status bar */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: 'Total Cameras', value: cameras.length, color: 'text-violet-400' },
          { label: 'Online',        value: online,          color: 'text-emerald-400' },
          { label: 'Offline',       value: offline,         color: 'text-red-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-white/3 border border-white/8 rounded-xl p-4 text-center">
            <p className={clsx('text-3xl font-black', color)}>{value}</p>
            <p className="text-xs text-white/40 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Camera grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-white/30">
          <RefreshCw className="w-6 h-6 animate-spin mr-2" /> Loading cameras...
        </div>
      ) : cameras.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-white/20 gap-4">
          <Camera className="w-12 h-12" />
          <p className="text-sm">No cameras found.</p>
          <Link
            to="/cameras/manage"
            className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 hover:bg-violet-500 rounded-xl text-sm font-semibold text-white transition-all"
          >
            <Plus className="w-4 h-4" /> Add Your First Camera
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {cameras.map((cam) => (
            <CameraCard key={cam.id} cam={cam} />
          ))}
        </div>
      )}
    </div>
  );
}
