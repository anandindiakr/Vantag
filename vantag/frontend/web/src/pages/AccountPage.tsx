/**
 * AccountPage — user profile, network configuration, and config.json download.
 *
 * Sections:
 *  1. Profile (shop name, email, plan, region)
 *  2. Network Configuration  (NVR IP, preferred LAN subnet → stored server-side)
 *  3. Download config.json   (pre-filled with api_key + scan_subnet)
 *  4. Active Agents table    (read-only)
 */
import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';
import {
  User, Building2, Network, Download, Copy,
  CheckCircle2, Loader2, RefreshCw, Cpu,
} from 'lucide-react';
import { api } from '../hooks/useApi';

// ─── Types ────────────────────────────────────────────────────────────────────

interface TenantProfile {
  id: string;
  name: string;
  email: string;
  phone?: string;
  address?: string;
  city?: string;
  country: string;
  region: string;
  plan_id: string;
  status: string;
  language: string;
  network_settings?: {
    nvr_ip?: string;
    scan_subnet?: string;
    nvr_brand?: string;
  };
  trial_ends_at?: string;
  created_at: string;
}

interface AgentKeyInfo {
  api_key: string;
  agent_id: string;
  device_type: string;
  device_name: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function SectionCard({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white/4 border border-white/10 rounded-2xl p-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-emerald-500/15">
          <Icon className="w-4 h-4 text-emerald-400" />
        </div>
        <h2 className="text-sm font-bold text-white uppercase tracking-wider">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
      <span className="text-xs text-white/40">{label}</span>
      <span className="text-sm text-white font-medium">{value ?? '—'}</span>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 px-2.5 py-1 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-white/50 hover:text-white/80 transition-all"
    >
      {copied ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AccountPage() {
  const [profile, setProfile] = useState<TenantProfile | null>(null);
  const [agentKey, setAgentKey] = useState<AgentKeyInfo | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);

  // Network settings form state
  const [nvrIp, setNvrIp] = useState('');
  const [scanSubnet, setScanSubnet] = useState('');
  const [nvrBrand, setNvrBrand] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoadingProfile(true);
    // Load profile + agent key in parallel
    Promise.allSettled([
      api.get<TenantProfile>('/tenants/me'),
      api.get<AgentKeyInfo>('/tenants/me/api-key'),
    ]).then(([profileRes, agentRes]) => {
      if (profileRes.status === 'fulfilled') {
        // api.get returns AxiosResponse; actual payload is in .data
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const t: TenantProfile = (profileRes.value as any).data ?? profileRes.value;
        setProfile(t);
        setNvrIp(t.network_settings?.nvr_ip ?? '');
        setScanSubnet(t.network_settings?.scan_subnet ?? '');
        setNvrBrand(t.network_settings?.nvr_brand ?? '');
      } else {
        toast.error('Could not load profile');
      }
      if (agentRes.status === 'fulfilled') {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const k: AgentKeyInfo = (agentRes.value as any).data ?? agentRes.value;
        setAgentKey(k);
      }
    }).finally(() => setLoadingProfile(false));
  }, []);

  const saveNetworkSettings = async () => {
    setSaving(true);
    try {
      await api.patch('/tenants/me/settings', {
        network_settings: {
          nvr_ip: nvrIp.trim(),
          scan_subnet: scanSubnet.trim(),
          nvr_brand: nvrBrand.trim(),
        },
      });
      toast.success('Network settings saved');
      // Refresh profile
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const updated: TenantProfile = ((await api.get<TenantProfile>('/tenants/me')) as any).data ?? (await api.get<TenantProfile>('/tenants/me'));
      setProfile(updated);
    } catch {
      toast.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const downloadConfig = () => {
    if (!agentKey) {
      toast.error('No Edge Agent key found — install the Edge Agent first from the Install Agent page.');
      return;
    }
    const config = {
      _comment: 'Vantag Edge Agent config — generated from your account page',
      api_key: agentKey.api_key,
      agent_id: agentKey.agent_id,
      backend_url: 'https://retail-vantag.com',
      mqtt_host: 'retail-vantag.com',
      mqtt_port: 1883,
      tenant_id: profile?.id ?? '',
      cameras: [],
      inference_device: 'cpu',
      inference_fps: 5,
      confidence_threshold: 0.6,
      event_cooldown_sec: 30,
      log_level: 'INFO',
      scan_subnet: scanSubnet.trim() || '',
    };
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'config.json';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('config.json downloaded — place it next to RetailVantag_EdgeAgent.exe');
  };

  if (loadingProfile) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
      </div>
    );
  }

  const planLabel: Record<string, string> = {
    starter: 'Starter (Trial)',
    basic: 'Basic',
    pro: 'Professional',
    enterprise: 'Enterprise',
  };

  const regionLabel: Record<string, string> = {
    india: 'India',
    singapore: 'Singapore',
    malaysia: 'Malaysia',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-2xl mx-auto space-y-6 p-6"
    >
      <div>
        <h1 className="text-xl font-bold text-white">Account</h1>
        <p className="text-sm text-white/40 mt-1">Profile, network settings, and Edge Agent configuration.</p>
      </div>

      {/* ── Profile ── */}
      <SectionCard icon={User} title="Profile">
        <Row label="Shop / Organisation" value={profile?.name} />
        <Row label="Email" value={profile?.email} />
        <Row label="Phone" value={profile?.phone} />
        <Row label="City" value={profile?.city} />
        <Row label="Plan" value={planLabel[profile?.plan_id ?? ''] ?? profile?.plan_id} />
        <Row label="Status" value={profile?.status?.toUpperCase()} />
        <Row label="Region" value={regionLabel[profile?.region ?? ''] ?? profile?.region} />
        <Row label="Member since" value={profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : undefined} />
      </SectionCard>

      {/* ── Network Configuration ── */}
      <SectionCard icon={Network} title="Network Configuration">
        <p className="text-xs text-white/40 mb-4">
          Provide your NVR/DVR IP and the LAN subnet where your cameras sit. The Edge Agent
          will use the subnet to focus its auto-discovery scan, avoiding false results from
          VPN or cloud network interfaces.
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-white/60 mb-1.5">NVR / DVR IP Address</label>
            <input
              type="text"
              value={nvrIp}
              onChange={(e) => setNvrIp(e.target.value)}
              placeholder="e.g. 192.168.254.50"
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-white/60 mb-1.5">
              Camera LAN Subnet <span className="text-white/30">(used by Edge Agent auto-scan)</span>
            </label>
            <input
              type="text"
              value={scanSubnet}
              onChange={(e) => setScanSubnet(e.target.value)}
              placeholder="e.g. 192.168.254.0/24"
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
            <p className="text-[11px] text-white/25 mt-1">
              Leave blank to auto-detect all private network adapters on the agent machine.
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-white/60 mb-1.5">NVR / DVR Brand <span className="text-white/30">(optional)</span></label>
            <select
              value={nvrBrand}
              onChange={(e) => setNvrBrand(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500/50 [&>option]:bg-gray-900"
            >
              <option value="">Select brand (optional)</option>
              <option value="Hikvision">Hikvision</option>
              <option value="Dahua">Dahua</option>
              <option value="Axis">Axis</option>
              <option value="Uniview">Uniview</option>
              <option value="Hanwha">Hanwha / Samsung</option>
              <option value="CP Plus">CP Plus</option>
              <option value="Bosch">Bosch</option>
              <option value="Pelco">Pelco</option>
              <option value="Other">Other / Generic</option>
            </select>
          </div>

          <button
            onClick={saveNetworkSettings}
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 hover:border-emerald-500/50 disabled:opacity-40 rounded-xl text-sm font-semibold text-emerald-300 transition-all"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Save Network Settings
          </button>
        </div>
      </SectionCard>

      {/* ── Download config.json ── */}
      <SectionCard icon={Cpu} title="Edge Agent Config">
        <p className="text-xs text-white/40 mb-4">
          Download a pre-filled <code className="text-emerald-400">config.json</code> for your
          Windows Edge Agent. It includes your API key, tenant ID, and the subnet you configured
          above. <strong className="text-white/70">Note:</strong> the Edge Agent zip from{' '}
          <code className="text-white/60">Install Edge Agent</code> already contains this file —
          you only need this download if you changed settings above and want to update an
          existing agent.
        </p>

        {agentKey ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between px-4 py-3 bg-white/3 border border-white/8 rounded-xl">
              <div>
                <p className="text-xs text-white/40">API Key</p>
                <p className="text-sm font-mono text-white/60 mt-0.5">
                  {agentKey.api_key.slice(0, 8)}{'•'.repeat(20)}
                </p>
              </div>
              <CopyButton text={agentKey.api_key} />
            </div>

            <button
              onClick={downloadConfig}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-500/15 hover:bg-blue-500/25 border border-blue-500/25 hover:border-blue-500/45 rounded-xl text-sm font-semibold text-blue-300 transition-all"
            >
              <Download className="w-4 h-4" />
              Download config.json
            </button>

            <div className="mt-3 p-4 bg-amber-500/5 border border-amber-500/15 rounded-xl text-xs text-amber-200/70 space-y-1.5">
              <p className="font-semibold text-amber-300">How to update an existing agent:</p>
              <p>1. Copy this <code>config.json</code> into your extracted Edge Agent folder — the same folder that has <code>run.bat</code> (replace the old file)</p>
              <p>2. Double-click <code>run.bat</code> to start (or restart) the agent — keep that window open or minimised</p>
              <p>3. Within ~1 minute the Agent Status page shows ONLINE and cameras start connecting</p>
              <p>4. If cameras are not found automatically, go to <strong>Manage Cameras → Manual Add</strong></p>
            </div>
          </div>
        ) : (
          <div className="px-4 py-3 bg-white/3 border border-white/8 rounded-xl text-sm text-white/40">
            No Edge Agent registered yet. Install the agent from <strong>Install Edge Agent</strong> first, then come back here to download a pre-filled config.
          </div>
        )}
      </SectionCard>

      {/* ── Your cameras (brief) ── */}
      <SectionCard icon={Building2} title="Camera IPs — Quick Reference">
        <p className="text-xs text-white/40 mb-3">
          These are the IP addresses you have registered. Use them to verify your NVR subnet above.
        </p>
        <div className="text-xs text-white/40 space-y-1">
          <p>Your cameras are managed under <strong className="text-white/60">Manage Cameras</strong>.</p>
          <p>To add cameras manually, go to <strong className="text-white/60">Cameras → Manage Cameras → Manual Add</strong>.</p>
        </div>
      </SectionCard>
    </motion.div>
  );
}
