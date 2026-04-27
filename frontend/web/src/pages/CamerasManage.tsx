// frontend/web/src/pages/CamerasManage.tsx
// Camera Management page: auto-scan, manual add, and camera list with delete.

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Camera, Wifi, WifiOff, Search, Plus, Trash2, TestTube2,
  Loader2, CheckCircle2, XCircle, ArrowLeft, Network,
} from 'lucide-react';
import clsx from 'clsx';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useCameras, queryKeys } from '../hooks/useApi';
import toast from 'react-hot-toast';

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
  return <label className="block text-xs font-medium text-white/50 mb-1">{children}</label>;
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

// ─── Section B: Manual Add Form ───────────────────────────────────────────────

function ManualAddSection({ onSaved }: { onSaved: () => void }) {
  const [form, setForm] = useState(BLANK_FORM);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = (key: keyof typeof BLANK_FORM) => (v: string) =>
    setForm((f) => ({ ...f, [key]: v }));

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
      setForm(BLANK_FORM);
      setTestResult(null);
      onSaved();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Failed to save camera.');
    } finally {
      setSaving(false);
    }
  };

  const canSave = testResult?.success === true;

  return (
    <SectionCard title="B — Manual Add">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Name */}
        <div>
          <FieldLabel>Camera Name *</FieldLabel>
          <TextInput value={form.name} onChange={set('name')} placeholder="Entrance Cam" />
        </div>
        {/* Location */}
        <div>
          <FieldLabel>Location *</FieldLabel>
          <TextInput value={form.location} onChange={set('location')} placeholder="Zone A – Front Door" />
        </div>
        {/* IP */}
        <div>
          <FieldLabel>IP / Host *</FieldLabel>
          <TextInput value={form.ip} onChange={set('ip')} placeholder="192.168.1.100" />
        </div>
        {/* Port */}
        <div>
          <FieldLabel>Port</FieldLabel>
          <TextInput value={form.port} onChange={set('port')} type="number" placeholder="554" />
        </div>
        {/* Username */}
        <div>
          <FieldLabel>Username</FieldLabel>
          <TextInput value={form.username} onChange={set('username')} placeholder="admin" />
        </div>
        {/* Password */}
        <div>
          <FieldLabel>Password</FieldLabel>
          <TextInput value={form.password} onChange={set('password')} type="password" placeholder="••••••" />
        </div>
        {/* RTSP Path */}
        <div>
          <FieldLabel>RTSP Path</FieldLabel>
          <TextInput value={form.rtsp_path} onChange={set('rtsp_path')} placeholder="/" />
        </div>
        {/* Resolution */}
        <div>
          <FieldLabel>Resolution</FieldLabel>
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
          <FieldLabel>FPS Target</FieldLabel>
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
      <div className="flex gap-3 mt-5">
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
          <p className="text-xs text-white/30 self-center">Run "Test Connection" first to enable Save</p>
        )}
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

  // Pre-fill manual form when user clicks "Add" from discovered camera
  const [prefill, setPrefill] = useState<{ ip: string; port: number } | null>(null);

  // A key trick: change a key to reset the ManualAddSection state
  const [formKey, setFormKey] = useState(0);

  const handleDiscoveredAdd = (ip: string, port: number) => {
    setPrefill({ ip, port });
    setFormKey((k) => k + 1);
    // Scroll to manual form
    setTimeout(() => {
      document.getElementById('manual-add-section')?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  const handleSaved = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.cameras });
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
          />
        </div>

        {/* C — Camera List */}
        <CameraListSection />
      </div>
    </div>
  );
}

// Wrapper to allow external ip/port injection without prop-drilling inside ManualAddSection
function ManualAddSectionWrapper({
  initialIp,
  initialPort,
  onSaved,
}: {
  initialIp: string;
  initialPort: number;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({ ...BLANK_FORM, ip: initialIp, port: initialPort });
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = (key: keyof typeof BLANK_FORM) => (v: string) =>
    setForm((f) => ({ ...f, [key]: v }));

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
      setTestResult(null);
      onSaved();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Failed to save camera.');
    } finally {
      setSaving(false);
    }
  };

  const canSave = testResult?.success === true;

  return (
    <SectionCard title="B — Manual Add">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Camera Name *</FieldLabel>
          <TextInput value={form.name} onChange={set('name')} placeholder="Entrance Cam" />
        </div>
        <div>
          <FieldLabel>Location *</FieldLabel>
          <TextInput value={form.location} onChange={set('location')} placeholder="Zone A – Front Door" />
        </div>
        <div>
          <FieldLabel>IP / Host *</FieldLabel>
          <TextInput value={form.ip} onChange={set('ip')} placeholder="192.168.1.100" />
        </div>
        <div>
          <FieldLabel>Port</FieldLabel>
          <TextInput value={form.port} onChange={set('port')} type="number" placeholder="554" />
        </div>
        <div>
          <FieldLabel>Username</FieldLabel>
          <TextInput value={form.username} onChange={set('username')} placeholder="admin" />
        </div>
        <div>
          <FieldLabel>Password</FieldLabel>
          <TextInput value={form.password} onChange={set('password')} type="password" placeholder="••••••" />
        </div>
        <div>
          <FieldLabel>RTSP Path</FieldLabel>
          <TextInput value={form.rtsp_path} onChange={set('rtsp_path')} placeholder="/" />
        </div>
        <div>
          <FieldLabel>Resolution</FieldLabel>
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
        <div>
          <FieldLabel>FPS Target</FieldLabel>
          <TextInput value={form.fps} onChange={set('fps')} type="number" placeholder="15" />
        </div>
      </div>

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
    </SectionCard>
  );
}
