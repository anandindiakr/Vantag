import { useState, useRef, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ChevronRight,
  Home,
  Store,
  Loader2,
  AlertOctagon,
  Phone,
  Filter,
  X,
  Maximize2,
} from 'lucide-react';
import clsx from 'clsx';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useVantagStore, EventType, VantagEvent } from '../store/useVantagStore';
import { useCameras } from '../hooks/useApi';

const EVENT_TYPE_OPTIONS: Array<{ value: EventType | 'all'; label: string }> = [
  { value: 'all',             label: 'All Events' },
  { value: 'sweep',           label: 'Sweep' },
  { value: 'dwell',           label: 'Dwell' },
  { value: 'watchlist_match', label: 'Watchlist' },
  { value: 'theft_attempt',   label: 'Theft Attempt' },
  { value: 'queue_alert',     label: 'Queue Alert' },
  { value: 'door_event',      label: 'Door Event' },
];

interface ZonePoint { x: number; y: number }

export default function CameraView() {
  const { storeId = '', cameraId = '' } = useParams<{ storeId: string; cameraId: string }>();

  const [eventFilter, setEventFilter]   = useState<EventType | 'all'>('all');
  const [zonePoints, setZonePoints]     = useState<ZonePoint[]>([]);
  const [isDrawing, setIsDrawing]       = useState(false);
  const [intercomLoading, setIntercomLoading] = useState(false);
  const [fullscreen, setFullscreen]     = useState(false);

  const overlayRef = useRef<SVGSVGElement>(null);

  const { data: cameras = [] } = useCameras(storeId);
  const allEvents              = useVantagStore((s) => s.recentEvents);

  const camera = cameras.find((c) => c.id === cameraId);

  // Events for this camera (optionally filtered)
  const cameraEvents: VantagEvent[] = allEvents.filter(
    (e) => e.cameraId === cameraId && (eventFilter === 'all' || e.type === eventFilter)
  );

  // Zone editor: click on SVG overlay to add polygon points
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (!isDrawing) return;
      const rect   = e.currentTarget.getBoundingClientRect();
      const x      = ((e.clientX - rect.left) / rect.width) * 100;
      const y      = ((e.clientY - rect.top)  / rect.height) * 100;
      setZonePoints((prev) => [...prev, { x, y }]);
    },
    [isDrawing]
  );

  const clearZone = () => setZonePoints([]);

  const saveZone = async () => {
    if (zonePoints.length < 3) {
      toast.error('Zone needs at least 3 points');
      return;
    }
    try {
      await axios.post(`/api/cameras/${cameraId}/zones`, { points: zonePoints });
      toast.success('Zone saved successfully');
      setIsDrawing(false);
      clearZone();
    } catch {
      toast.error('Failed to save zone');
    }
  };

  const handleIntercom = async () => {
    setIntercomLoading(true);
    try {
      await axios.post(`/api/cameras/${cameraId}/intercom/initiate`);
      toast.success('Intercom session initiated');
    } catch {
      toast.error('Failed to initiate intercom');
    } finally {
      setIntercomLoading(false);
    }
  };

  if (!camera && cameras.length > 0) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 text-slate-400">
        <AlertOctagon size={40} />
        <p>Camera not found</p>
        <Link to={`/store/${storeId}`} className="text-vantag-red hover:underline text-sm">
          Back to Store
        </Link>
      </div>
    );
  }

  const streamSrc = `/api/cameras/${cameraId}/stream`;

  return (
    <div className="min-h-screen bg-vantag-dark pb-10">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <nav className="flex items-center gap-1.5 text-sm text-slate-400 mb-1">
          <Link to="/" className="flex items-center gap-1 hover:text-slate-200">
            <Home size={14} /> Dashboard
          </Link>
          <ChevronRight size={12} />
          <Link
            to={`/store/${storeId}`}
            className="flex items-center gap-1 hover:text-slate-200"
          >
            <Store size={14} /> {storeId}
          </Link>
          <ChevronRight size={12} />
          <span className="text-slate-100 font-medium">{camera?.name ?? cameraId}</span>
        </nav>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-100">{camera?.name ?? 'Camera'}</h1>
            <p className="text-xs text-slate-400">{camera?.location ?? 'Location unknown'}</p>
          </div>
          <div className="flex items-center gap-2">
            {camera && (
              <div className="flex items-center gap-1.5">
                <div
                  className={clsx(
                    'w-2 h-2 rounded-full',
                    camera.online ? 'bg-vantag-green animate-pulse' : 'bg-slate-600'
                  )}
                />
                <span className="text-xs text-slate-400">
                  {camera.online ? 'LIVE' : 'OFFLINE'}
                </span>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="px-6 py-6">
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* ── Stream + Zone Editor ───────────────────────────────── */}
          <div className="xl:col-span-2 space-y-4">
            {/* Stream */}
            <div
              className={clsx(
                'relative bg-black rounded-xl overflow-hidden border border-slate-700/60',
                fullscreen && 'fixed inset-0 z-50 rounded-none border-0'
              )}
            >
              {cameras.length === 0 ? (
                <div className="flex items-center justify-center aspect-video bg-slate-900">
                  <Loader2 size={28} className="animate-spin text-slate-500" />
                </div>
              ) : (
                <img
                  src={streamSrc}
                  alt={`Camera ${cameraId} stream`}
                  className="w-full aspect-video object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              )}

              {/* Zone editor SVG overlay */}
              <svg
                ref={overlayRef}
                className="absolute inset-0 w-full h-full"
                onClick={handleOverlayClick}
                style={{ cursor: isDrawing ? 'crosshair' : 'default' }}
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
              >
                {zonePoints.length > 2 && (
                  <polygon
                    points={zonePoints.map((p) => `${p.x},${p.y}`).join(' ')}
                    fill="rgba(239,68,68,0.2)"
                    stroke="#EF4444"
                    strokeWidth="0.5"
                    strokeDasharray="2 1"
                  />
                )}
                {zonePoints.map((p, i) => (
                  <circle
                    key={i}
                    cx={p.x}
                    cy={p.y}
                    r="1.2"
                    fill="#EF4444"
                  />
                ))}
              </svg>

              {/* Controls overlay */}
              <div className="absolute top-3 right-3 flex gap-2">
                <button
                  onClick={() => setFullscreen((f) => !f)}
                  className="p-1.5 rounded-lg bg-black/50 text-white hover:bg-black/70 transition-colors"
                  title="Toggle fullscreen"
                >
                  <Maximize2 size={15} />
                </button>
              </div>

              {/* Fullscreen close */}
              {fullscreen && (
                <button
                  onClick={() => setFullscreen(false)}
                  className="absolute top-4 left-4 p-2 rounded-full bg-black/60 text-white hover:bg-black/80"
                >
                  <X size={18} />
                </button>
              )}
            </div>

            {/* Actions bar */}
            <div className="flex items-center gap-3 flex-wrap">
              {/* Intercom */}
              <button
                onClick={handleIntercom}
                disabled={intercomLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors disabled:opacity-60"
              >
                {intercomLoading ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : (
                  <Phone size={15} />
                )}
                Intercom
              </button>

              {/* Zone editor toggles */}
              {!isDrawing ? (
                <button
                  onClick={() => setIsDrawing(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-vantag-card border border-slate-600 hover:border-slate-400 text-slate-300 text-sm font-medium transition-colors"
                >
                  Draw Zone
                </button>
              ) : (
                <>
                  <button
                    onClick={saveZone}
                    className="px-4 py-2 rounded-lg bg-vantag-green/20 border border-vantag-green/40 text-vantag-green text-sm font-medium hover:bg-vantag-green/30 transition-colors"
                  >
                    Save Zone
                  </button>
                  <button
                    onClick={() => { clearZone(); setIsDrawing(false); }}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-700/50 text-slate-400 text-sm hover:text-slate-200 transition-colors"
                  >
                    <X size={14} /> Cancel
                  </button>
                  {zonePoints.length > 0 && (
                    <button
                      onClick={clearZone}
                      className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      Clear points
                    </button>
                  )}
                </>
              )}

              {isDrawing && (
                <span className="text-xs text-slate-500 italic">
                  Click on the video to add polygon points ({zonePoints.length} added)
                </span>
              )}
            </div>

            {/* Current detection zones */}
            {camera && camera.zones.length > 0 && (
              <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-4">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Configured Zones
                </h3>
                <div className="flex flex-wrap gap-2">
                  {camera.zones.map((z) => (
                    <span
                      key={z.id}
                      className="text-xs px-2 py-1 rounded-lg bg-slate-700/50 border border-slate-600/50 text-slate-300"
                    >
                      {z.name} ({z.type})
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Right Panel ────────────────────────────────────────── */}
          <div className="space-y-4">
            {/* Current detections */}
            {cameraEvents.length > 0 && (
              <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-4">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                  Active Detections
                </h3>
                <div className="space-y-2">
                  {cameraEvents.slice(0, 5).map((ev) => (
                    <div
                      key={ev.id}
                      className="flex items-center justify-between bg-slate-800/60 rounded-lg px-3 py-2"
                    >
                      <span className="text-xs text-slate-200 capitalize">
                        {ev.type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-xs text-slate-400">
                        {Math.round(ev.confidence * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Event history */}
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
                <h3 className="text-sm font-semibold text-slate-100">Event History</h3>
                <div className="flex items-center gap-1.5">
                  <Filter size={13} className="text-slate-500" />
                  <select
                    value={eventFilter}
                    onChange={(e) => setEventFilter(e.target.value as EventType | 'all')}
                    className="bg-slate-800 border border-slate-600 rounded text-xs text-slate-300 px-2 py-1 focus:outline-none focus:border-slate-400"
                  >
                    {EVENT_TYPE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="divide-y divide-slate-700/40 max-h-[400px] overflow-y-auto scrollbar-thin">
                {cameraEvents.length === 0 ? (
                  <div className="py-8 text-center text-slate-500 text-sm">No events</div>
                ) : (
                  cameraEvents.map((ev) => (
                    <div key={ev.id} className="px-4 py-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-200 capitalize">
                          {ev.type.replace(/_/g, ' ')}
                        </span>
                        <span
                          className={clsx(
                            'text-xs px-1.5 py-0.5 rounded font-semibold',
                            ev.severity === 'HIGH' || ev.severity === 'CRITICAL'
                              ? 'bg-vantag-red/20 text-vantag-red'
                              : ev.severity === 'MEDIUM'
                              ? 'bg-vantag-amber/20 text-vantag-amber'
                              : 'bg-slate-700/50 text-slate-400'
                          )}
                        >
                          {ev.severity}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">{ev.description}</p>
                      <p className="text-xs text-slate-600 mt-0.5">
                        {new Date(ev.ts).toLocaleString()}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
