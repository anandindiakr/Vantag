// frontend/web/src/pages/CamerasManage.tsx
// Camera Management page: auto-scan, manual add (brand-aware), and camera list with delete.
// Features: brand presets, auto-detect RTSP path, contextual help, floating support button.

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Camera, Wifi, WifiOff, Plus, Trash2, TestTube2,
  Loader2, CheckCircle2, XCircle, ArrowLeft, Network, Sparkles,
  MessageCircle,
} from 'lucide-react';
import clsx from 'clsx';
import { useQueryClient } from '@tanstack/react-query';
import { api, useCameras, queryKeys } from '../hooks/useApi';
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

  const canSave = testResult?.success === true;

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
          <p className="text-xs text-white/30">Run &quot;Test Connection&quot; first to enable Save</p>
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
            <motion.div
              key={cam.id}
              layout
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              className="flex items-center justify-between gap-4 px-4 py-3 bg-white/3 border border-white/8 rounded-xl hover:border-white/15 transition-colors"
            >
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
                  onClick={() => handleDelete(cam.id, cam.name)}
                  disabled={deletingId === cam.id}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 hover:border-red-500/40 disabled:opacity-40 rounded-lg text-xs font-medium text-red-400 transition-all"
                >
                  {deletingId === cam.id
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Trash2 className="w-3.5 h-3.5" />}
                  Delete
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </SectionCard>
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
        {/* A — Auto Scan */}
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
