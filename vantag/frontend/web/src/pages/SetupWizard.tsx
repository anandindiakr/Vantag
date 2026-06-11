/**
 * SetupWizard — /setup
 *
 * Guided, self-correcting setup flow that diagnoses WHY things aren't
 * working and tells the user exactly what to do next:
 *   Step 1 — Edge Agent running?      (polls /api/edge/agents every 5s)
 *   Step 2 — Network check            (cloud vs LAN explanation + auto-detect)
 *   Step 3 — Discover cameras         (scan-request → poll /cameras/discovered)
 *   Step 4 — Camera health            (registered cameras online/offline)
 *   Step 5 — Done                     (go to dashboard)
 *
 * Each step auto-advances when its check passes and shows beginner-friendly
 * fix instructions when it fails.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  MonitorCheck,
  Wifi,
  WifiOff,
  Radar,
  Camera,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  ArrowLeft,
  Network,
  RefreshCw,
  PartyPopper,
  Settings2,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface AgentItem {
  agent_id: string;
  device_type: string;
  device_name: string;
  status: 'online' | 'offline';
  last_heartbeat_age_seconds: number | null;
  camera_count: number;
}

interface DiscoveredCam {
  camera_id: string;
  name: string;
  ip?: string | null;
  brand?: string | null;
  conn_status: string;
  needs_credentials?: boolean;
}

interface RegisteredCam {
  camera_id: string;
  name: string;
  rtsp_url: string;
  status: string;
  enabled: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('vantag_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

function isPrivateIp(host: string): boolean {
  return (
    /^192\.168\./.test(host) ||
    /^10\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host)
  );
}

function rtspHost(rtspUrl: string): string {
  // rtsp://***@192.168.1.50:554/path  →  192.168.1.50
  const m = rtspUrl.match(/rtsp:\/\/(?:[^@/]*@)?([^:/]+)/);
  return m ? m[1] : '';
}

const STEPS = [
  { id: 1, label: 'Edge Agent', icon: <MonitorCheck size={16} /> },
  { id: 2, label: 'Network', icon: <Network size={16} /> },
  { id: 3, label: 'Find Cameras', icon: <Radar size={16} /> },
  { id: 4, label: 'Camera Health', icon: <Camera size={16} /> },
  { id: 5, label: 'Done', icon: <PartyPopper size={16} /> },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function SetupWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);

  // Shared state
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [agentChecked, setAgentChecked] = useState(false);
  const [cameras, setCameras] = useState<RegisteredCam[]>([]);
  const [discovered, setDiscovered] = useState<DiscoveredCam[]>([]);
  const [scanning, setScanning] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const scanDeadline = useRef<number>(0);

  const onlineAgent = agents.find((a) => a.status === 'online') ?? null;

  // ── Poll agents (steps 1 & 2) ─────────────────────────────────────────────
  const fetchAgents = useCallback(async () => {
    try {
      const data = await apiGet<{ agents: AgentItem[] }>('/api/edge/agents');
      setAgents(data.agents ?? []);
    } catch {
      /* transient */
    } finally {
      setAgentChecked(true);
    }
  }, []);

  const fetchCameras = useCallback(async () => {
    try {
      const data = await apiGet<RegisteredCam[]>('/api/cameras');
      setCameras(Array.isArray(data) ? data : []);
    } catch {
      /* transient */
    }
  }, []);

  const fetchDiscovered = useCallback(async () => {
    try {
      const data = await apiGet<DiscoveredCam[]>('/api/cameras/discovered');
      setDiscovered(Array.isArray(data) ? data : []);
    } catch {
      /* transient */
    }
  }, []);

  useEffect(() => {
    fetchAgents();
    fetchCameras();
    fetchDiscovered();
    const t = setInterval(() => {
      fetchAgents();
      if (step >= 3) fetchDiscovered();
      if (step >= 4) fetchCameras();
    }, 5000);
    return () => clearInterval(t);
  }, [step, fetchAgents, fetchCameras, fetchDiscovered]);

  // ── Auto-advance step 1 when agent comes online ───────────────────────────
  useEffect(() => {
    if (step === 1 && onlineAgent) {
      toast.success(`Edge Agent "${onlineAgent.device_name}" is online!`);
      setStep(2);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onlineAgent?.agent_id, step]);

  // ── Trigger a LAN scan (step 3) ───────────────────────────────────────────
  const triggerScan = async () => {
    setScanning(true);
    scanDeadline.current = Date.now() + 120_000;
    try {
      await apiPost('/api/cameras/scan-request');
      toast('Scan queued — your Edge Agent will pick it up within ~30s…', { icon: '📡' });
    } catch (err) {
      setScanning(false);
      toast.error((err as Error).message ?? 'Could not queue scan.');
    }
  };

  // Stop the scanning spinner once new cameras appear or deadline passes
  useEffect(() => {
    if (!scanning) return;
    if (discovered.length > 0 || Date.now() > scanDeadline.current) {
      setScanning(false);
      if (discovered.length > 0) toast.success(`Found ${discovered.length} camera(s)!`);
    }
  }, [discovered, scanning]);

  const confirmCamera = async (id: string) => {
    setConfirming(id);
    try {
      await apiPost(`/api/cameras/discovered/${id}/confirm`);
      toast.success('Camera added to your dashboard.');
      fetchDiscovered();
      fetchCameras();
    } catch (err) {
      toast.error((err as Error).message ?? 'Could not confirm camera.');
    } finally {
      setConfirming(null);
    }
  };

  // ── Derived network diagnosis (step 2) ────────────────────────────────────
  const lanCameras = cameras.filter((c) => isPrivateIp(rtspHost(c.rtsp_url)));
  const networkProblem = lanCameras.length > 0 && !onlineAgent;

  // ──────────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 text-slate-100">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings2 className="text-violet-400" size={26} /> Setup Wizard
        </h1>
        <p className="text-slate-400 mt-1 text-sm">
          We check each part of your setup live and tell you exactly what to fix.
        </p>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-1 mb-8 overflow-x-auto">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => s.id < step && setStep(s.id)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition',
                s.id === step
                  ? 'bg-violet-600 text-white'
                  : s.id < step
                    ? 'bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30'
                    : 'bg-slate-800 text-slate-500',
              )}
            >
              {s.id < step ? <CheckCircle2 size={14} /> : s.icon}
              {s.label}
            </button>
            {i < STEPS.length - 1 && <div className="w-4 h-px bg-slate-700" />}
          </div>
        ))}
      </div>

      {/* ── STEP 1 — Edge Agent ─────────────────────────────────────────── */}
      {step === 1 && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <MonitorCheck size={20} className="text-violet-400" /> Step 1 — Is your Edge Agent running?
          </h2>
          <p className="text-sm text-slate-400">
            The Edge Agent is a small program that runs on a PC <strong>inside your store
            network</strong> (the same Wi-Fi/LAN as your cameras). It connects your cameras
            to the cloud — without it, cameras stay offline.
          </p>

          {!agentChecked ? (
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <Loader2 className="animate-spin" size={16} /> Checking…
            </div>
          ) : onlineAgent ? (
            <div className="flex items-center gap-2 text-emerald-400 text-sm">
              <CheckCircle2 size={16} /> Agent online — moving on…
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 text-amber-400 text-sm">
                <AlertCircle size={16} />
                {agents.length === 0
                  ? 'No Edge Agent has ever connected for your account.'
                  : 'Your agent is installed but not currently running.'}
              </div>
              <ol className="list-decimal list-inside text-sm text-slate-300 space-y-1.5 bg-slate-900/50 rounded-lg p-4">
                <li>
                  <Link to="/download" className="text-violet-400 underline">
                    Download the Edge Agent
                  </Link>{' '}
                  on a Windows PC that is on the <strong>same network as your cameras</strong>.
                </li>
                <li>Unzip it and double-click <code className="bg-slate-700 px-1 rounded">install.bat</code> (or <code className="bg-slate-700 px-1 rounded">retail-vantag.exe</code>).</li>
                <li>Keep the window open (it runs in the background). This page detects it automatically.</li>
              </ol>
              <div className="flex items-center gap-2 text-slate-500 text-xs">
                <Loader2 className="animate-spin" size={14} /> Auto-checking every 5 seconds — no need to refresh.
              </div>
            </>
          )}

          <div className="flex justify-end">
            <button
              onClick={() => setStep(2)}
              className="text-xs text-slate-500 hover:text-slate-300 underline"
            >
              Skip for now →
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2 — Network check ──────────────────────────────────────── */}
      {step === 2 && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Network size={20} className="text-violet-400" /> Step 2 — Network check
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div className={clsx('rounded-lg p-4 border', onlineAgent ? 'border-emerald-600/40 bg-emerald-600/10' : 'border-amber-600/40 bg-amber-600/10')}>
              <div className="flex items-center gap-2 font-medium mb-1">
                {onlineAgent ? <Wifi size={16} className="text-emerald-400" /> : <WifiOff size={16} className="text-amber-400" />}
                Edge Agent
              </div>
              <p className="text-slate-300">
                {onlineAgent
                  ? `"${onlineAgent.device_name}" is online and can reach your store LAN.`
                  : 'No agent online — cloud cannot reach cameras on a private network (192.168.x.x).'}
              </p>
            </div>
            <div className="rounded-lg p-4 border border-slate-600/40 bg-slate-900/40">
              <div className="flex items-center gap-2 font-medium mb-1">
                <Camera size={16} className="text-violet-400" /> Your cameras
              </div>
              <p className="text-slate-300">
                {cameras.length === 0
                  ? 'No cameras registered yet — we will find them in the next step.'
                  : `${cameras.length} registered, ${lanCameras.length} on a private LAN address.`}
              </p>
            </div>
          </div>

          {networkProblem && (
            <div className="rounded-lg p-4 border border-red-600/40 bg-red-600/10 text-sm text-red-300 flex gap-2">
              <AlertCircle size={18} className="shrink-0 mt-0.5" />
              <div>
                <strong>Detected problem:</strong> your cameras use private LAN addresses but no
                Edge Agent is online. The cloud server physically cannot connect to
                192.168.x.x addresses — this is why cameras show offline. Fix: go back to
                Step 1 and start the agent on a PC in the camera network.
              </div>
            </div>
          )}

          {!networkProblem && (
            <div className="rounded-lg p-4 border border-emerald-600/40 bg-emerald-600/10 text-sm text-emerald-300 flex gap-2">
              <CheckCircle2 size={18} className="shrink-0 mt-0.5" />
              <div>
                {onlineAgent
                  ? 'Network looks good — your agent bridges the LAN to the cloud.'
                  : 'No LAN-only cameras detected yet. You can continue.'}
              </div>
            </div>
          )}

          <div className="flex justify-between">
            <button onClick={() => setStep(1)} className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
              <ArrowLeft size={14} /> Back
            </button>
            <button
              onClick={() => setStep(3)}
              className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 px-4 py-2 rounded-lg text-sm font-medium"
            >
              Continue <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 3 — Discover cameras ───────────────────────────────────── */}
      {step === 3 && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Radar size={20} className="text-violet-400" /> Step 3 — Find your cameras
          </h2>
          <p className="text-sm text-slate-400">
            Your Edge Agent scans the store network for cameras (RTSP port 554, ONVIF).
            Found cameras appear below — click <strong>Add</strong> to register them.
          </p>

          {!onlineAgent && (
            <div className="rounded-lg p-3 border border-amber-600/40 bg-amber-600/10 text-sm text-amber-300 flex gap-2">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              No agent online — the scan will run as soon as the agent connects. You can also{' '}
              <Link to="/cameras/manage" className="underline">add a camera manually</Link>.
            </div>
          )}

          <button
            onClick={triggerScan}
            disabled={scanning}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium"
          >
            {scanning ? <Loader2 className="animate-spin" size={16} /> : <Radar size={16} />}
            {scanning ? 'Scanning… (up to 2 min)' : 'Scan my network'}
          </button>

          {discovered.length > 0 && (
            <div className="space-y-2">
              {discovered.map((d) => (
                <div key={d.camera_id} className="flex items-center justify-between bg-slate-900/50 rounded-lg px-4 py-3">
                  <div>
                    <div className="text-sm font-medium">{d.name}</div>
                    <div className="text-xs text-slate-500">
                      {d.ip ?? 'unknown IP'} {d.brand ? `· ${d.brand}` : ''}
                      {d.needs_credentials && ' · needs username/password'}
                    </div>
                  </div>
                  {d.needs_credentials ? (
                    <Link
                      to="/cameras/manage"
                      className="text-xs bg-amber-600/20 text-amber-300 px-3 py-1.5 rounded-lg hover:bg-amber-600/30"
                    >
                      Enter credentials
                    </Link>
                  ) : (
                    <button
                      onClick={() => confirmCamera(d.camera_id)}
                      disabled={confirming === d.camera_id}
                      className="text-xs bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-3 py-1.5 rounded-lg font-medium"
                    >
                      {confirming === d.camera_id ? 'Adding…' : 'Add'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {discovered.length === 0 && !scanning && (
            <div className="rounded-lg border border-amber-600/40 bg-amber-600/10 p-4 text-xs text-amber-200 space-y-2">
              <p className="font-semibold text-amber-300">Using a Hikvision / Dahua NVR? Cameras behind an NVR don't respond to scans directly.</p>
              <p>Add them manually using your <strong>NVR's IP</strong> and these RTSP channel paths:</p>
              <div className="font-mono bg-slate-900/60 p-2 rounded space-y-0.5">
                <div className="grid grid-cols-2"><span>Channel 1:</span><span>/Streaming/Channels/101</span></div>
                <div className="grid grid-cols-2"><span>Channel 2:</span><span>/Streaming/Channels/201</span></div>
                <div className="grid grid-cols-2"><span>Channel 3:</span><span>/Streaming/Channels/301</span></div>
                <div className="grid grid-cols-2"><span>Channel N:</span><span>/Streaming/Channels/N01</span></div>
              </div>
              <p>Use the <strong>NVR admin password</strong> — the one you type on the NVR screen or in iVMS-4200 / Hik-Connect.</p>
              <Link to="/cameras/manage" className="inline-block mt-1 bg-violet-600 hover:bg-violet-500 text-white px-3 py-1.5 rounded-lg font-medium no-underline">
                Add NVR cameras manually →
              </Link>
            </div>
          )}

          <div className="flex justify-between">
            <button onClick={() => setStep(2)} className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
              <ArrowLeft size={14} /> Back
            </button>
            <button
              onClick={() => { fetchCameras(); setStep(4); }}
              className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 px-4 py-2 rounded-lg text-sm font-medium"
            >
              Continue <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 4 — Camera health ──────────────────────────────────────── */}
      {step === 4 && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Camera size={20} className="text-violet-400" /> Step 4 — Camera health
          </h2>

          {cameras.length === 0 ? (
            <div className="text-sm text-amber-300 flex gap-2 items-start">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              No cameras registered. Go back to Step 3 to scan, or{' '}
              <Link to="/cameras/manage" className="underline">add one manually</Link>.
            </div>
          ) : (
            <div className="space-y-2">
              {cameras.map((c) => (
                <div key={c.camera_id} className="flex items-center justify-between bg-slate-900/50 rounded-lg px-4 py-3">
                  <div>
                    <div className="text-sm font-medium">{c.name}</div>
                    <div className="text-xs text-slate-500">{rtspHost(c.rtsp_url) || '—'}</div>
                  </div>
                  <span
                    className={clsx(
                      'text-xs px-2.5 py-1 rounded-full font-medium',
                      c.status === 'online'
                        ? 'bg-emerald-600/20 text-emerald-400'
                        : 'bg-red-600/20 text-red-400',
                    )}
                  >
                    {c.status === 'online' ? 'Online' : 'Offline'}
                  </span>
                </div>
              ))}
            </div>
          )}

          {cameras.some((c) => c.status !== 'online') && (
            <div className="rounded-lg p-4 border border-slate-600/40 bg-slate-900/40 text-xs text-slate-400 space-y-1.5">
              <p className="font-medium text-slate-300">Why is a camera offline?</p>
              <p>1. The Edge Agent must be running ({onlineAgent ? '✓ it is' : '✗ it is NOT — fix Step 1'}).</p>
              <p>2. The agent pulls its camera list every ~60s — newly added cameras can take a minute to go online.</p>
              <p>3. Wrong RTSP path or credentials — use <Link to="/cameras/manage" className="text-violet-400 underline">Auto-Detect</Link> in Manage Cameras (runs through your agent).</p>
            </div>
          )}

          <div className="flex justify-between">
            <button onClick={() => setStep(3)} className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
              <ArrowLeft size={14} /> Back
            </button>
            <button
              onClick={() => setStep(5)}
              className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 px-4 py-2 rounded-lg text-sm font-medium"
            >
              Continue <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 5 — Done ───────────────────────────────────────────────── */}
      {step === 5 && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6 space-y-4 text-center">
          <PartyPopper size={40} className="text-violet-400 mx-auto" />
          <h2 className="text-xl font-semibold">Setup complete!</h2>
          <div className="text-sm text-slate-400 space-y-1">
            <p>Agent: {onlineAgent ? `✓ ${onlineAgent.device_name} online` : '✗ not online — cameras stay offline until it runs'}</p>
            <p>Cameras: {cameras.length} registered, {cameras.filter((c) => c.status === 'online').length} online</p>
          </div>
          <div className="flex justify-center gap-3 pt-2">
            <button
              onClick={() => { setStep(1); fetchAgents(); fetchCameras(); }}
              className="flex items-center gap-1.5 bg-slate-700 hover:bg-slate-600 px-4 py-2 rounded-lg text-sm"
            >
              <RefreshCw size={14} /> Re-run checks
            </button>
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 px-5 py-2 rounded-lg text-sm font-medium"
            >
              Go to Dashboard <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
