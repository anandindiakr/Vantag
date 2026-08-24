import { useState, useRef, useCallback, useEffect } from 'react';
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
  ShieldCheck,
  Clock,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useVantagStore, EventType, VantagEvent } from '../store/useVantagStore';
import { useCameras, api } from '../hooks/useApi';

const EVENT_TYPE_OPTIONS: Array<{ value: EventType | 'all'; label: string }> = [
  { value: 'all',               label: 'All Events' },
  { value: 'shoplifting',       label: 'Shoplifting' },
  { value: 'inventory_movement',label: 'Inventory Move' },
  { value: 'restricted_zone',   label: 'Restricted Zone' },
  { value: 'queue_breach',      label: 'Queue Breach' },
  { value: 'fall_detected',     label: 'Fall Detected' },
  { value: 'loitering',         label: 'Loitering' },
  { value: 'face_match',        label: 'Face Match' },
  { value: 'tamper',            label: 'Camera Tamper' },
  { value: 'jewelry_handover',  label: 'Case Hand Reach' },
  { value: 'jewelry_tray',      label: 'Tray Change' },
  { value: 'grab_and_run',      label: 'Grab & Run' },
];

interface ZonePoint { x: number; y: number }

// Behaviour-based AI detections. OFF by default — the backend drops these
// event types unless enabled here, so no false incidents are generated.
const DETECTION_TOGGLES: Array<{ key: string; label: string; desc: string }> = [
  { key: 'shoplifting',         label: 'Shoplifting',          desc: 'Sweep / concealment motion heuristics' },
  { key: 'loitering',           label: 'Loitering',            desc: 'Person staying in view too long' },
  { key: 'suspicious_behavior', label: 'Suspicious Behavior',  desc: 'Erratic movement patterns' },
  { key: 'crowding',            label: 'Crowding',             desc: 'Too many people in view' },
  { key: 'fall_detected',       label: 'Fall Detection',       desc: 'Person falling / on the ground' },
  { key: 'people_count',        label: 'People Count',         desc: 'Live person counting (People Count page)' },
];

export default function CameraView() {
  const { storeId = '', cameraId = '' } = useParams<{ storeId: string; cameraId: string }>();

  const [eventFilter, setEventFilter]   = useState<EventType | 'all'>('all');
  const [zonePoints, setZonePoints]     = useState<ZonePoint[]>([]);
  const [isDrawing, setIsDrawing]       = useState(false);
  const [intercomLoading, setIntercomLoading] = useState(false);
  const [fullscreen, setFullscreen]     = useState(false);
  const [detections, setDetections]     = useState<Record<string, boolean>>({});
  const [detSaving, setDetSaving]       = useState<string | null>(null);
  const [schedule, setSchedule]         = useState({ enabled: false, start: '09:00', end: '21:00' });
  const [schedSaving, setSchedSaving]   = useState(false);

  const overlayRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!cameraId) return;
    let cancelled = false;
    api
      .get(`/cameras/${cameraId}/detections`)
      .then(({ data }) => {
        if (!cancelled && data?.detections) setDetections(data.detections);
      })
      .catch(() => { /* older backend without toggles — leave all off */ });
    api
      .get(`/cameras/${cameraId}/schedule`)
      .then(({ data }) => {
        if (!cancelled && data?.schedule) {
          setSchedule({
            enabled: !!data.schedule.enabled,
            start: data.schedule.start || '09:00',
            end: data.schedule.end || '21:00',
          });
        }
      })
      .catch(() => { /* older backend without schedule — keep defaults */ });
    return () => { cancelled = true; };
  }, [cameraId]);

  const saveSchedule = async (next: { enabled: boolean; start: string; end: string }) => {
    setSchedSaving(true);
    const prev = schedule;
    setSchedule(next);
    try {
      await api.patch(`/cameras/${cameraId}/schedule`, {
        ...next,
        // Browser's local UTC offset, e.g. IST = +330 (getTimezoneOffset is inverted)
        tz_offset_minutes: -new Date().getTimezoneOffset(),
      });
      toast.success(
        next.enabled
          ? `AI detections scheduled ${next.start}–${next.end} (theft stays on 24/7)`
          : 'Detection schedule disabled — AI detections run 24/7'
      );
    } catch {
      setSchedule(prev);
      toast.error('Failed to save schedule');
    } finally {
      setSchedSaving(false);
    }
  };

  const toggleDetection = async (key: string) => {
    const next = !detections[key];
    setDetSaving(key);
    setDetections((prev) => ({ ...prev, [key]: next }));
    try {
      await api.patch(`/cameras/${cameraId}/detections`, { detections: { [key]: next } });
      toast.success(
        `${DETECTION_TOGGLES.find((d) => d.key === key)?.label ?? key} ${next ? 'enabled' : 'disabled'}`
      );
    } catch {
      setDetections((prev) => ({ ...prev, [key]: !next }));
      toast.error('Failed to save detection setting');
    } finally {
      setDetSaving(null);
    }
  };

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
      // Load the camera's current zone config (and reference resolution) so
      // we merge with existing zones instead of overwriting them.
      const { data: cfg } = await api.get(`/zones/cameras/${cameraId}`);
      const resW = cfg?.resolution?.width  || 1920;
      const resH = cfg?.resolution?.height || 1080;

      // Points are drawn as percentages (0-100) of the video overlay.
      // Convert the polygon's bounding box to pixel coords in the camera's
      // reference resolution — the format the backend zone store expects.
      const xs = zonePoints.map((p) => (p.x / 100) * resW);
      const ys = zonePoints.map((p) => (p.y / 100) * resH);
      const bbox = [
        Math.max(0, Math.round(Math.min(...xs))),
        Math.max(0, Math.round(Math.min(...ys))),
        Math.min(resW, Math.round(Math.max(...xs))),
        Math.min(resH, Math.round(Math.max(...ys))),
      ];

      const zones = cfg?.zones ?? {};
      const existing = zones.people_count_zones ?? [];
      await api.put(`/zones/cameras/${cameraId}`, {
        shelf_zones:      zones.shelf_zones ?? [],
        restricted_zones: zones.restricted_zones ?? [],
        queue_zones:      zones.queue_zones ?? [],
        people_count_zones: [
          ...existing,
          {
            label: `Count Area ${existing.length + 1}`,
            bbox,
            zone_type: 'people_count',
          },
        ],
      });
      toast.success('Zone saved — people counting will use this area within ~1 minute');
      setIsDrawing(false);
      clearZone();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      toast.error(
        typeof detail === 'string' ? `Failed to save zone: ${detail}` : 'Failed to save zone'
      );
    }
  };

  const handleIntercom = async () => {
    setIntercomLoading(true);
    try {
      const { data } = await api.post(`/cameras/${cameraId}/intercom/initiate`);
      if (data?.edge_connected) {
        toast.success('Intercom session ready — camera audio device connected');
      } else {
        toast(
          'Intercom requires a camera or edge device with a speaker/mic connected. ' +
          'Your current camera does not have audio support, so two-way talk is unavailable.',
          { icon: 'ℹ️', duration: 6000 }
        );
      }
    } catch {
      toast.error('Failed to initiate intercom — backend unreachable');
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

  // Browsers can't attach Authorization headers to <img> requests, so the
  // JWT is passed as a query param (backend accepts ?token= on image routes).
  const authToken = localStorage.getItem('vantag_token') ?? '';
  const streamSrc = `/api/cameras/${cameraId}/stream?token=${encodeURIComponent(authToken)}`;

  return (
    <div className="min-h-screen bg-vantag-dark pb-10">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <nav className="flex items-center gap-1.5 text-sm text-slate-400 mb-1">
          <Link to="/dashboard" className="flex items-center gap-1 hover:text-slate-200">
            <Home size={14} /> Dashboard
          </Link>
          <ChevronRight size={12} />
          <Link
            to={`/stores/${storeId}`}
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
            {/* AI Detection toggles */}
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1">
                <ShieldCheck size={15} className="text-vantag-green" />
                <h3 className="text-sm font-semibold text-slate-100">AI Detections</h3>
              </div>
              <p className="text-xs text-slate-500 mb-3">
                Off by default. Enable only the detections you need — disabled types
                never create incidents for this camera.
              </p>
              <div className="space-y-2">
                {DETECTION_TOGGLES.map((d) => {
                  const on = !!detections[d.key];
                  return (
                    <div
                      key={d.key}
                      className="flex items-center justify-between bg-slate-800/60 rounded-lg px-3 py-2"
                    >
                      <div>
                        <p className="text-xs font-medium text-slate-200">{d.label}</p>
                        <p className="text-[10px] text-slate-500">{d.desc}</p>
                      </div>
                      <button
                        onClick={() => toggleDetection(d.key)}
                        disabled={detSaving === d.key}
                        className={clsx(
                          'relative w-9 h-5 rounded-full transition-colors shrink-0 disabled:opacity-60',
                          on ? 'bg-vantag-green' : 'bg-slate-600'
                        )}
                        title={on ? 'Disable' : 'Enable'}
                      >
                        <span
                          className={clsx(
                            'absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all',
                            on ? 'left-[18px]' : 'left-0.5'
                          )}
                        />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Detection schedule */}
            <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <Clock size={15} className="text-vantag-amber" />
                  <h3 className="text-sm font-semibold text-slate-100">Detection Schedule</h3>
                </div>
                <button
                  onClick={() => saveSchedule({ ...schedule, enabled: !schedule.enabled })}
                  disabled={schedSaving}
                  className={clsx(
                    'relative w-9 h-5 rounded-full transition-colors shrink-0 disabled:opacity-60',
                    schedule.enabled ? 'bg-vantag-green' : 'bg-slate-600'
                  )}
                  title={schedule.enabled ? 'Disable schedule (run 24/7)' : 'Enable schedule'}
                >
                  <span
                    className={clsx(
                      'absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all',
                      schedule.enabled ? 'left-[18px]' : 'left-0.5'
                    )}
                  />
                </button>
              </div>
              <p className="text-xs text-slate-500 mb-3">
                Limit AI detections to a daily time window. Theft detection is
                always on 24/7 and is not affected by this schedule.
              </p>
              <div className={clsx('flex items-center gap-2', !schedule.enabled && 'opacity-50 pointer-events-none')}>
                <div className="flex-1">
                  <label className="block text-[10px] text-slate-500 mb-1">Active from</label>
                  <input
                    type="time"
                    value={schedule.start}
                    onChange={(e) => setSchedule((s) => ({ ...s, start: e.target.value }))}
                    onBlur={() => saveSchedule(schedule)}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg text-xs text-slate-200 px-2 py-1.5 focus:outline-none focus:border-slate-400"
                  />
                </div>
                <span className="text-slate-500 text-xs mt-4">to</span>
                <div className="flex-1">
                  <label className="block text-[10px] text-slate-500 mb-1">Active until</label>
                  <input
                    type="time"
                    value={schedule.end}
                    onChange={(e) => setSchedule((s) => ({ ...s, end: e.target.value }))}
                    onBlur={() => saveSchedule(schedule)}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg text-xs text-slate-200 px-2 py-1.5 focus:outline-none focus:border-slate-400"
                  />
                </div>
              </div>
              {schedule.enabled && schedule.start > schedule.end && (
                <p className="text-[10px] text-vantag-amber mt-2">
                  Overnight window: active from {schedule.start} until {schedule.end} the next day.
                </p>
              )}
            </div>
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
