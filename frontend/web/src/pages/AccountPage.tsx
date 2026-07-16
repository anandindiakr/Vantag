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

interface ChannelSettings {
  enabled?: boolean;
  provider?: string;
  account_sid?: string;
  auth_token?: string;
  from_number?: string;
  to_number?: string;
  auth_key?: string;
  api_key?: string;
  api_secret?: string;
  sender_id?: string;
  phone_number_id?: string;
  access_token?: string;
  source_number?: string;
  app_name?: string;
  url?: string;
  method?: string;
  body_template?: string;
}

interface EmailChannelSettings {
  enabled?: boolean;
  to_email?: string;
}

interface AlertSettings {
  min_severity?: string;
  sms?: ChannelSettings;
  whatsapp?: ChannelSettings;
  email?: EmailChannelSettings;
}

// ─── Alert provider catalog (wizard) ─────────────────────────────────────────

interface ProviderField {
  key: keyof ChannelSettings;
  label: string;
  placeholder: string;
  secret?: boolean;
}

interface ProviderDef {
  id: string;
  label: string;
  region: string;
  steps: string[];
  fields: ProviderField[];
}

const TO_FIELD: ProviderField = { key: 'to_number', label: 'Your phone (receives alerts)', placeholder: '+919876543210' };

const SMS_PROVIDERS: ProviderDef[] = [
  {
    id: 'twilio', label: 'Twilio', region: 'Global',
    steps: [
      'Sign up at twilio.com and buy/claim a phone number',
      'Copy Account SID and Auth Token from the Twilio Console dashboard',
      'Enter them below with your Twilio number as "From"',
    ],
    fields: [
      { key: 'account_sid', label: 'Account SID', placeholder: 'ACxxxxxxxxxxxxxxxx' },
      { key: 'auth_token', label: 'Auth Token', placeholder: 'Twilio Auth Token', secret: true },
      { key: 'from_number', label: 'From number (Twilio)', placeholder: '+1415XXXXXXX' },
      TO_FIELD,
    ],
  },
  {
    id: 'msg91', label: 'MSG91', region: 'India',
    steps: [
      'Sign up at msg91.com (popular Indian SMS provider)',
      'Go to Settings → API Keys and copy your Auth Key',
      'Optionally register a 6-letter Sender ID (e.g. RTLNZR) under DLT',
    ],
    fields: [
      { key: 'auth_key', label: 'Auth Key', placeholder: 'MSG91 Auth Key', secret: true },
      { key: 'sender_id', label: 'Sender ID (6 letters)', placeholder: 'RTLNZR' },
      TO_FIELD,
    ],
  },
  {
    id: 'textlocal', label: 'Textlocal', region: 'India',
    steps: [
      'Sign up at textlocal.in',
      'Go to Settings → API Keys → Create API Key',
      'Optionally set a 6-letter Sender ID',
    ],
    fields: [
      { key: 'api_key', label: 'API Key', placeholder: 'Textlocal API Key', secret: true },
      { key: 'sender_id', label: 'Sender ID (6 letters)', placeholder: 'TXTLCL' },
      TO_FIELD,
    ],
  },
  {
    id: 'vonage', label: 'Vonage (Nexmo)', region: 'Global',
    steps: [
      'Sign up at vonage.com (API dashboard)',
      'Copy API Key and API Secret from the dashboard homepage',
    ],
    fields: [
      { key: 'api_key', label: 'API Key', placeholder: 'Vonage API Key' },
      { key: 'api_secret', label: 'API Secret', placeholder: 'Vonage API Secret', secret: true },
      { key: 'from_number', label: 'From / Sender name', placeholder: 'RetailNazar' },
      TO_FIELD,
    ],
  },
  {
    id: 'http', label: 'My local telecom (HTTP gateway)', region: 'Any country',
    steps: [
      'Ask your local SMS provider for their "HTTP API" documentation',
      'Paste their send URL below using {to} and {message} placeholders',
      'Example: https://sms.provider.com/send?key=XXXX&to={to}&text={message}',
    ],
    fields: [
      { key: 'url', label: 'Gateway URL (use {to} and {message})', placeholder: 'https://sms.provider.com/send?key=XX&to={to}&text={message}' },
      { key: 'method', label: 'Method (GET or POST)', placeholder: 'GET' },
      { key: 'body_template', label: 'POST body template (optional)', placeholder: '{"to":"{to}","text":"{message}"}' },
      TO_FIELD,
    ],
  },
];

const WA_PROVIDERS: ProviderDef[] = [
  {
    id: 'twilio', label: 'Twilio WhatsApp', region: 'Global',
    steps: [
      'In Twilio Console, activate the WhatsApp Sandbox (Messaging → Try it out)',
      'From your phone, send the join code to the sandbox number once',
      'Enter Account SID, Auth Token, and the sandbox number as "From"',
    ],
    fields: [
      { key: 'account_sid', label: 'Account SID', placeholder: 'ACxxxxxxxxxxxxxxxx' },
      { key: 'auth_token', label: 'Auth Token', placeholder: 'Twilio Auth Token', secret: true },
      { key: 'from_number', label: 'From (Twilio WhatsApp number)', placeholder: '+14155238886' },
      { key: 'to_number', label: 'Your WhatsApp number', placeholder: '+919876543210' },
    ],
  },
  {
    id: 'meta', label: 'WhatsApp Cloud API (Meta — official, free)', region: 'Global',
    steps: [
      'Go to developers.facebook.com → Create App → type "Business"',
      'Add the WhatsApp product; Meta gives you a free test number',
      'Copy the Phone Number ID and a permanent Access Token',
      'Important: message the business number once from your phone to open the 24-hour session, then test',
    ],
    fields: [
      { key: 'phone_number_id', label: 'Phone Number ID', placeholder: '1065XXXXXXXXXXX' },
      { key: 'access_token', label: 'Access Token', placeholder: 'EAAG…', secret: true },
      { key: 'to_number', label: 'Your WhatsApp number', placeholder: '+919876543210' },
    ],
  },
  {
    id: 'gupshup', label: 'Gupshup', region: 'India',
    steps: [
      'Sign up at gupshup.io and create a WhatsApp app',
      'Copy the API Key, your approved Source (business) number, and App name',
    ],
    fields: [
      { key: 'api_key', label: 'API Key', placeholder: 'Gupshup API Key', secret: true },
      { key: 'source_number', label: 'Source (business) number', placeholder: '91XXXXXXXXXX' },
      { key: 'app_name', label: 'App name', placeholder: 'RetailNazarApp' },
      { key: 'to_number', label: 'Your WhatsApp number', placeholder: '+919876543210' },
    ],
  },
  {
    id: 'http', label: 'My local provider (HTTP gateway)', region: 'Any country',
    steps: [
      'Ask your WhatsApp API provider for their HTTP send-message URL',
      'Paste it below using {to} and {message} placeholders',
    ],
    fields: [
      { key: 'url', label: 'Gateway URL (use {to} and {message})', placeholder: 'https://wa.provider.com/send?key=XX&to={to}&text={message}' },
      { key: 'method', label: 'Method (GET or POST)', placeholder: 'POST' },
      { key: 'body_template', label: 'POST body template (optional)', placeholder: '{"to":"{to}","text":"{message}"}' },
      { key: 'to_number', label: 'Your WhatsApp number', placeholder: '+919876543210' },
    ],
  },
];

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

function ChannelWizardCard({
  title,
  providers,
  settings,
  onChange,
  onTest,
  testing,
  testResult,
}: {
  title: string;
  providers: ProviderDef[];
  settings: ChannelSettings;
  onChange: (patch: Partial<ChannelSettings>) => void;
  onTest: () => void;
  testing: boolean;
  testResult?: { ok: boolean; message: string };
}) {
  const provider = providers.find((p) => p.id === (settings.provider ?? 'twilio')) ?? providers[0];
  return (
    <div className="p-4 bg-white/3 border border-white/8 rounded-xl mb-4">
      <div className="flex items-center justify-between mb-3">
        <label className="flex items-center gap-2 text-sm font-semibold text-white">
          <input
            type="checkbox"
            checked={!!settings.enabled}
            onChange={(e) => onChange({ enabled: e.target.checked })}
            className="w-4 h-4 accent-emerald-500"
          />
          {title}
        </label>
        {testResult && (
          <span className={`flex items-center gap-1 text-xs ${testResult.ok ? 'text-emerald-400' : 'text-red-400'}`}>
            {testResult.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {testResult.message}
          </span>
        )}
      </div>

      {/* Step 1: pick provider */}
      <div className="mb-3">
        <label className="block text-[11px] font-semibold text-emerald-300/80 mb-1">
          Step 1 — Choose your provider
        </label>
        <select
          value={provider.id}
          onChange={(e) => onChange({ provider: e.target.value })}
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-emerald-500/50 [&>option]:bg-gray-900"
        >
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label} — {p.region}
            </option>
          ))}
        </select>
      </div>

      {/* Step 2: how to get credentials */}
      <div className="mb-3 p-3 bg-blue-500/5 border border-blue-500/15 rounded-lg">
        <p className="text-[11px] font-semibold text-blue-300 mb-1">Step 2 — Get your credentials</p>
        <ol className="text-[11px] text-blue-200/60 space-y-0.5 list-decimal list-inside">
          {provider.steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </div>

      {/* Step 3: fill fields */}
      <p className="text-[11px] font-semibold text-emerald-300/80 mb-1">Step 3 — Enter the details</p>
      <div className="grid grid-cols-2 gap-3">
        {provider.fields.map((f) => (
          <div key={f.key as string} className={f.key === 'url' || f.key === 'body_template' ? 'col-span-2' : ''}>
            <label className="block text-[10px] text-white/40 mb-0.5">{f.label}</label>
            <input
              type={f.secret ? 'password' : 'text'}
              placeholder={f.placeholder}
              value={(settings[f.key] as string) ?? ''}
              onChange={(e) => onChange({ [f.key]: e.target.value } as Partial<ChannelSettings>)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/20 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
        ))}
      </div>

      {/* Step 4: test */}
      <p className="text-[11px] font-semibold text-emerald-300/80 mt-3 mb-1">Step 4 — Send a test message</p>
      <button
        onClick={onTest}
        disabled={testing}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 disabled:opacity-40 rounded-lg text-xs font-medium text-white/70 hover:text-white transition-all"
      >
        {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
        Send Test {title}
      </button>
    </div>
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
    sms: { enabled: false, provider: 'twilio', account_sid: '', auth_token: '', from_number: '', to_number: '' },
    whatsapp: { enabled: false, provider: 'twilio', account_sid: '', auth_token: '', from_number: '', to_number: '' },
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
    patch: Partial<ChannelSettings & EmailChannelSettings>,
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
          event is detected. Pick your SMS / WhatsApp provider (Twilio, MSG91, Textlocal,
          Vonage, Meta WhatsApp Cloud API, Gupshup, or your own local telecom's HTTP
          gateway), follow the built-in steps, then use{' '}
          <strong className="text-white/70">Send Test</strong> to verify each channel
          before saving. See <strong className="text-white/70">Help Center → Alert Dispatch Setup</strong> for
          a full walkthrough.
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
        <ChannelWizardCard
          title="SMS Alerts"
          providers={SMS_PROVIDERS}
          settings={alertSettings.sms ?? {}}
          onChange={(patch) => updateChannel('sms', patch)}
          onTest={() => testChannel('sms')}
          testing={testingChannel === 'sms'}
          testResult={testResult.sms}
        />

        {/* WhatsApp */}
        <ChannelWizardCard
          title="WhatsApp Alerts"
          providers={WA_PROVIDERS}
          settings={alertSettings.whatsapp ?? {}}
          onChange={(patch) => updateChannel('whatsapp', patch)}
          onTest={() => testChannel('whatsapp')}
          testing={testingChannel === 'whatsapp'}
          testResult={testResult.whatsapp}
        />

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
