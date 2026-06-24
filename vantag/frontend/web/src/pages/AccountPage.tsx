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
  CreditCard, ArrowUpCircle, Clock, Receipt, X, ChevronRight,
} from 'lucide-react';
import { api } from '../hooks/useApi';
import { useRazorpay } from '../hooks/useRazorpay';

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

interface BillingPlan {
  id: string;
  name: string;
  max_cameras: number;
  price: number;
  currency: string;
  currency_symbol: string;
  razorpay_plan_id: string;
  features: string[];
}

interface BillingPlansResponse {
  razorpay_key_id: string;
  currency: string;
  current_plan: string;
  plans: BillingPlan[];
}

interface BillingStatus {
  plan_id: string;
  status: string;
  trial_ends_at: string | null;
  trial_days_left: number | null;
  last_payment: { amount: number; currency: string; date: string; invoice_number: string } | null;
}

interface Invoice {
  id: string;
  amount: number;
  currency: string;
  status: string;
  invoice_number: string;
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

// ─── Billing Section Component ────────────────────────────────────────────────

function BillingSection() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [plansData, setPlansData] = useState<BillingPlansResponse | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [payingPlan, setPayingPlan] = useState<string | null>(null);
  const { openCheckout } = useRazorpay();

  useEffect(() => {
    (async () => {
      try {
        const [s, p, inv] = await Promise.all([
          api.get('/billing/status'),
          api.get('/billing/plans'),
          api.get('/billing/invoices'),
        ]);
        setStatus(s as BillingStatus);
        setPlansData(p as BillingPlansResponse);
        setInvoices((inv as { invoices: Invoice[] }).invoices ?? []);
      } catch {
        toast.error('Could not load billing info');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleUpgrade = async (plan: BillingPlan) => {
    if (!plansData) return;
    setPayingPlan(plan.id);
    try {
      const order = await api.post('/billing/order', {
        plan_id: plan.id,
        amount: plan.price,
        currency: plan.currency,
      }) as { order_id: string; amount: number; currency: string };

      openCheckout({
        key: plansData.razorpay_key_id || undefined,  // per-region key (IN / SG / MY)
        orderId: order.order_id,
        amount: order.amount,
        currency: order.currency,
        description: `${plan.name} Plan`,
        onSuccess: async (response) => {
          try {
            await api.post('/billing/verify', {
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_order_id:   response.razorpay_order_id,
              razorpay_signature:  response.razorpay_signature,
              plan_id: plan.id,
            });
            toast.success(`Upgraded to ${plan.name}!`);
            setShowUpgrade(false);
            const s = await api.get('/billing/status') as BillingStatus;
            setStatus(s);
          } catch {
            toast.error('Payment verification failed. Contact support.');
          }
        },
        onDismiss: () => setPayingPlan(null),
      });
    } catch {
      toast.error('Could not initiate payment. Try again.');
    } finally {
      setPayingPlan(null);
    }
  };

  const planLabel: Record<string, string> = {
    starter: 'Starter',
    growth: 'Growth',
    pro: 'Pro',
    proplus: 'Pro Plus',
  };
  const planColor: Record<string, string> = {
    starter: 'text-slate-300',
    growth: 'text-green-300',
    pro: 'text-blue-300',
    proplus: 'text-purple-300',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-24">
        <Loader2 className="w-5 h-5 animate-spin text-white/30" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Current plan banner */}
      <div className="flex items-center justify-between rounded-xl bg-white/5 border border-white/10 px-5 py-4">
        <div className="flex items-center gap-3">
          <CreditCard className="w-5 h-5 text-indigo-300" />
          <div>
            <p className="text-xs text-white/40 mb-0.5">Current plan</p>
            <p className={`text-sm font-semibold ${planColor[status?.plan_id ?? ''] ?? 'text-white'}`}>
              {planLabel[status?.plan_id ?? ''] ?? status?.plan_id ?? '—'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {status?.trial_days_left != null && status.trial_days_left >= 0 && (
            <div className="flex items-center gap-1.5 text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-1.5">
              <Clock className="w-3.5 h-3.5" />
              {status.trial_days_left === 0 ? 'Trial expired' : `${status.trial_days_left} day${status.trial_days_left !== 1 ? 's' : ''} left in trial`}
            </div>
          )}
          <button
            onClick={() => setShowUpgrade(true)}
            className="flex items-center gap-1.5 text-xs bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/30 text-indigo-200 rounded-lg px-3 py-1.5 transition-all"
          >
            <ArrowUpCircle className="w-3.5 h-3.5" />
            Upgrade Plan
          </button>
        </div>
      </div>

      {/* Last payment */}
      {status?.last_payment && (
        <div className="rounded-xl bg-white/5 border border-white/10 px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-white/50">
            <Receipt className="w-4 h-4" />
            Last payment: {new Date(status.last_payment.date).toLocaleDateString()}
          </div>
          <p className="text-xs font-semibold text-white">
            {status.last_payment.currency === 'INR' ? '₹' : status.last_payment.currency === 'SGD' ? 'S$' : 'RM '}
            {status.last_payment.amount.toLocaleString()}
          </p>
        </div>
      )}

      {/* Invoice history */}
      {invoices.length > 0 && (
        <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
          <p className="text-xs font-semibold text-white/40 px-5 pt-3 pb-2 border-b border-white/5">Invoice History</p>
          <div className="divide-y divide-white/5">
            {invoices.slice(0, 5).map((inv) => (
              <div key={inv.id} className="flex items-center justify-between px-5 py-2.5">
                <span className="text-xs text-white/50">{inv.invoice_number} · {new Date(inv.created_at).toLocaleDateString()}</span>
                <span className={`text-xs font-medium ${inv.status === 'paid' ? 'text-green-300' : 'text-amber-300'}`}>
                  {inv.status === 'paid' ? '✓ ' : ''}{inv.currency === 'INR' ? '₹' : inv.currency === 'SGD' ? 'S$' : 'RM '}{inv.amount.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upgrade Modal */}
      {showUpgrade && plansData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="relative w-full max-w-2xl bg-[#0d1117] border border-white/10 rounded-2xl p-6 shadow-2xl"
          >
            <button
              onClick={() => setShowUpgrade(false)}
              className="absolute top-4 right-4 text-white/30 hover:text-white/70"
            >
              <X size={18} />
            </button>
            <h2 className="text-base font-semibold text-white mb-1">Choose a Plan</h2>
            <p className="text-xs text-white/40 mb-5">All plans include a 3-day free trial for new accounts.</p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {plansData.plans.map((plan) => {
                const isCurrent = plan.id === plansData.current_plan;
                const isHigher = ['starter','growth','pro','proplus'].indexOf(plan.id) > ['starter','growth','pro','proplus'].indexOf(plansData.current_plan);
                return (
                  <div
                    key={plan.id}
                    className={`rounded-xl border p-4 flex flex-col gap-2 transition-all ${
                      isCurrent
                        ? 'border-indigo-500/40 bg-indigo-500/10'
                        : 'border-white/10 bg-white/5 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-sm font-semibold ${planColor[plan.id] ?? 'text-white'}`}>{plan.name}</span>
                      {isCurrent && <span className="text-xs text-indigo-300 bg-indigo-500/20 px-2 py-0.5 rounded-full">Current</span>}
                    </div>
                    <p className="text-xl font-bold text-white">
                      {plan.currency_symbol}{plan.price.toLocaleString()}
                      <span className="text-xs font-normal text-white/40">/mo</span>
                    </p>
                    <p className="text-xs text-white/40">Up to {plan.max_cameras} cameras</p>
                    <ul className="text-xs text-white/50 space-y-0.5 mt-1 flex-1">
                      {plan.features.slice(0, 4).map((f, i) => (
                        <li key={i} className="flex items-center gap-1.5">
                          <ChevronRight size={10} className="text-indigo-400 shrink-0" />
                          {f}
                        </li>
                      ))}
                    </ul>
                    <button
                      disabled={isCurrent || !isHigher || payingPlan === plan.id || !plan.razorpay_plan_id}
                      onClick={() => handleUpgrade(plan)}
                      className={`mt-2 w-full py-2 rounded-lg text-xs font-semibold transition-all flex items-center justify-center gap-1.5 ${
                        isCurrent
                          ? 'bg-indigo-500/20 text-indigo-300 cursor-default'
                          : isHigher && plan.razorpay_plan_id
                          ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
                          : 'bg-white/5 text-white/20 cursor-not-allowed'
                      }`}
                    >
                      {payingPlan === plan.id ? (
                        <><Loader2 size={12} className="animate-spin" /> Processing…</>
                      ) : isCurrent ? (
                        'Current Plan'
                      ) : !plan.razorpay_plan_id ? (
                        'Coming Soon'
                      ) : isHigher ? (
                        <><ArrowUpCircle size={12} /> Upgrade</>
                      ) : (
                        'Downgrade'
                      )}
                    </button>
                  </div>
                );
              })}
            </div>

            {!plansData.razorpay_key_id && (
              <p className="mt-4 text-xs text-amber-300 text-center">
                Payment gateway not configured yet. Contact support to upgrade.
              </p>
            )}
          </motion.div>
        </div>
      )}
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

      {/* ── Subscription & Billing ── */}
      <SectionCard icon={CreditCard} title="Subscription & Billing">
        <BillingSection />
      </SectionCard>
    </motion.div>
  );
}
