import { useState } from 'react';
import {
  ShoppingCart, AlertTriangle, Shield, Package,
  Users, Clock, Eye, Camera, Zap, Trash2,
  CheckCircle, Loader2, PlayCircle,
} from 'lucide-react';
import clsx from 'clsx';
import axios from 'axios';
import toast from 'react-hot-toast';

// ── Types ─────────────────────────────────────────────────────────────────────

interface FiredEvent {
  incident_id: string;
  event_type:  string;
  camera_id:   string;
  store_id:    string;
  severity:    string;
  firedAt:     string;
}

interface EventCard {
  key:         string;
  label:       string;
  icon:        React.ReactNode;
  description: string;
  realTrigger: string;
  color:       string;
  bgColor:     string;
  defaultSev:  string;
}

// ── Event card definitions ────────────────────────────────────────────────────

const EVENTS: EventCard[] = [
  {
    key:         'shoplifting',
    label:       'Shoplifting',
    icon:        <ShoppingCart size={28} />,
    description: 'Detects when a person removes products rapidly from a shelf zone.',
    realTrigger: 'Walk up to a shelf, grab and pocket an item quickly.',
    color:       'text-red-400',
    bgColor:     'bg-red-500/10 border-red-500/30',
    defaultSev:  'high',
  },
  {
    key:         'fall_detected',
    label:       'Fall Detected',
    icon:        <AlertTriangle size={28} />,
    description: 'Uses pose skeleton — detects when a person is horizontal on the floor.',
    realTrigger: 'Lie down or crouch flat in front of any camera for 3+ seconds.',
    color:       'text-orange-400',
    bgColor:     'bg-orange-500/10 border-orange-500/30',
    defaultSev:  'critical',
  },
  {
    key:         'restricted_zone',
    label:       'Zone Entry',
    icon:        <Shield size={28} />,
    description: 'Fires when a person enters a configured restricted area (polygon zone).',
    realTrigger: 'Walk into the corner area defined as "Back Office" on each camera.',
    color:       'text-purple-400',
    bgColor:     'bg-purple-500/10 border-purple-500/30',
    defaultSev:  'high',
  },
  {
    key:         'inventory_movement',
    label:       'Inventory Move',
    icon:        <Package size={28} />,
    description: 'Item count in a shelf zone drops by 2+ — possible theft or unauthorised restocking.',
    realTrigger: 'Remove multiple items from within a shelf bounding box zone.',
    color:       'text-yellow-400',
    bgColor:     'bg-yellow-500/10 border-yellow-500/30',
    defaultSev:  'medium',
  },
  {
    key:         'queue_breach',
    label:       'Queue Breach',
    icon:        <Users size={28} />,
    description: 'Queue length exceeds configured threshold at a checkout zone.',
    realTrigger: 'Have 5+ people stand in the queue zone at the same time.',
    color:       'text-blue-400',
    bgColor:     'bg-blue-500/10 border-blue-500/30',
    defaultSev:  'medium',
  },
  {
    key:         'loitering',
    label:       'Loitering',
    icon:        <Clock size={28} />,
    description: 'Person remains stationary in the same spot for an unusually long time.',
    realTrigger: 'Stand still in one place for 3+ minutes in camera view.',
    color:       'text-cyan-400',
    bgColor:     'bg-cyan-500/10 border-cyan-500/30',
    defaultSev:  'medium',
  },
  {
    key:         'face_match',
    label:       'Watchlist Match',
    icon:        <Eye size={28} />,
    description: 'Face recognition match against a person on your watchlist.',
    realTrigger: 'Upload a face image to Watchlist — system matches automatically.',
    color:       'text-pink-400',
    bgColor:     'bg-pink-500/10 border-pink-500/30',
    defaultSev:  'critical',
  },
  {
    key:         'tamper',
    label:       'Camera Tamper',
    icon:        <Camera size={28} />,
    description: 'Camera covered, moved, or scene changes abruptly.',
    realTrigger: 'Block the camera lens with your hand for 2+ seconds.',
    color:       'text-gray-400',
    bgColor:     'bg-gray-500/10 border-gray-500/30',
    defaultSev:  'high',
  },
];

const CAMERAS = ['cam-01', 'cam-03', 'cam-04'];
const SEVERITIES = ['medium', 'high', 'critical'];

const SEV_COLORS: Record<string, string> = {
  medium:   'bg-amber-500/20 text-amber-300',
  high:     'bg-red-500/20 text-red-300',
  critical: 'bg-red-700/30 text-red-200 font-bold',
};

// ── Auth helper ───────────────────────────────────────────────────────────────

const authHeader = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('vantag_token') ?? ''}` },
});

// ── Component ─────────────────────────────────────────────────────────────────

export default function DemoCenter() {
  const [cameraSelections, setCameraSelections] = useState<Record<string, string>>(
    Object.fromEntries(EVENTS.map((e, i) => [e.key, CAMERAS[i % CAMERAS.length]]))
  );
  const [severitySelections, setSeveritySelections] = useState<Record<string, string>>(
    Object.fromEntries(EVENTS.map((e) => [e.key, e.defaultSev]))
  );
  const [firing, setFiring]       = useState<Record<string, boolean>>({});
  const [firingAll, setFiringAll] = useState(false);
  const [clearing, setClearing]   = useState(false);
  const [firedLog, setFiredLog]   = useState<FiredEvent[]>([]);

  // ── Fire single event ───────────────────────────────────────────────────────

  const fireEvent = async (eventKey: string) => {
    setFiring((f) => ({ ...f, [eventKey]: true }));
    try {
      const { data } = await axios.post(
        '/api/demo/trigger',
        {
          event_type: eventKey,
          camera_id:  cameraSelections[eventKey],
          severity:   severitySelections[eventKey],
        },
        authHeader()
      );
      setFiredLog((prev) => [
        { ...data, firedAt: new Date().toLocaleTimeString() },
        ...prev,
      ]);
      toast.success(`${EVENTS.find((e) => e.key === eventKey)?.label} incident fired!`);
    } catch {
      toast.error('Failed to fire event — is the backend running?');
    } finally {
      setFiring((f) => ({ ...f, [eventKey]: false }));
    }
  };

  // ── Fire all events ─────────────────────────────────────────────────────────

  const fireAll = async () => {
    setFiringAll(true);
    try {
      const { data } = await axios.post('/api/demo/trigger-sequence', {}, authHeader());
      const newEntries: FiredEvent[] = (data.events ?? []).map((e: FiredEvent) => ({
        ...e,
        firedAt: new Date().toLocaleTimeString(),
      }));
      setFiredLog((prev) => [...newEntries, ...prev]);
      toast.success(`${data.fired} demo incidents fired across all cameras!`);
    } catch {
      toast.error('Failed to fire sequence — is the backend running?');
    } finally {
      setFiringAll(false);
    }
  };

  // ── Clear demo events ───────────────────────────────────────────────────────

  const clearDemo = async () => {
    setClearing(true);
    try {
      const { data } = await axios.delete('/api/demo/clear', authHeader());
      setFiredLog([]);
      toast.success(`Cleared ${data.cleared} demo incidents.`);
    } catch {
      toast.error('Clear failed.');
    } finally {
      setClearing(false);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-vantag-bg text-slate-100 p-6 space-y-6">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <Zap size={24} className="text-vantag-red" />
            Demo &amp; Test Center
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Simulate any detection event to demonstrate the system. Events appear instantly in
            the <span className="text-slate-200 font-medium">Incidents</span> page and update
            the <span className="text-slate-200 font-medium">Dashboard</span> risk scores.
          </p>
        </div>
        <div className="flex gap-3 flex-shrink-0">
          <button
            onClick={clearDemo}
            disabled={clearing}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-400 transition-colors text-sm disabled:opacity-50"
          >
            {clearing ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
            Clear Demo Events
          </button>
          <button
            onClick={fireAll}
            disabled={firingAll}
            className="flex items-center gap-2 px-5 py-2 rounded-lg bg-vantag-red hover:bg-red-600 text-white font-semibold text-sm transition-colors disabled:opacity-60 shadow-lg shadow-red-900/30"
          >
            {firingAll
              ? <Loader2 size={15} className="animate-spin" />
              : <PlayCircle size={15} />}
            {firingAll ? 'Firing All…' : 'Fire All Events — Full Demo'}
          </button>
        </div>
      </div>

      {/* How to use callout */}
      <div className="bg-blue-950/40 border border-blue-700/40 rounded-xl p-4 text-sm text-blue-200">
        <strong className="text-blue-300">How to use this page:</strong>
        {' '}Pick a camera and severity for any event type below, then click
        {' '}<span className="font-semibold text-white">Fire Event</span> — the incident
        appears on the Incidents page within 1 second and updates the Dashboard risk score.
        Use <span className="font-semibold text-white">Fire All Events</span> to run a full
        end-to-end demo of every detection type in 3 seconds.
      </div>

      {/* Event cards — 2 rows of 4 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {EVENTS.map((ev) => {
          const isFiring = firing[ev.key];
          return (
            <div
              key={ev.key}
              className={clsx(
                'rounded-xl border p-4 flex flex-col gap-3',
                ev.bgColor
              )}
            >
              {/* Icon + label */}
              <div className="flex items-center gap-3">
                <span className={ev.color}>{ev.icon}</span>
                <span className="font-semibold text-slate-100 text-sm">{ev.label}</span>
              </div>

              {/* Description */}
              <p className="text-xs text-slate-400 leading-relaxed">{ev.description}</p>

              {/* Real trigger hint */}
              <div className="bg-black/20 rounded-lg px-3 py-2 text-xs text-slate-400">
                <span className="text-slate-300 font-medium">Real trigger: </span>
                {ev.realTrigger}
              </div>

              {/* Camera selector */}
              <div className="flex gap-2">
                <select
                  value={cameraSelections[ev.key]}
                  onChange={(e) =>
                    setCameraSelections((s) => ({ ...s, [ev.key]: e.target.value }))
                  }
                  className="flex-1 text-xs bg-black/30 border border-slate-600 rounded-lg px-2 py-1.5 text-slate-200"
                >
                  {CAMERAS.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
                <select
                  value={severitySelections[ev.key]}
                  onChange={(e) =>
                    setSeveritySelections((s) => ({ ...s, [ev.key]: e.target.value }))
                  }
                  className="text-xs bg-black/30 border border-slate-600 rounded-lg px-2 py-1.5 text-slate-200"
                >
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>{s.toUpperCase()}</option>
                  ))}
                </select>
              </div>

              {/* Fire button */}
              <button
                onClick={() => fireEvent(ev.key)}
                disabled={isFiring}
                className={clsx(
                  'w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-semibold transition-all',
                  'bg-white/10 hover:bg-white/20 text-slate-100 border border-white/10 hover:border-white/20',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                {isFiring
                  ? <Loader2 size={14} className="animate-spin" />
                  : <PlayCircle size={14} />}
                {isFiring ? 'Firing…' : 'Fire Event'}
              </button>
            </div>
          );
        })}
      </div>

      {/* Live event log */}
      <div className="bg-vantag-card rounded-xl border border-slate-700/60 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-700/60 flex items-center justify-between">
          <h2 className="font-semibold text-slate-200 text-sm">
            Live Feed — Events Fired This Session
          </h2>
          <span className="text-xs text-slate-500">{firedLog.length} events</span>
        </div>

        {firedLog.length === 0 ? (
          <div className="px-5 py-10 text-center text-slate-500 text-sm">
            No events fired yet — click any "Fire Event" button above to begin.
          </div>
        ) : (
          <div className="divide-y divide-slate-700/40 max-h-80 overflow-y-auto">
            {firedLog.map((ev) => (
              <div key={ev.incident_id} className="px-5 py-3 flex items-center gap-4 text-sm">
                <CheckCircle size={16} className="text-vantag-green flex-shrink-0" />
                <span className="text-slate-500 text-xs w-16 flex-shrink-0">{ev.firedAt}</span>
                <span className={clsx(
                  'text-xs font-semibold px-2 py-0.5 rounded uppercase',
                  SEV_COLORS[ev.severity] ?? 'bg-slate-700 text-slate-300'
                )}>
                  {ev.severity}
                </span>
                <span className="font-medium text-slate-200 uppercase tracking-wide text-xs">
                  {ev.event_type.replace(/_/g, ' ')}
                </span>
                <span className="text-slate-500 text-xs">{ev.camera_id}</span>
                <span className="text-slate-600 text-xs ml-auto">{ev.incident_id}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pro tip */}
      <div className="bg-vantag-card rounded-xl border border-slate-700/60 p-5">
        <h3 className="font-semibold text-slate-200 mb-3">
          After firing demo events — what to check
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm text-slate-400">
          <div className="flex flex-col gap-1">
            <span className="text-slate-200 font-medium">Incidents page</span>
            <span>All events appear here with severity, camera, timestamp and description.</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-slate-200 font-medium">Dashboard risk cards</span>
            <span>Scores update every 10 s. High-weight events (shoplifting, fall) push scores to CRITICAL.</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-slate-200 font-medium">WebSocket feed</span>
            <span>Status bar shows LIVE — events stream in real-time without page refresh.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
