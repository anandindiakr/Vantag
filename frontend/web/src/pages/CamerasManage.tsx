// frontend/web/src/pages/CamerasManage.tsx
// Camera Management page: auto-scan, manual add (brand-aware), and camera list with delete.
// Features: brand presets, auto-detect RTSP path, contextual help, floating support button.

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Camera, Wifi, WifiOff, Plus, Trash2, TestTube2,
  Loader2, CheckCircle2, XCircle, ArrowLeft, Network, Sparkles,
  MessageCircle, SlidersHorizontal, Pencil, Save,
} from 'lucide-react';
import clsx from 'clsx';
import { useQueryClient } from '@tanstack/react-query';
import { api, useCameras, queryKeys, useUpdateCameraSensitivity } from '../hooks/useApi';
import type { Camera as CameraModel } from '../store/useVantagStore';
import toast from 'react-hot-toast';
import InfoTooltip from '../components/InfoTooltip';

// ─── Brand RTSP Presets ───────────────────────────────────────────────────────

const BRAND_RTSP_PRESETS: Record<string, { port: number; paths: string[] }> = {
  hikvision: { port: 554, paths: ['/Streaming/Channels/101', '/Streaming/Channels/102', '/h264/ch1/main/av_stream'] },
  dahua:     { port: 554, paths: ['/cam/realmonitor?channel=1&subtype=0', '/cam/realmonitor?channel=1&subtype=1'] },
  cpplus:    { port: 554, paths: ['/cam/realmonitor?channel=1&subtype=0'] },
  tplink:    { port: 554, paths: ['/stream1', '/stream2'] },
  reolink:   { port: 554, paths: ['/h264Preview_01_main', '/h264Preview_01_sub'] },
  uniview:   { port: 554, paths: ['/media/video1', '/media/video2'] },
  axis:      { port: 554, paths: ['/axis-media/media.amp'] },
  bosch:     { port: 554, paths: ['/rtsp_tunnel'] },
  ezviz:     { port: 554, paths: ['/Streaming/Channels/101'] },
  xiaomi:    { port: 554, paths: ['/live/ch00_0'] },
  onvif:     { port: 554, paths: ['/onvif/media_service', '/onvif1', '/onvif2'] },
  generic:   { port: 554, paths: ['/stream', '/stream1', '/live', '/live.sdp', '/'] },
};

const BRAND_OPTIONS = [
  { value: 'generic',   label: "I don't know / Generic" },
  { value: 'hikvision', label: 'Hikvision' },
  { value: 'dahua',     label: 'Dahua' },
  { value: 'cpplus',    label: 'CP Plus' },
  { value: 'tplink',    label: 'TP-Link / Tapo' },
  { value: 'reolink',   label: 'Reolink' },
  { value: 'uniview',   label: 'Uniview' },
  { value: 'axis',      label: 'Axis' },
  { value: 'bosch',     label: 'Bosch' },
  { value: 'ezviz',     label: 'Ezviz' },
  { value: 'xiaomi',    label: 'Xiaomi / Mi' },
  { value: 'onvif',     label: 'ONVIF (auto-detect)' },
];

// ─── Types ────────────────────────────────────────────────────────────────────

interface DiscoveredCamera {
  ip: string;
  port: number;
  vendor_hint: string | null;
}

interface TestResult {
  success: boolean;
  thumbnail_base64?: string;
  error?: string;
  lan_unreachable?: boolean;
}

interface AutoDetectResult {
  success: boolean;
  port?: number;
  path?: string;
  brand_detected?: string;
  thumbnail_base64?: string;
  tried?: number;
  message?: string;
}

// ─── Manual form default state ─────────────────────────────────────────────

const BLANK_FORM = {
  name: '',
  location: '',
  ip: '',
  port: 554,
  username: '',
  password: '',
  rtsp_path: '/',
  resolution: '1920x1080',
  fps: 15,
  enabled: true,
  low_light_mode: false,
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white/3 border border-white/8 rounded-2xl p-6">
      <h2 className="text-base font-semibold text-white mb-4">{title}</h2>
      {children}
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="flex items-center text-xs font-medium text-white/50 mb-1">{children}</label>;
}

function TextInput({
  value, onChange, placeholder, type = 'text', className = '',
}: {
  value: string | number;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  className?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={clsx(
        'w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/60 transition-colors',
        className,
      )}
    />
  );
}

// ─── Section A: Auto-Scan ─────────────────────────────────────────────────────

function AutoScanSection({ onAdd }: { onAdd: (ip: string, port: number) => void }) {
  const [scanning, setScanning] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredCamera[]>([]);
  const [subnet, setSubnet] = useState('');

  const handleScan = async () => {
    setScanning(true);
    setDiscovered([]);
    try {
      const res = await api.post<DiscoveredCamera[]>('/cameras/scan', {
        subnet: subnet.trim() || undefined,
      });
      setDiscovered(res.data ?? []);
      if ((res.data ?? []).length === 0) {
        toast('No cameras found on the network.', { icon: '🔍' });
      } else {
        toast.success(`Found ${res.data.length} camera(s).`);
      }
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Scan failed.');
    } finally {
      setScanning(false);
    }
  };

  return (
    <SectionCard title="A — Auto-Scan Network">
      <div className="flex gap-3 mb-4">
        <TextInput
          value={subnet}
          onChange={setSubnet}
          placeholder="192.168.1.0/24  (leave blank to auto-detect)"
          className="flex-1"
        />
        <button
          onClick={handleScan}
          disabled={scanning}
          className="flex items-center gap-2 px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl text-sm font-semibold text-white transition-all whitespace-nowrap"
        >
          {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Network className="w-4 h-4" />}
          {scanning ? 'Scanning…' : 'Scan My Network for Cameras'}
        </button>
      </div>

      {scanning && (
        <div className="flex items-center gap-3 text-sm text-white/50 py-4">
          <Loader2 className="w-5 h-5 animate-spin text-violet-400" />
          Probing port 554 across your subnet…
        </div>
      )}

      <AnimatePresence>
        {discovered.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-2"
          >
            {discovered.map((cam) => (
              <motion.div
                key={cam.ip}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-white/5 border border-white/10 rounded-xl p-4 flex items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white truncate">{cam.ip}:{cam.port}</p>
                  {cam.vendor_hint && (
                    <p className="text-xs text-violet-400 mt-0.5">{cam.vendor_hint}</p>
                  )}
                </div>
                <button
                  onClick={() => onAdd(cam.ip, cam.port)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600/20 hover:bg-violet-600/40 border border-violet-500/30 rounded-lg text-xs font-medium text-violet-300 transition-all whitespace-nowrap"
                >
                  <Plus className="w-3.5 h-3.5" /> Add
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </SectionCard>
  );
}

// ─── Section A2: Edge-Agent Auto-Discovery (cameras on the store LAN) ──────────

interface EdgeDiscoveredCamera {
  camera_id: string;
  name: string;
  ip: string | null;
  brand: string | null;
  model: string | null;
  conn_status: string;
  port: number | null;
  rtsp_path: string | null;
  thumbnail_url: string | null;
  needs_credentials: boolean;
  confidence: number | null;
}

function EdgeDiscoveryCard({
  cam,
  onConfirmed,
}: {
  cam: EdgeDiscoveredCamera;
  onConfirmed: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(cam.name);
  const [location, setLocation] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleConfirm = async () => {
    if (!location.trim()) {
      toast.error('Please enter a location / store name.');
      return;
    }
    if (cam.needs_credentials && (!username.trim() || !password.trim())) {
      toast.error('This camera needs a username and password.');
      return;
    }
    setSaving(true);
    try {
      await api.post(`/cameras/discovered/${cam.camera_id}/confirm`, {
        name: name.trim() || cam.name,
        location: location.trim(),
        username: username.trim() || undefined,
        password: password.trim() || undefined,
      });
      toast.success(`${name || cam.ip} added and is now monitored.`);
      onConfirmed();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Failed to confirm camera.');
    } finally {
      setSaving(false);
    }
  };

  const online = cam.conn_status === 'online';

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
      <div className="aspect-video bg-black/40 flex items-center justify-center">
        {cam.thumbnail_url ? (
          <img src={cam.thumbnail_url} alt={cam.name} className="w-full h-full object-cover" />
        ) : (
          <Camera className="w-8 h-8 text-white/20" />
        )}
      </div>
      <div className="p-3 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-white truncate">{cam.name}</p>
          <span
            className={clsx(
              'text-[10px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap',
              online ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300',
            )}
          >
            {online ? 'Stream OK' : 'Needs login'}
          </span>
        </div>
        <p className="text-xs text-white/40 truncate">
          {cam.ip}
          {cam.port ? `:${cam.port}` : ''}
          {cam.brand ? ` · ${cam.brand}` : ''}
        </p>

        {!open ? (
          <button
            onClick={() => setOpen(true)}
            className="w-full mt-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-violet-600/20 hover:bg-violet-600/40 border border-violet-500/30 rounded-lg text-xs font-medium text-violet-300 transition-all"
          >
            <Plus className="w-3.5 h-3.5" /> Confirm &amp; Add
          </button>
        ) : (
          <div className="space-y-2 pt-1">
            <TextInput value={name} onChange={setName} placeholder="Camera name" />
            <TextInput value={location} onChange={setLocation} placeholder="Location / store *" />
            {cam.needs_credentials && (
              <>
                <TextInput value={username} onChange={setUsername} placeholder="Camera username *" />
                <TextInput value={password} onChange={setPassword} placeholder="Camera password *" type="password" />
              </>
            )}
            <div className="flex gap-2">
              <button
                onClick={handleConfirm}
                disabled={saving}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-lg text-xs font-semibold text-white transition-all"
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                {saving ? 'Adding…' : 'Add Camera'}
              </button>
              <button
                onClick={() => setOpen(false)}
                disabled={saving}
                className="px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-white/60 transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EdgeDiscoverySection() {
  const qc = useQueryClient();
  const [requesting, setRequesting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [cameras, setCameras] = useState<EdgeDiscoveredCamera[]>([]);

  const fetchDiscovered = async () => {
    try {
      const res = await api.get<EdgeDiscoveredCamera[]>('/cameras/discovered');
      setCameras(res.data ?? []);
      return res.data ?? [];
    } catch {
      return [];
    }
  };

  // Show whatever the Edge Agent has already reported, without making the user
  // click "Auto-Scan" first, and keep refreshing so newly-discovered cameras
  // appear on their own (the agent scans the LAN on startup and on request).
  useEffect(() => {
    void fetchDiscovered();
    const timer = setInterval(() => {
      void fetchDiscovered();
    }, 6000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAutoScan = async () => {
    setRequesting(true);
    try {
      await api.post('/cameras/scan-request', {});
      toast.success('Scan requested. Your edge agent is scanning the store network…');
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Could not request a scan.');
      setRequesting(false);
      return;
    }
    setRequesting(false);
    setPolling(true);
    // Poll for discovered cameras for up to ~60s.
    let attempts = 0;
    const before = cameras.length;
    const timer = setInterval(async () => {
      attempts += 1;
      const found = await fetchDiscovered();
      if (found.length > before || attempts >= 15) {
        clearInterval(timer);
        setPolling(false);
        if (found.length > before) {
          toast.success(`Found ${found.length} camera(s) on your network.`);
        } else if (found.length > 0) {
          toast.success(`Showing ${found.length} camera(s) your Edge Agent has found.`);
        } else if (attempts >= 15) {
          toast('No new cameras yet. Make sure the edge agent is running.', { icon: '🔍' });
        }
      }
    }, 4000);
  };

  const handleConfirmed = () => {
    void fetchDiscovered();
    void qc.invalidateQueries({ queryKey: queryKeys.cameras });
  };

  return (
    <SectionCard title="A — Auto-Discover Cameras (Edge Agent)">
      <p className="text-sm text-white/50 mb-4">
        Click below and your on-site Edge Agent will scan the store network and find your
        cameras automatically — no IP address or RTSP path needed.
      </p>
      <div className="flex flex-wrap gap-3 mb-4">
        <button
          onClick={handleAutoScan}
          disabled={requesting || polling}
          className="flex items-center gap-2 px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl text-sm font-semibold text-white transition-all whitespace-nowrap"
        >
          {requesting || polling ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {polling ? 'Scanning your network…' : requesting ? 'Requesting…' : 'Auto-Scan with Edge Agent'}
        </button>
        <button
          onClick={() => void fetchDiscovered()}
          disabled={polling}
          className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 disabled:opacity-50 rounded-xl text-sm font-medium text-white/70 transition-all whitespace-nowrap"
        >
          <Network className="w-4 h-4" /> Refresh List
        </button>
      </div>

      {polling && (
        <div className="flex items-center gap-3 text-sm text-white/50 py-2">
          <Loader2 className="w-5 h-5 animate-spin text-violet-400" />
          Waiting for the edge agent to report discovered cameras…
        </div>
      )}

      {cameras.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-2">
          {cameras.map((cam) => (
            <EdgeDiscoveryCard key={cam.camera_id} cam={cam} onConfirmed={handleConfirmed} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ─── Section B: Manual Add Form (with brand presets + auto-detect + tooltips) ──

function ManualAddSectionWrapper({
  initialIp,
  initialPort,
  onSaved,
  onOpenChat,
}: {
  initialIp: string;
  initialPort: number;
  onSaved: () => void;
  onOpenChat: (msg: string) => void;
}) {
  const [form, setForm] = useState({ ...BLANK_FORM, ip: initialIp, port: initialPort });
  const [selectedBrand, setSelectedBrand] = useState('generic');
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  // Auto-detect state
  const [detecting, setDetecting] = useState(false);
  const [detectProgress, setDetectProgress] = useState<{ tried: number; total: number } | null>(null);

  const set = (key: keyof typeof BLANK_FORM) => (v: string) =>
    setForm((f) => ({ ...f, [key]: v }));

  // When brand changes, auto-fill port and first path
  const handleBrandChange = (brand: string) => {
    setSelectedBrand(brand);
    const preset = BRAND_RTSP_PRESETS[brand];
    if (preset) {
      setForm((f) => ({
        ...f,
        port: preset.port,
        rtsp_path: preset.paths[0],
      }));
    }
  };

  const handleTest = async () => {
    if (!form.ip) { toast.error('IP / Host is required.'); return; }
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.post<TestResult>('/cameras/test', {
        ip: form.ip,
        port: Number(form.port),
        username: form.username || undefined,
        password: form.password || undefined,
        rtsp_path: form.rtsp_path || '/',
      });
      setTestResult(res.data);
      if (res.data.success) toast.success('Connection successful!');
      else if (res.data.lan_unreachable)
        toast.success('LAN camera detected — click "Save Camera" and your Edge Agent will validate it locally.');
      else toast.error(res.data.error ?? 'Connection failed.');
    } catch (err: unknown) {
      setTestResult({ success: false, error: (err as Error).message });
      toast.error((err as Error).message ?? 'Test failed.');
    } finally {
      setTesting(false);
    }
  };

  const handleAutoDetect = async () => {
    if (!form.ip) { toast.error('IP / Host is required before auto-detecting.'); return; }
    setDetecting(true);
    setDetectProgress({ tried: 0, total: 24 });
    setTestResult(null);

    // Simulate incremental progress while waiting for the real response
    let fakeCount = 0;
    const totalPaths = Object.values(BRAND_RTSP_PRESETS).flatMap((p) => p.paths).length;
    const progressInterval = setInterval(() => {
      fakeCount = Math.min(fakeCount + 1, totalPaths - 1);
      setDetectProgress({ tried: fakeCount, total: totalPaths });
    }, 1200);

    try {
      const res = await api.post<AutoDetectResult>('/cameras/auto-detect-path', {
        ip: form.ip,
        port: Number(form.port),
        username: form.username || undefined,
        password: form.password || undefined,
      });
      clearInterval(progressInterval);
      setDetectProgress(null);

      if (res.data.success && res.data.path) {
        setForm((f) => ({
          ...f,
          rtsp_path: res.data.path!,
          port: res.data.port ?? f.port,
        }));
        if (res.data.brand_detected) {
          const brandKey = res.data.brand_detected.toLowerCase();
          if (BRAND_RTSP_PRESETS[brandKey]) setSelectedBrand(brandKey);
        }
        toast.success(
          `Path detected${res.data.brand_detected ? ` (${res.data.brand_detected})` : ''}: ${res.data.path}`,
        );
        // Also set a fake successful test result if thumbnail came back
        if (res.data.thumbnail_base64) {
          setTestResult({ success: true, thumbnail_base64: res.data.thumbnail_base64 });
        }
      } else if ((res.data as { queued?: boolean; job_id?: string }).queued) {
        // LAN camera — the probe runs on the user's Edge Agent. Poll for the result.
        const jobId = (res.data as { job_id?: string }).job_id!;
        toast('Camera is on your LAN — probing through your Edge Agent (up to ~90s)…', { icon: '📡' });
        const deadline = Date.now() + 95_000;
        let finished = false;
        while (Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, 4000));
          try {
            const poll = await api.get<{
              status: string; success?: boolean; rtsp_path?: string;
              rtsp_url?: string; error?: string;
            }>(`/cameras/auto-detect-path/result/${jobId}`);
            if (poll.data.status === 'done') {
              finished = true;
              if (poll.data.success && poll.data.rtsp_path) {
                setForm((f) => ({ ...f, rtsp_path: poll.data.rtsp_path! }));
                toast.success(`Edge Agent found a working path: ${poll.data.rtsp_path}`);
              } else {
                toast.error(poll.data.error ?? 'Edge Agent could not find a working RTSP path. Check the IP, port and camera credentials.');
              }
              break;
            }
            if (poll.data.status === 'expired') {
              finished = true;
              toast.error('Probe expired — please try Auto-Detect again.');
              break;
            }
          } catch { /* transient — keep polling */ }
        }
        if (!finished) {
          toast.error('Edge Agent did not respond in time. Make sure the agent is running on a PC in the same network as the camera, then retry.');
        }
      } else {
        toast.error(res.data.message ?? 'Could not auto-detect RTSP path.');
      }
    } catch (err: unknown) {
      clearInterval(progressInterval);
      setDetectProgress(null);
      toast.error((err as Error).message ?? 'Auto-detect failed.');
    } finally {
      setDetecting(false);
      setDetectProgress(null);
    }
  };

  const handleSave = async () => {
    if (!form.name) { toast.error('Camera name is required.'); return; }
    if (!form.location) { toast.error('Location is required.'); return; }
    if (!form.ip) { toast.error('IP / Host is required.'); return; }
    setSaving(true);
    try {
      await api.post('/cameras', {
        name: form.name,
        location: form.location,
        ip: form.ip,
        port: Number(form.port),
        username: form.username || undefined,
        password: form.password || undefined,
        rtsp_path: form.rtsp_path || '/',
        resolution: form.resolution,
        fps: Number(form.fps),
        enabled: form.enabled,
        low_light_mode: form.low_light_mode,
      });
      toast.success(`Camera "${form.name}" added!`);
      setForm({ ...BLANK_FORM });
      setSelectedBrand('generic');
      setTestResult(null);
      onSaved();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Failed to save camera.');
    } finally {
      setSaving(false);
    }
  };

  // A camera can be saved when the cloud test succeeded, OR when the test
  // reported the camera is on a private LAN the cloud cannot reach — those are
  // validated locally by the on-site Edge Agent, so we must not block Save.
  const canSave = testResult?.success === true || testResult?.lan_unreachable === true;

  const brandLabel = BRAND_OPTIONS.find((b) => b.value === selectedBrand)?.label ?? 'Generic';

  return (
    <SectionCard title="B — Manual Add">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

        {/* Camera Brand — full width */}
        <div className="sm:col-span-2">
          <FieldLabel>
            Camera Brand
            <InfoTooltip text="Pick your camera brand so we can auto-fill the correct stream settings. If unsure, leave as 'Generic'." />
          </FieldLabel>
          <select
            value={selectedBrand}
            onChange={(e) => handleBrandChange(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500/60 transition-colors"
          >
            {BRAND_OPTIONS.map((b) => (
              <option key={b.value} value={b.value} className="bg-slate-900">
                {b.label}
              </option>
            ))}
          </select>
        </div>

        {/* Name */}
        <div>
          <FieldLabel>
            Camera Name *
            <InfoTooltip text="Any friendly name — e.g. 'Front Door', 'Cashier Counter'." />
          </FieldLabel>
          <TextInput value={form.name} onChange={set('name')} placeholder="Entrance Cam" />
        </div>

        {/* Location */}
        <div>
          <FieldLabel>
            Location *
            <InfoTooltip text="Where the camera is installed — e.g. 'Store 1 – Entrance'." />
          </FieldLabel>
          <TextInput value={form.location} onChange={set('location')} placeholder="Zone A – Front Door" />
        </div>

        {/* IP */}
        <div>
          <FieldLabel>
            IP / Host *
            <InfoTooltip text="The local IP address of the camera. Check your router's admin page, or look on the camera's back sticker. Usually starts with 192.168…" />
          </FieldLabel>
          <TextInput value={form.ip} onChange={set('ip')} placeholder="192.168.1.100" />
        </div>

        {/* Port */}
        <div>
          <FieldLabel>
            Port
            <InfoTooltip text="Usually 554. Only change if you configured a custom port on the camera." />
          </FieldLabel>
          <TextInput value={form.port} onChange={set('port')} type="number" placeholder="554" />
        </div>

        {/* Username */}
        <div>
          <FieldLabel>
            Username
            <InfoTooltip text="The login you set for the camera's web interface. Default is often 'admin' or printed on the camera sticker." />
          </FieldLabel>
          <TextInput value={form.username} onChange={set('username')} placeholder="admin" />
        </div>

        {/* Password */}
        <div>
          <FieldLabel>
            Password
            <InfoTooltip text="The password for your camera's web interface. Default is often 'admin' or 'admin123' — check the sticker on the camera." />
          </FieldLabel>
          <TextInput value={form.password} onChange={set('password')} type="password" placeholder="••••••" />
        </div>

        {/* RTSP Path — with auto-detect button */}
        <div className="sm:col-span-2">
          <FieldLabel>
            RTSP Path
            <InfoTooltip text="The stream URL path. Pick your brand above and we auto-fill this. If unsure, click 'Auto-Detect'." />
          </FieldLabel>
          <div className="flex gap-2">
            <TextInput value={form.rtsp_path} onChange={set('rtsp_path')} placeholder="/" className="flex-1" />
            <button
              onClick={handleAutoDetect}
              disabled={detecting || !form.ip}
              title="Let AI scan all known paths to find your stream automatically"
              className="flex items-center gap-2 px-4 py-2 bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/30 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-sm font-medium text-cyan-300 transition-all whitespace-nowrap"
            >
              {detecting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              {detecting ? 'Detecting…' : 'Auto-Detect Path (AI)'}
            </button>
          </div>

          {/* Progress bar during auto-detect */}
          <AnimatePresence>
            {detecting && detectProgress && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-2"
              >
                <div className="flex items-center gap-2 text-xs text-cyan-400/70">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Trying paths… {detectProgress.tried}/{detectProgress.total}
                </div>
                <div className="mt-1 h-1 bg-white/10 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-cyan-500/60 rounded-full"
                    animate={{ width: `${(detectProgress.tried / detectProgress.total) * 100}%` }}
                    transition={{ ease: 'linear' }}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Preset path hints */}
          {selectedBrand !== 'generic' && BRAND_RTSP_PRESETS[selectedBrand]?.paths.length > 1 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {BRAND_RTSP_PRESETS[selectedBrand].paths.map((p) => (
                <button
                  key={p}
                  onClick={() => setForm((f) => ({ ...f, rtsp_path: p }))}
                  className={clsx(
                    'text-xs px-2 py-0.5 rounded-lg border transition-all',
                    form.rtsp_path === p
                      ? 'border-violet-500/60 bg-violet-500/15 text-violet-300'
                      : 'border-white/10 text-white/30 hover:text-white/60 hover:border-white/20',
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Resolution */}
        <div>
          <FieldLabel>
            Resolution
            <InfoTooltip text="Video quality. 1920x1080 is highest quality but uses more bandwidth. Use 720p if your network is slow." />
          </FieldLabel>
          <select
            value={form.resolution}
            onChange={(e) => setForm((f) => ({ ...f, resolution: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500/60 transition-colors"
          >
            <option value="1920x1080">1920×1080 (Full HD)</option>
            <option value="1280x720">1280×720 (HD)</option>
            <option value="640x480">640×480 (SD)</option>
          </select>
        </div>

        {/* FPS */}
        <div>
          <FieldLabel>
            FPS Target
            <InfoTooltip text="Frames per second. 15 is smooth enough for most retail use and saves resources. Use 30 only for fast-action areas." />
          </FieldLabel>
          <TextInput value={form.fps} onChange={set('fps')} type="number" placeholder="15" />
        </div>
      </div>

      {/* Thumbnail preview */}
      <AnimatePresence>
        {testResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4"
          >
            {testResult.success && testResult.thumbnail_base64 ? (
              <div className="rounded-xl overflow-hidden border border-emerald-500/30 max-w-sm">
                <img
                  src={`data:image/jpeg;base64,${testResult.thumbnail_base64}`}
                  alt="Camera preview"
                  className="w-full object-cover"
                />
                <div className="flex items-center gap-2 px-3 py-2 bg-emerald-500/10 text-emerald-400 text-xs font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Connection successful
                </div>
              </div>
            ) : testResult.success ? (
              <div className="flex items-center gap-2 text-emerald-400 text-sm">
                <CheckCircle2 className="w-4 h-4" /> Connected (no frame captured)
              </div>
            ) : testResult.lan_unreachable ? (
              <div className="flex items-start gap-2 text-amber-300 text-sm bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2.5">
                <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                <span>
                  This camera is on your local network, so the cloud can't test it directly — that's normal.
                  Click <strong>Save Camera</strong> and your on-site Edge Agent will connect to it locally and start monitoring.
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-red-400 text-sm">
                <XCircle className="w-4 h-4" /> {testResult.error ?? 'Connection failed'}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Actions */}
      <div className="flex flex-wrap gap-3 mt-5 items-center">
        <button
          onClick={handleTest}
          disabled={testing || !form.ip}
          className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-sm font-medium text-white transition-all"
        >
          {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube2 className="w-4 h-4" />}
          Test Connection
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !canSave}
          className="flex items-center gap-2 px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-sm font-semibold text-white transition-all"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Save Camera
        </button>
        {!canSave && !testing && (
          <p className="text-xs text-white/30">Run &quot;Test Connection&quot; first — for LAN cameras it will let you Save right away.</p>
        )}
      </div>

      {/* Floating help nudge inside the card */}
      <div className="mt-5 pt-4 border-t border-white/5 flex items-center justify-between">
        <p className="text-xs text-white/20">Having trouble? Our AI assistant can guide you step by step.</p>
        <button
          onClick={() =>
            onOpenChat(
              `I'm trying to add my camera. Brand: ${brandLabel}. I need help finding the RTSP path / IP / credentials.`,
            )
          }
          className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600/15 hover:bg-violet-600/25 border border-violet-500/25 rounded-lg text-xs font-medium text-violet-300 transition-all whitespace-nowrap"
        >
          <MessageCircle className="w-3.5 h-3.5" /> Ask AI
        </button>
      </div>
    </SectionCard>
  );
}

// ─── Section C: Camera List ───────────────────────────────────────────────────

function CameraListSection() {
  const qc = useQueryClient();
  const { data: cameras = [], isLoading } = useCameras();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Delete camera "${name}"? This cannot be undone.`)) return;
    setDeletingId(id);
    try {
      await api.delete(`/cameras/${id}`);
      toast.success(`Camera "${name}" deleted.`);
      void qc.invalidateQueries({ queryKey: queryKeys.cameras });
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Failed to delete camera.');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <SectionCard title="C — Registered Cameras">
      {isLoading ? (
        <div className="flex items-center gap-2 text-white/30 text-sm py-4">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading cameras…
        </div>
      ) : cameras.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-white/20 gap-3">
          <Camera className="w-10 h-10" />
          <p className="text-sm">No cameras registered yet.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {cameras.map((cam) => (
            <CameraRow
              key={cam.id}
              cam={cam}
              deleting={deletingId === cam.id}
              onDelete={() => handleDelete(cam.id, cam.name)}
            />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ─── Single camera row with per-camera sensitivity slider ─────────────────────

function sensitivityLabel(t: number): string {
  if (t <= 0.4) return 'High catch-rate (more alerts)';
  if (t >= 0.7) return 'Low false-alarms (fewer alerts)';
  return 'Balanced';
}

function CameraRow({
  cam,
  deleting,
  onDelete,
}: {
  cam: CameraModel;
  deleting: boolean;
  onDelete: () => void;
}) {
  const qc = useQueryClient();
  const updateSensitivity = useUpdateCameraSensitivity();
  const [threshold, setThreshold] = useState<number>(cam.confidenceThreshold ?? 0.5);

  // ── Edit state ──
  const [editing, setEditing] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editName, setEditName] = useState(cam.name);
  const [editLocation, setEditLocation] = useState(cam.location ?? '');
  const [editRtsp, setEditRtsp] = useState('');

  const handleEditSave = async () => {
    if (!editName.trim()) { toast.error('Camera name cannot be empty.'); return; }
    setSavingEdit(true);
    try {
      await api.patch(`/cameras/${cam.id}`, {
        name: editName.trim(),
        location: editLocation.trim() || undefined,
        rtsp_url: editRtsp.trim() || undefined,
      });
      toast.success(`Camera "${editName.trim()}" updated. The Edge Agent will pick it up on next sync.`);
      setEditing(false);
      setEditRtsp('');
      void qc.invalidateQueries({ queryKey: queryKeys.cameras });
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Failed to update camera.');
    } finally {
      setSavingEdit(false);
    }
  };

  // Keep local slider in sync if the server value changes (e.g. refetch).
  useEffect(() => {
    setThreshold(cam.confidenceThreshold ?? 0.5);
  }, [cam.confidenceThreshold]);

  // Debounced PATCH so we don't fire on every pixel of slider drag.
  const commit = (value: number) => {
    updateSensitivity.mutate(
      { cameraId: cam.id, threshold: value },
      {
        onSuccess: () => toast.success(`Sensitivity saved for "${cam.name}".`),
        onError: (err) => toast.error((err as Error).message ?? 'Failed to save sensitivity.'),
      },
    );
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 8 }}
      className="flex flex-col gap-3 px-4 py-3 bg-white/3 border border-white/8 rounded-xl hover:border-white/15 transition-colors"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          {cam.online ? (
            <Wifi className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          ) : (
            <WifiOff className="w-4 h-4 text-white/20 flex-shrink-0" />
          )}
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{cam.name}</p>
            <p className="text-xs text-white/40 truncate">{cam.location} · {cam.resolution}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span
            className={clsx(
              'text-xs font-bold px-2 py-0.5 rounded-full',
              cam.online
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-white/5 text-white/30',
            )}
          >
            {cam.online ? 'ONLINE' : 'OFFLINE'}
          </span>
          <button
            onClick={() => {
              setEditName(cam.name);
              setEditLocation(cam.location ?? '');
              setEditRtsp('');
              setEditing((e) => !e);
            }}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-medium transition-all',
              editing
                ? 'bg-violet-500/20 border-violet-500/40 text-violet-300'
                : 'bg-white/5 hover:bg-white/10 border-white/10 hover:border-white/20 text-white/70',
            )}
          >
            <Pencil className="w-3.5 h-3.5" />
            Edit
          </button>
          <button
            onClick={onDelete}
            disabled={deleting}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 hover:border-red-500/40 disabled:opacity-40 rounded-lg text-xs font-medium text-red-400 transition-all"
          >
            {deleting
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Trash2 className="w-3.5 h-3.5" />}
            Delete
          </button>
        </div>
      </div>

      {/* Inline edit form */}
      <AnimatePresence>
        {editing && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-white/5">
              <div>
                <FieldLabel>Camera Name</FieldLabel>
                <TextInput value={editName} onChange={setEditName} placeholder="Entrance Cam" />
              </div>
              <div>
                <FieldLabel>Location</FieldLabel>
                <TextInput value={editLocation} onChange={setEditLocation} placeholder="Zone A – Front Door" />
              </div>
              <div className="sm:col-span-2">
                <FieldLabel>
                  New RTSP URL (leave blank to keep current)
                  <InfoTooltip text="Full RTSP URL including credentials, e.g. rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/101. The current URL is hidden for security — only fill this to replace it." />
                </FieldLabel>
                <TextInput
                  value={editRtsp}
                  onChange={setEditRtsp}
                  placeholder="rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101"
                />
              </div>
              <div className="sm:col-span-2 flex gap-2">
                <button
                  onClick={handleEditSave}
                  disabled={savingEdit}
                  className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl text-xs font-semibold text-white transition-all"
                >
                  {savingEdit ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  {savingEdit ? 'Saving…' : 'Save Changes'}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  disabled={savingEdit}
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 rounded-xl text-xs text-white/60 transition-all"
                >
                  Cancel
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Per-camera detection sensitivity */}
      <div className="flex items-center gap-3 pt-2 border-t border-white/5">
        <SlidersHorizontal className="w-3.5 h-3.5 text-white/30 flex-shrink-0" />
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-xs font-medium text-white/50">Sensitivity</span>
          <InfoTooltip text="Detection confidence threshold. Lower = catches more events but more false alarms. Higher = fewer false alarms but may miss subtle events. Applied to this camera's AI on the next sync." />
        </div>
        <input
          type="range"
          min={0.25}
          max={0.85}
          step={0.05}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          onPointerUp={() => commit(threshold)}
          onKeyUp={() => commit(threshold)}
          className="flex-1 accent-emerald-400 cursor-pointer"
        />
        <span className="text-xs font-mono text-white/60 w-10 text-right">
          {Math.round(threshold * 100)}%
        </span>
        <span className="text-[10px] text-white/30 w-40 text-right hidden sm:inline">
          {updateSensitivity.isPending ? 'Saving…' : sensitivityLabel(threshold)}
        </span>
      </div>
    </motion.div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CamerasManage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [prefill, setPrefill] = useState<{ ip: string; port: number } | null>(null);
  const [formKey, setFormKey] = useState(0);

  // Support chat prefill — state removed (event-driven via window dispatch)

  const handleDiscoveredAdd = (ip: string, port: number) => {
    setPrefill({ ip, port });
    setFormKey((k) => k + 1);
    setTimeout(() => {
      document.getElementById('manual-add-section')?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  const handleSaved = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.cameras });
  };

  const handleOpenChat = (msg: string) => {
    // Dispatch a custom event so SupportChat can pick it up
    window.dispatchEvent(new CustomEvent('vantag:support-chat', { detail: { open: true, prefillMessage: msg } }));
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={() => navigate('/cameras')}
          className="p-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-white">Manage Cameras</h1>
          <p className="text-white/40 text-sm mt-1">
            Add cameras to your Vantag system via network scan or manual entry.
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {/* A — Edge-Agent Auto-Discovery (store LAN) */}
        <EdgeDiscoverySection />

        {/* A2 — VPS-side network scan (fallback for LAN-local deployments) */}
        <AutoScanSection onAdd={handleDiscoveredAdd} />

        {/* B — Manual Add */}
        <div id="manual-add-section">
          <ManualAddSectionWrapper
            key={formKey}
            initialIp={prefill?.ip ?? ''}
            initialPort={prefill?.port ?? 554}
            onSaved={handleSaved}
            onOpenChat={handleOpenChat}
          />
        </div>

        {/* C — Camera List */}
        <CameraListSection />
      </div>

      {/* Fixed floating help button (bottom-right) */}
      <button
        onClick={() =>
          handleOpenChat(
            "I'm trying to add my camera. I need help finding the RTSP path / IP / credentials.",
          )
        }
        className="fixed bottom-24 right-6 z-40 flex items-center gap-2 px-4 py-3 bg-gradient-to-br from-violet-600 to-purple-700 hover:from-violet-500 hover:to-purple-600 rounded-2xl text-white text-sm font-semibold shadow-xl transition-all hover:scale-105"
        title="Open AI support chat for camera setup help"
      >
        <MessageCircle className="w-4 h-4" />
        Need help setting up?
      </button>
    </div>
  );
}
