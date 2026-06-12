/**
 * AdminDashboard.tsx — Super-admin platform management panel.
 * Route: /admin  (and sub-routes via hash-based tab navigation)
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  LayoutDashboard, Users, CreditCard, AlertTriangle,
  Network, ShieldAlert, CheckCircle, XCircle,
  RefreshCw, Download, Search, Ban, Play, Trash2,
  ChevronRight, Activity, Globe, Bell,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────

interface AdminStats {
  total_tenants: number;
  active_tenants: number;
  trial_tenants: number;
  suspended_tenants: number;
  total_revenue_inr: number;
  total_revenue_sgd: number;
  total_revenue_myr: number;
  mrr_inr: number;
  mrr_sgd: number;
  mrr_myr: number;
  total_cameras: number;
  total_incidents_today: number;
  total_incidents_30d: number;
  new_signups_today: number;
  new_signups_7d: number;
  churn_7d: number;
  system_health: { db: string; mqtt: string; ai: string };
}

interface TenantRow {
  id: string;
  name: string;
  owner_email: string;
  region: string;
  plan: string;
  status: string;
  cameras: number;
  incidents_30d: number;
  mrr: number;
  created_at: string;
  last_login: string | null;
}

interface PaymentRow {
  id: string;
  tenant_id: string;
  event_type: string;
  razorpay_event_id: string | null;
  processed: boolean;
  created_at: string;
}

interface IncidentRow {
  id: string;
  tenant_id: string;
  type: string;
  severity: string;
  created_at: string;
}

interface AlertRow {
  id: string;
  level: string;
  title: string;
  detail: string | null;
  source: string | null;
  created_at: string;
}

// ── Auth helper ─────────────────────────────────────────────────────────────

function authHeaders() {
  const token = localStorage.getItem('vantag_token') || '';
  return { Authorization: `Bearer ${token}` };
}

async function downloadCsv(url: string, filename: string) {
  try {
    const r = await fetch(url, { headers: authHeaders() });
    if (!r.ok) {
      alert(`Export failed: ${r.status} ${r.statusText}`);
      return;
    }
    const blob = await r.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  } catch (e: any) {
    alert(`Export failed: ${e?.message || e}`);
  }
}

// ── Sub-components ──────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, color = 'violet' }: {
  label: string; value: string | number; sub?: string; color?: string;
}) {
  const colorMap: Record<string, string> = {
    violet: 'from-violet-600/20 to-purple-700/10 border-violet-500/30',
    green:  'from-emerald-600/20 to-emerald-700/10 border-emerald-500/30',
    amber:  'from-amber-600/20 to-amber-700/10 border-amber-500/30',
    red:    'from-red-600/20 to-red-700/10 border-red-500/30',
    cyan:   'from-cyan-600/20 to-cyan-700/10 border-cyan-500/30',
  };
  return (
    <div className={`bg-gradient-to-br ${colorMap[color] || colorMap.violet} border rounded-xl p-5`}>
      <p className="text-xs text-white/40 uppercase tracking-widest font-mono mb-2">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-white/40 mt-1">{sub}</p>}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    active:    'bg-emerald-500/20 text-emerald-400',
    trial:     'bg-cyan-500/20 text-cyan-400',
    suspended: 'bg-red-500/20 text-red-400',
    deleted:   'bg-slate-500/20 text-slate-400',
    cancelled: 'bg-orange-500/20 text-orange-400',
  };
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${map[status] || 'bg-white/10 text-white/50'}`}>
      {status}
    </span>
  );
}

function LevelBadge({ level }: { level: string }) {
  const map: Record<string, string> = {
    info:     'bg-blue-500/20 text-blue-400',
    warning:  'bg-amber-500/20 text-amber-400',
    critical: 'bg-red-500/20 text-red-400',
  };
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${map[level] || 'bg-white/10 text-white/50'}`}>
      {level.toUpperCase()}
    </span>
  );
}

function HealthDot({ status }: { status: string }) {
  return (
    <span className="flex items-center gap-1.5 text-sm">
      {status === 'ok'
        ? <CheckCircle className="w-4 h-4 text-emerald-400" />
        : <XCircle className="w-4 h-4 text-red-400" />}
      <span className={status === 'ok' ? 'text-emerald-400' : 'text-red-400'}>{status}</span>
    </span>
  );
}

// ── ARCHITECTURE DIAGRAM (moved here from public page) ───────────────────────

function ArchitectureTab() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold mb-2">Architecture at a glance</h2>
        <p className="text-white/50 text-sm">Internal reference — not visible on public pages.</p>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-2xl p-8">
        <pre className="text-center text-violet-300 font-mono text-xs md:text-sm overflow-x-auto">
{`  ┌─ Retailer's LAN ──────────────┐       ┌─── Vantag Cloud (VPS) ───┐
  │                               │       │                          │
  │  [IP Camera] ─┐               │       │   Dashboard / Web / App  │
  │  [IP Camera] ─┤               │       │           ▲              │
  │  [IP Camera] ─┼─▶ Edge Agent ─┼──TLS──┼──▶ FastAPI + PostgreSQL  │
  │  [IP Camera] ─┘   (YOLOv8)    │       │           │              │
  │                               │       │      Mosquitto MQTT      │
  │  Video stays LOCAL            │       │                          │
  │  Only events + snapshots      │       │  Razorpay · Let's Encrypt│
  │  leave the LAN (low BW)       │       │                          │
  └───────────────────────────────┘       └──────────────────────────┘`}
        </pre>
      </div>
      <div className="grid md:grid-cols-2 gap-4 text-sm">
        <div className="bg-white/5 border border-white/10 rounded-xl p-5">
          <h3 className="font-bold mb-3 text-violet-400">Edge Stack</h3>
          <ul className="space-y-1.5 text-white/60">
            <li>• YOLOv8 — object detection (ONNX / TensorRT)</li>
            <li>• Python Edge Agent (Windows / Linux / Android)</li>
            <li>• RTSP camera ingestion via OpenCV</li>
            <li>• Local event buffering, TLS egress</li>
          </ul>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-5">
          <h3 className="font-bold mb-3 text-cyan-400">Cloud Stack</h3>
          <ul className="space-y-1.5 text-white/60">
            <li>• FastAPI + SQLAlchemy async (PostgreSQL)</li>
            <li>• Mosquitto MQTT broker (event streaming)</li>
            <li>• Razorpay (INR/SGD/MYR payments)</li>
            <li>• Let's Encrypt TLS · React/Vite frontend</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

// ── MAIN COMPONENT ──────────────────────────────────────────────────────────

type Tab = 'overview' | 'tenants' | 'payments' | 'incidents' | 'alerts' | 'architecture';

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('overview');
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [tenantTotal, setTenantTotal] = useState(0);
  const [tenantSearch, setTenantSearch] = useState('');
  const [tenantStatus, setTenantStatus] = useState('');
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [incidents, setIncidents] = useState<IncidentRow[]>([]);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailTenant, setDetailTenant] = useState<any>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // ── Data fetchers ──────────────────────────────────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/admin/stats', { headers: authHeaders() });
      setStats(data);
    } catch (e: any) {
      if (e?.response?.status === 403) {
        toast.error('Access denied — super-admin only');
        navigate('/dashboard');
      }
    }
  }, [navigate]);

  const fetchTenants = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (tenantSearch) params.set('search', tenantSearch);
      if (tenantStatus) params.set('status', tenantStatus);
      const { data } = await axios.get(`/api/admin/tenants?${params}`, { headers: authHeaders() });
      setTenants(data.tenants || []);
      setTenantTotal(data.total || 0);
    } finally {
      setLoading(false);
    }
  }, [tenantSearch, tenantStatus]);

  const fetchPayments = useCallback(async () => {
    const { data } = await axios.get('/api/admin/payments', { headers: authHeaders() });
    setPayments(data.payments || []);
  }, []);

  const fetchIncidents = useCallback(async () => {
    const { data } = await axios.get('/api/admin/incidents', { headers: authHeaders() });
    setIncidents(data.incidents || []);
  }, []);

  const fetchAlerts = useCallback(async () => {
    const { data } = await axios.get('/api/admin/alerts', { headers: authHeaders() });
    setAlerts(data.alerts || []);
  }, []);

  useEffect(() => {
    fetchStats();
    fetchAlerts();
  }, [fetchStats, fetchAlerts]);

  useEffect(() => {
    if (tab === 'tenants') fetchTenants();
    if (tab === 'payments') fetchPayments();
    if (tab === 'incidents') fetchIncidents();
    if (tab === 'alerts') fetchAlerts();
  }, [tab, fetchTenants, fetchPayments, fetchIncidents, fetchAlerts]);

  useEffect(() => {
    if (tab === 'tenants') fetchTenants();
  }, [tenantSearch, tenantStatus]);

  // ── Tenant actions ─────────────────────────────────────────────────────

  const openDetail = async (id: string) => {
    const { data } = await axios.get(`/api/admin/tenants/${id}`, { headers: authHeaders() });
    setDetailTenant(data);
    setDetailOpen(true);
  };

  const suspendTenant = async (id: string, name: string) => {
    if (!confirm(`Suspend ${name}?`)) return;
    await axios.post(`/api/admin/tenants/${id}/suspend`, {}, { headers: authHeaders() });
    toast.success(`${name} suspended`);
    fetchTenants();
  };

  const resumeTenant = async (id: string, name: string) => {
    await axios.post(`/api/admin/tenants/${id}/resume`, {}, { headers: authHeaders() });
    toast.success(`${name} resumed`);
    fetchTenants();
  };

  const deleteTenant = async (id: string, name: string) => {
    if (!confirm(`Soft-delete ${name}? This can be undone by re-setting status.`)) return;
    await axios.delete(`/api/admin/tenants/${id}`, { headers: authHeaders() });
    toast.success(`${name} deleted`);
    fetchTenants();
  };

  const acknowledgeAlert = async (id: string) => {
    await axios.post(`/api/admin/alerts/${id}/acknowledge`, {}, { headers: authHeaders() });
    toast.success('Alert acknowledged');
    fetchAlerts();
  };

  // ── Tabs config ────────────────────────────────────────────────────────

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'overview',      label: 'Overview',     icon: <LayoutDashboard size={16} /> },
    { key: 'tenants',       label: 'Tenants',       icon: <Users size={16} /> },
    { key: 'payments',      label: 'Payments',      icon: <CreditCard size={16} /> },
    { key: 'incidents',     label: 'Incidents',     icon: <AlertTriangle size={16} /> },
    { key: 'alerts',        label: 'Alerts',        icon: <Bell size={16} />, badge: alerts.length },
    { key: 'architecture',  label: 'Architecture',  icon: <Network size={16} /> },
  ] as any;

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      {/* Header */}
      <div className="border-b border-white/10 px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldAlert className="text-red-400" size={24} />
          <div>
            <h1 className="text-xl font-bold">Admin Panel</h1>
            <p className="text-xs text-white/30">Platform management — super-admin only</p>
          </div>
        </div>
        <button
          onClick={() => { fetchStats(); fetchAlerts(); }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-sm transition-all"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="flex">
        {/* Sidebar tabs */}
        <aside className="w-52 flex-shrink-0 border-r border-white/10 min-h-screen p-4">
          <nav className="space-y-1">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  tab === t.key
                    ? 'bg-violet-600/20 text-violet-400 border border-violet-500/30'
                    : 'text-white/40 hover:text-white hover:bg-white/5'
                }`}
              >
                {t.icon}
                {t.label}
                {(t as any).badge > 0 && (
                  <span className="ml-auto bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                    {(t as any).badge}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 p-8 overflow-auto">

          {/* ── OVERVIEW ── */}
          {tab === 'overview' && stats && (
            <div className="space-y-8">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <KpiCard label="Total Tenants"    value={stats.total_tenants}     color="violet" />
                <KpiCard label="Active"           value={stats.active_tenants}    color="green" />
                <KpiCard label="Trial"            value={stats.trial_tenants}     color="cyan" />
                <KpiCard label="Suspended"        value={stats.suspended_tenants} color="red" />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <KpiCard label="MRR (INR)"        value={`₹${stats.mrr_inr.toLocaleString()}`} color="amber" />
                <KpiCard label="MRR (SGD)"        value={`S$${stats.mrr_sgd.toLocaleString()}`} color="amber" />
                <KpiCard label="MRR (MYR)"        value={`RM${stats.mrr_myr.toLocaleString()}`} color="amber" />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <KpiCard label="New Today"        value={stats.new_signups_today} color="cyan"
                  sub={`+${stats.new_signups_7d} in 7 days`} />
                <KpiCard label="Churn (7d)"       value={stats.churn_7d}          color="red" />
                <KpiCard label="Incidents Today"  value={stats.total_incidents_today} color="violet" />
                <KpiCard label="Incidents (30d)"  value={stats.total_incidents_30d}   color="violet" />
              </div>
              <div className="grid md:grid-cols-2 gap-6">
                <div className="bg-white/5 border border-white/10 rounded-xl p-6">
                  <h3 className="font-bold mb-4 flex items-center gap-2">
                    <Activity size={16} className="text-emerald-400" /> System Health
                  </h3>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white/50">Database</span>
                      <HealthDot status={stats.system_health.db} />
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white/50">MQTT</span>
                      <HealthDot status={stats.system_health.mqtt} />
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white/50">AI Engine</span>
                      <HealthDot status={stats.system_health.ai} />
                    </div>
                  </div>
                </div>
                <div className="bg-white/5 border border-white/10 rounded-xl p-6">
                  <h3 className="font-bold mb-4 flex items-center gap-2">
                    <Globe size={16} className="text-cyan-400" /> Infrastructure
                  </h3>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-sm text-white/50">Total Cameras</span>
                      <span className="font-bold">{stats.total_cameras}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-white/50">Total Revenue INR</span>
                      <span className="font-bold">₹{stats.total_revenue_inr.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-white/50">Total Revenue SGD</span>
                      <span className="font-bold">S${stats.total_revenue_sgd.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-white/50">Total Revenue MYR</span>
                      <span className="font-bold">RM{stats.total_revenue_myr.toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── TENANTS ── */}
          {tab === 'tenants' && (
            <div className="space-y-4">
              <div className="flex items-center gap-4 flex-wrap">
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                  <input
                    value={tenantSearch}
                    onChange={e => setTenantSearch(e.target.value)}
                    placeholder="Search name or email…"
                    className="bg-white/5 border border-white/10 rounded-lg pl-9 pr-4 py-2 text-sm w-64 focus:outline-none focus:border-violet-500/50"
                  />
                </div>
                <select
                  value={tenantStatus}
                  onChange={e => setTenantStatus(e.target.value)}
                  className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none"
                >
                  <option value="">All statuses</option>
                  <option value="trial">Trial</option>
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                  <option value="cancelled">Cancelled</option>
                </select>
                <span className="text-sm text-white/40 ml-auto">{tenantTotal} total</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-white/40 text-xs uppercase tracking-wider">
                      <th className="text-left py-3 pr-4">Name</th>
                      <th className="text-left py-3 pr-4">Email</th>
                      <th className="text-left py-3 pr-4">Region</th>
                      <th className="text-left py-3 pr-4">Plan</th>
                      <th className="text-left py-3 pr-4">Status</th>
                      <th className="text-right py-3 pr-4">Cameras</th>
                      <th className="text-right py-3 pr-4">MRR</th>
                      <th className="text-left py-3 pr-4">Joined</th>
                      <th className="text-center py-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tenants.map((t) => (
                      <tr key={t.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                        <td className="py-3 pr-4 font-semibold">{t.name}</td>
                        <td className="py-3 pr-4 text-white/50 text-xs">{t.owner_email}</td>
                        <td className="py-3 pr-4">
                          <span className="text-xs bg-white/5 px-2 py-0.5 rounded">{t.region}</span>
                        </td>
                        <td className="py-3 pr-4 text-white/60">{t.plan}</td>
                        <td className="py-3 pr-4"><StatusBadge status={t.status} /></td>
                        <td className="py-3 pr-4 text-right">{t.cameras}</td>
                        <td className="py-3 pr-4 text-right">{t.mrr > 0 ? t.mrr.toLocaleString() : '—'}</td>
                        <td className="py-3 pr-4 text-white/40 text-xs">
                          {new Date(t.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-3">
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              onClick={() => openDetail(t.id)}
                              className="p-1.5 rounded hover:bg-white/10 text-white/40 hover:text-white transition-colors"
                              title="View detail"
                            ><ChevronRight size={14} /></button>
                            {t.status !== 'suspended' ? (
                              <button
                                onClick={() => suspendTenant(t.id, t.name)}
                                className="p-1.5 rounded hover:bg-red-500/20 text-white/40 hover:text-red-400 transition-colors"
                                title="Suspend"
                              ><Ban size={14} /></button>
                            ) : (
                              <button
                                onClick={() => resumeTenant(t.id, t.name)}
                                className="p-1.5 rounded hover:bg-emerald-500/20 text-white/40 hover:text-emerald-400 transition-colors"
                                title="Resume"
                              ><Play size={14} /></button>
                            )}
                            <button
                              onClick={() => deleteTenant(t.id, t.name)}
                              className="p-1.5 rounded hover:bg-red-500/20 text-white/40 hover:text-red-400 transition-colors"
                              title="Delete"
                            ><Trash2 size={14} /></button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {tenants.length === 0 && !loading && (
                      <tr><td colSpan={9} className="text-center py-12 text-white/30">No tenants found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── PAYMENTS ── */}
          {tab === 'payments' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold">Payment Events</h2>
                <button
                  onClick={() => downloadCsv('/api/admin/payments/export.csv', 'payments_export.csv')}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-sm transition-all"
                >
                  <Download size={14} /> Export CSV
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-white/40 text-xs uppercase tracking-wider">
                      <th className="text-left py-3 pr-4">ID</th>
                      <th className="text-left py-3 pr-4">Tenant</th>
                      <th className="text-left py-3 pr-4">Event</th>
                      <th className="text-left py-3 pr-4">Razorpay ID</th>
                      <th className="text-center py-3 pr-4">Processed</th>
                      <th className="text-left py-3">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payments.map((p) => (
                      <tr key={p.id} className="border-b border-white/5 hover:bg-white/3">
                        <td className="py-3 pr-4 font-mono text-xs text-white/40">{p.id.slice(0, 8)}…</td>
                        <td className="py-3 pr-4 text-xs text-white/50">{p.tenant_id?.slice(0, 8)}…</td>
                        <td className="py-3 pr-4">{p.event_type}</td>
                        <td className="py-3 pr-4 text-xs text-white/40">{p.razorpay_event_id || '—'}</td>
                        <td className="py-3 pr-4 text-center">
                          {p.processed
                            ? <CheckCircle size={14} className="text-emerald-400 mx-auto" />
                            : <XCircle size={14} className="text-red-400 mx-auto" />}
                        </td>
                        <td className="py-3 text-white/40 text-xs">{new Date(p.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                    {payments.length === 0 && (
                      <tr><td colSpan={6} className="text-center py-12 text-white/30">No payments found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── INCIDENTS ── */}
          {tab === 'incidents' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold">All Incidents</h2>
                <button
                  onClick={() => downloadCsv('/api/admin/incidents/export.csv', 'incidents_export.csv')}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-sm transition-all"
                >
                  <Download size={14} /> Export CSV
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-white/40 text-xs uppercase tracking-wider">
                      <th className="text-left py-3 pr-4">ID</th>
                      <th className="text-left py-3 pr-4">Tenant</th>
                      <th className="text-left py-3 pr-4">Type</th>
                      <th className="text-left py-3 pr-4">Severity</th>
                      <th className="text-left py-3">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.map((i) => (
                      <tr key={i.id} className="border-b border-white/5 hover:bg-white/3">
                        <td className="py-3 pr-4 font-mono text-xs text-white/40">{i.id.slice(0, 8)}…</td>
                        <td className="py-3 pr-4 text-xs text-white/50">{i.tenant_id?.slice(0, 8)}…</td>
                        <td className="py-3 pr-4">{i.type}</td>
                        <td className="py-3 pr-4"><LevelBadge level={i.severity || 'info'} /></td>
                        <td className="py-3 text-white/40 text-xs">{new Date(i.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                    {incidents.length === 0 && (
                      <tr><td colSpan={5} className="text-center py-12 text-white/30">No incidents found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── ALERTS ── */}
          {tab === 'alerts' && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold">System Alerts</h2>
              {alerts.length === 0 && (
                <div className="text-center py-12 text-white/30">
                  <CheckCircle size={32} className="text-emerald-400 mx-auto mb-3" />
                  All clear — no active alerts
                </div>
              )}
              <div className="space-y-3">
                {alerts.map((a) => (
                  <div key={a.id} className="bg-white/5 border border-white/10 rounded-xl p-5 flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <LevelBadge level={a.level} />
                      <div>
                        <p className="font-semibold text-sm">{a.title}</p>
                        {a.detail && <p className="text-xs text-white/40 mt-0.5">{a.detail}</p>}
                        <p className="text-[11px] text-white/25 mt-1">
                          {a.source} · {new Date(a.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => acknowledgeAlert(a.id)}
                      className="px-3 py-1.5 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg transition-all whitespace-nowrap"
                    >
                      Acknowledge
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── ARCHITECTURE ── */}
          {tab === 'architecture' && <ArchitectureTab />}
        </main>
      </div>

      {/* Tenant detail drawer */}
      {detailOpen && detailTenant && (
        <div className="fixed inset-0 bg-black/60 z-50 flex justify-end" onClick={() => setDetailOpen(false)}>
          <div
            className="w-full max-w-xl bg-[#0d1117] border-l border-white/10 h-full overflow-auto p-6"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold">{detailTenant.name}</h2>
              <button onClick={() => setDetailOpen(false)} className="text-white/40 hover:text-white">✕</button>
            </div>
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Email', detailTenant.email],
                  ['Country', detailTenant.country],
                  ['Plan', detailTenant.plan_id],
                  ['Status', detailTenant.status],
                  ['Onboarding', `Step ${detailTenant.onboarding_step}`],
                  ['Created', new Date(detailTenant.created_at).toLocaleDateString()],
                ].map(([k, v]) => (
                  <div key={k} className="bg-white/5 rounded-lg p-3">
                    <p className="text-[10px] text-white/30 uppercase tracking-wider">{k}</p>
                    <p className="font-semibold mt-0.5">{v}</p>
                  </div>
                ))}
              </div>
              <div>
                <h3 className="font-bold mb-2">Users ({detailTenant.users?.length})</h3>
                <div className="space-y-2">
                  {detailTenant.users?.map((u: any) => (
                    <div key={u.id} className="bg-white/3 rounded-lg p-3 flex justify-between items-center">
                      <div>
                        <p className="font-semibold text-sm">{u.email}</p>
                        <p className="text-xs text-white/40">{u.role}</p>
                      </div>
                      <StatusBadge status={u.is_active ? 'active' : 'suspended'} />
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="font-bold mb-2">Subscriptions ({detailTenant.subscriptions?.length})</h3>
                <div className="space-y-2">
                  {detailTenant.subscriptions?.map((s: any) => (
                    <div key={s.id} className="bg-white/3 rounded-lg p-3 flex justify-between items-center">
                      <div>
                        <p className="font-semibold text-sm">{s.plan_id}</p>
                        <p className="text-xs text-white/40">{s.currency} {s.amount}</p>
                      </div>
                      <StatusBadge status={s.status} />
                    </div>
                  ))}
                  {!detailTenant.subscriptions?.length && <p className="text-white/30 text-xs">No subscriptions</p>}
                </div>
              </div>
              <div>
                <h3 className="font-bold mb-2">Cameras ({detailTenant.cameras?.length})</h3>
                <div className="space-y-1">
                  {detailTenant.cameras?.map((c: any) => (
                    <div key={c.id} className="text-xs text-white/50 py-1 border-b border-white/5">
                      {c.name} — {c.is_active ? 'active' : 'inactive'}
                    </div>
                  ))}
                  {!detailTenant.cameras?.length && <p className="text-white/30 text-xs">No cameras</p>}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
