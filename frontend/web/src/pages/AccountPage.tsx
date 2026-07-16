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
  CheckCircle2, Loader2, RefreshCw, Cpu, Bell, Send, XCircle,
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

interface TwilioChannelSettings {
  enabled?: boolean;
  account_sid?: string;
  auth_token?: string;
  from_number?: string;
  to_number?: string;
}

interface EmailChannelSettings {
  enabled?: boolean;
  to_email?: string;
}

interface AlertSettings {
  min_severity?: string;
  sms?: TwilioChannelSettings;
  whatsapp?: TwilioChannelSettings;
  email?: EmailChannelSettings;
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

  // Alert Dispatch form state
  const [alertSettings, setAlertSettings] = useState<AlertSettings>({
    min_severity: 'MEDIUM',
    sms: { enabled: false, account_sid: '', auth_token: '', from_number: '', to_number: '' },
    whatsapp: { enabled: false, account_sid: '', auth_token: '', from_number: '', to_number: '' },
    email: { enabled: false, to_email: '' },
  });
  const [savingAlerts, setSavingAlerts] = useState(false);
  const [testingChannel, setTestingChannel] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; message: string }>>({});

  useEffect(() => {
    setLoadingProfile(true);
    // Load profile + agent key in parallel
    Promise.allSettled([
      api.get<TenantProfile>('/tenants/me'),
      api.get<AgentKeyInfo>('/tenants/me/api-key'),
      api.get<{ alert_settings: AlertSettings }>('/tenants/me/alert-settings'),
    ]).then(([profileRes, agentRes, alertRes]) => {
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
      if (alertRes.status === 'fulfilled') {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const payload = (alertRes.value as any).data ?? alertRes.value;
        const loaded: AlertSettings = payload?.alert_settings ?? {};
        setAlertSettings((prev) => ({
          min_severity: loaded.min_severity ?? prev.min_severity,
          sms: { ...prev.sms, ...loaded.sms },
          whatsapp: { ...prev.whatsapp, ...loaded.whatsapp },
          email: { ...prev.email, ...loaded.email },
        }));
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

  const updateChannel = (
    channel: 'sms' | 'whatsapp' | 'email',
    patch: Partial<TwilioChannelSettings & EmailChannelSettings>,
  ) => {
    setAlertSettings((prev) => ({
      ...prev,
      [channel]: { ...(prev[channel] as object), ...patch },
    }));
  };

  const saveAlertSettings = async () => {
    setSavingAlerts(true);
    try {
      await api.patch('/tenants/me/alert-settings', alertSettings);
      toast.success('Alert dispatch settings saved');
    } catch {
      toast.error('Failed to save alert settings');
    } finally {
      setSavingAlerts(false);
    }
  };

  const testChannel = async (channel: 'sms' | 'whatsapp' | 'email') => {
    setTestingChannel(channel);
    setTestResult((prev) => ({ ...prev, [channel]: undefined as unknown as { ok: boolean; message: string } }));
    try {
      const res = await api.post('/tenants/me/alert-settings/test', {
        channel,
        alert_settings: alertSettings,
      });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const payload = (res as any).data ?? res;
      const ok = payload?.success ?? payload?.ok ?? true;
      const message = payload?.message ?? payload?.detail ?? (ok ? 'Test alert sent successfully' : 'Test failed');
      setTestResult((prev) => ({ ...prev, [channel]: { ok, message } }));
      if (ok) {
        toast.success(`${channel.toUpperCase()} test alert sent`);
      } else {
        toast.error(message);
      }
    } catch (err) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const message = (err as any)?.response?.data?.detail ?? (err as any)?.message ?? 'Test failed — check credentials';
      setTestResult((prev) => ({ ...prev, [channel]: { ok: false, message } }));
      toast.error(message);
    } finally {
      setTestingChannel(null);
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
    starter: 'Starter',
    growth: 'Growth',
    pro: 'Pro',
    proplus: 'Pro Plus',
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

      {/* ── Alert Dispatch ── */}
      <SectionCard icon={Bell} title="Alert Dispatch">
        <p className="text-xs text-white/40 mb-4">
          Configure how you get notified when a theft, POS anomaly, or other security
          event is detected. Enable SMS and/or WhatsApp (via Twilio) and/or Email, then
          use <strong className="text-white/70">Test</strong> to verify each channel
          before saving. See <strong className="text-white/70">Help Center → Alert Dispatch Setup</strong> for
          a full walkthrough on getting Twilio credentials.
        </p>

        <div className="mb-5">
          <label className="block text-xs font-medium text-white/60 mb-1.5">Minimum Severity to Alert</label>
          <select
            value={alertSettings.min_severity ?? 'MEDIUM'}
            onChange={(e) => setAlertSettings((prev) => ({ ...prev, min_severity: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500/50 [&>option]:bg-gray-900"
          >
            <option value="LOW">LOW — alert on everything</option>
            <option value="MEDIUM">MEDIUM — skip low-confidence events</option>
            <option value="HIGH">HIGH — only confident detections</option>
            <option value="CRITICAL">CRITICAL — only most severe events</option>
          </select>
        </div>

        {/* SMS */}
        <div className="p-4 bg-white/3 border border-white/8 rounded-xl mb-4">
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-white">
              <input
                type="checkbox"
                checked={!!alertSettings.sms?.enabled}
                onChange={(e) => updateChannel('sms', { enabled: e.target.checked })}
                className="w-4 h-4 accent-emerald-500"
              />
              SMS (via Twilio)
            </label>
            {testResult.sms && (
              <span className={`flex items-center gap-1 text-xs ${testResult.sms.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                {testResult.sms.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                {testResult.sms.message}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input
              type="text"
              placeholder="Twilio Account SID"
              value={alertSettings.sms?.account_sid ?? ''}
              onChange={(e) => updateChannel('sms', { account_sid: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
            <input
              type="password"
              placeholder="Twilio Auth Token"
              value={alertSettings.sms?.auth_token ?? ''}
              onChange={(e) => updateChannel('sms', { auth_token: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
            <input
              type="text"
              placeholder="From Number (e.g. +1415XXXXXXX)"
              value={alertSettings.sms?.from_number ?? ''}
              onChange={(e) => updateChannel('sms', { from_number: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
            <input
              type="text"
              placeholder="To Number (your phone, +91XXXXXXXXXX)"
              value={alertSettings.sms?.to_number ?? ''}
              onChange={(e) => updateChannel('sms', { to_number: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <button
            onClick={() => testChannel('sms')}
            disabled={testingChannel === 'sms'}
            className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 disabled:opacity-40 rounded-lg text-xs font-medium text-white/70 hover:text-white transition-all"
          >
            {testingChannel === 'sms' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Test SMS
          </button>
        </div>

        {/* WhatsApp */}
        <div className="p-4 bg-white/3 border border-white/8 rounded-xl mb-4">
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-white">
              <input
                type="checkbox"
                checked={!!alertSettings.whatsapp?.enabled}
                onChange={(e) => updateChannel('whatsapp', { enabled: e.target.checked })}
                className="w-4 h-4 accent-emerald-500"
              />
              WhatsApp (via Twilio)
            </label>
            {testResult.whatsapp && (
              <span className={`flex items-center gap-1 text-xs ${testResult.whatsapp.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                {testResult.whatsapp.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                {testResult.whatsapp.message}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input
              type="text"
              placeholder="Twilio Account SID"
              value={alertSettings.whatsapp?.account_sid ?? ''}
              onChange={(e) => updateChannel('whatsapp', { account_sid: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
            <input
              type="password"
              placeholder="Twilio Auth Token"
              value={alertSettings.whatsapp?.auth_token ?? ''}
              onChange={(e) => updateChannel('whatsapp', { auth_token: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
            <input
              type="text"
              placeholder="From Number (Twilio WhatsApp sandbox/number)"
              value={alertSettings.whatsapp?.from_number ?? ''}
              onChange={(e) => updateChannel('whatsapp', { from_number: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
            <input
              type="text"
              placeholder="To Number (your WhatsApp, +91XXXXXXXXXX)"
              value={alertSettings.whatsapp?.to_number ?? ''}
              onChange={(e) => updateChannel('whatsapp', { to_number: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <p className="text-[11px] text-white/25 mt-2">
            The <code>whatsapp:</code> prefix is added automatically — enter plain phone numbers only.
          </p>
          <button
            onClick={() => testChannel('whatsapp')}
            disabled={testingChannel === 'whatsapp'}
            className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 disabled:opacity-40 rounded-lg text-xs font-medium text-white/70 hover:text-white transition-all"
          >
            {testingChannel === 'whatsapp' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Test WhatsApp
          </button>
        </div>

        {/* Email */}
        <div className="p-4 bg-white/3 border border-white/8 rounded-xl mb-5">
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-white">
              <input
                type="checkbox"
                checked={!!alertSettings.email?.enabled}
                onChange={(e) => updateChannel('email', { enabled: e.target.checked })}
                className="w-4 h-4 accent-emerald-500"
              />
              Email
            </label>
            {testResult.email && (
              <span className={`flex items-center gap-1 text-xs ${testResult.email.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                {testResult.email.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                {testResult.email.message}
              </span>
            )}
          </div>
          <input
            type="email"
            placeholder="Alert recipient email address"
            value={alertSettings.email?.to_email ?? ''}
            onChange={(e) => updateChannel('email', { to_email: e.target.value })}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
          />
          <button
            onClick={() => testChannel('email')}
            disabled={testingChannel === 'email'}
            className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 disabled:opacity-40 rounded-lg text-xs font-medium text-white/70 hover:text-white transition-all"
          >
            {testingChannel === 'email' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Test Email
          </button>
        </div>

        <button
          onClick={saveAlertSettings}
          disabled={savingAlerts}
          className="flex items-center gap-2 px-5 py-2.5 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 hover:border-emerald-500/50 disabled:opacity-40 rounded-xl text-sm font-semibold text-emerald-300 transition-all"
        >
          {savingAlerts ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Save Alert Dispatch Settings
        </button>
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
