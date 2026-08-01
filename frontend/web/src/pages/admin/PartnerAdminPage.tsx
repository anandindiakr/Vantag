/**
 * PartnerAdminPage.tsx — Super-admin management of dealers/distributors/
 * freelancers (Partners), their admin-editable commission rate table, and
 * the commission ledger (approve / mark paid).
 * Route: /admin/partners
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  Handshake, Plus, RefreshCw, Ban, Play, Percent, Wallet, ArrowLeft, X,
} from 'lucide-react';

function authHeaders() {
  const token = localStorage.getItem('vantag_token') || '';
  return { Authorization: `Bearer ${token}` };
}

interface Partner {
  id: string; name: string; email: string; phone: string | null;
  partner_type: string; referral_code: string; status: string;
  country: string | null; referred_customers: number; created_at: string;
  commission_rule_id: string | null; commission_rule_name: string | null;
}
interface CommissionRule {
  id: string; rule_type: string; product_plan: string; region: string;
  tier_name: string | null; tier_min_streams: number; tier_max_streams: number | null;
  rate_pct: number; is_active: boolean;
}
interface LedgerEntry {
  id: string; partner_id: string; tenant_id: string; invoice_id: string;
  gross_amount: number; currency: string; commission_amount: number;
  rate_pct: number; status: string; computed_at: string; paid_at: string | null;
}

type Tab = 'partners' | 'rules' | 'ledger';

export default function PartnerAdminPage() {
  const [tab, setTab] = useState<Tab>('partners');
  const [partners, setPartners] = useState<Partner[]>([]);
  const [rules, setRules] = useState<CommissionRule[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showAddRule, setShowAddRule] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, r, l] = await Promise.all([
        axios.get('/api/admin/partners', { headers: authHeaders() }),
        axios.get('/api/admin/commission-rules', { headers: authHeaders() }),
        axios.get('/api/admin/commission-ledger', { headers: authHeaders() }),
      ]);
      setPartners(p.data.partners);
      setRules(r.data.rules);
      setLedger(l.data.entries);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load partner data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const togglePartnerStatus = async (p: Partner) => {
    const next = p.status === 'active' ? 'suspended' : 'active';
    try {
      await axios.patch(`/api/admin/partners/${p.id}`, { status: next }, { headers: authHeaders() });
      toast.success(`Partner ${next}`);
      load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Update failed');
    }
  };

  const updateRuleRate = async (rule: CommissionRule, rate: number) => {
    try {
      await axios.patch(`/api/admin/commission-rules/${rule.id}`, { rate_pct: rate }, { headers: authHeaders() });
      toast.success('Rate updated');
      load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Update failed');
    }
  };

  const assignPartnerRule = async (p: Partner, ruleId: string) => {
    try {
      await axios.patch(`/api/admin/partners/${p.id}`,
        ruleId ? { commission_rule_id: ruleId } : { clear_commission_rule: true },
        { headers: authHeaders() });
      toast.success('Commission rule updated');
      load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Update failed');
    }
  };

  const markLedger = async (entry: LedgerEntry, status: string) => {
    try {
      await axios.patch(`/api/admin/commission-ledger/${entry.id}`, { status }, { headers: authHeaders() });
      toast.success(`Marked ${status}`);
      load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Update failed');
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <header className="border-b border-white/8 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/admin" className="text-white/40 hover:text-white/80"><ArrowLeft className="w-5 h-5" /></Link>
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
            <Handshake className="w-4 h-4" />
          </div>
          <span className="font-semibold text-lg">Partners &amp; Commissions</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="p-2 rounded-lg hover:bg-white/5 text-white/50"><RefreshCw className="w-4 h-4" /></button>
          <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 px-3 py-2 rounded-lg text-sm font-medium">
            <Plus className="w-4 h-4" /> New Partner
          </button>
        </div>
      </header>

      <nav className="max-w-6xl mx-auto px-6 pt-6 flex gap-2">
        {(['partners', 'rules', 'ledger'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium capitalize ${tab === t ? 'bg-emerald-600' : 'bg-white/5 text-white/50 hover:bg-white/10'}`}>
            {t === 'rules' ? 'Commission Rules' : t}
          </button>
        ))}
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-6">
        {loading ? (
          <div className="py-20 flex justify-center"><div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : tab === 'partners' ? (
          <PartnersTable partners={partners} rules={rules} onToggle={togglePartnerStatus} onAssignRule={assignPartnerRule} />
        ) : tab === 'rules' ? (
          <RulesTable rules={rules} onUpdate={updateRuleRate} onAddRule={() => setShowAddRule(true)} />
        ) : (
          <LedgerTable ledger={ledger} onMark={markLedger} />
        )}
      </main>

      {showCreate && <CreatePartnerModal rules={rules} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {showAddRule && <AddRuleModal onClose={() => setShowAddRule(false)} onCreated={() => { setShowAddRule(false); load(); }} />}
    </div>
  );
}

function PartnersTable({ partners, rules, onToggle, onAssignRule }: {
  partners: Partner[]; rules: CommissionRule[]; onToggle: (p: Partner) => void;
  onAssignRule: (p: Partner, ruleId: string) => void;
}) {
  return (
    <div className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
      <table className="w-full text-sm">
        <thead className="text-white/40 text-xs uppercase">
          <tr>
            <th className="text-left px-6 py-3">Name</th>
            <th className="text-left px-6 py-3">Email</th>
            <th className="text-left px-6 py-3">Type</th>
            <th className="text-left px-6 py-3">Referral Code</th>
            <th className="text-left px-6 py-3">Commission Rule</th>
            <th className="text-left px-6 py-3">Referred</th>
            <th className="text-left px-6 py-3">Status</th>
            <th className="text-left px-6 py-3">Action</th>
          </tr>
        </thead>
        <tbody>
          {partners.length === 0 && (
            <tr><td colSpan={8} className="px-6 py-10 text-center text-white/30">No partners yet — click "New Partner" to invite one.</td></tr>
          )}
          {partners.map(p => (
            <tr key={p.id} className="border-t border-white/5">
              <td className="px-6 py-3">{p.name}</td>
              <td className="px-6 py-3 text-white/60">{p.email}</td>
              <td className="px-6 py-3 text-white/60 capitalize">{p.partner_type}</td>
              <td className="px-6 py-3 font-mono text-emerald-400">{p.referral_code}</td>
              <td className="px-6 py-3">
                <select
                  value={p.commission_rule_id || ''}
                  onChange={e => onAssignRule(p, e.target.value)}
                  className="bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-xs max-w-[180px]"
                >
                  <option value="">No rule assigned</option>
                  {rules.map(r => (
                    <option key={r.id} value={r.id}>
                      {(r.tier_name || r.rule_type.replace('_', ' '))} ({r.rate_pct}%)
                    </option>
                  ))}
                </select>
              </td>
              <td className="px-6 py-3">{p.referred_customers}</td>
              <td className="px-6 py-3">
                <span className={`px-2.5 py-1 rounded-full text-xs font-medium capitalize ${p.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'}`}>
                  {p.status}
                </span>
              </td>
              <td className="px-6 py-3">
                <button onClick={() => onToggle(p)} className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/60">
                  {p.status === 'active' ? <><Ban className="w-3 h-3" /> Suspend</> : <><Play className="w-3 h-3" /> Reactivate</>}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RulesTable({ rules, onUpdate, onAddRule }: {
  rules: CommissionRule[]; onUpdate: (r: CommissionRule, rate: number) => void; onAddRule: () => void;
}) {
  const [edits, setEdits] = useState<Record<string, number>>({});
  return (
    <div className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-white/8 text-sm text-white/50 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2"><Percent className="w-4 h-4" /> Rates are fully editable — changes apply to the next commission calculation onward.</span>
        <button onClick={onAddRule} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 flex-shrink-0">
          <Plus className="w-3.5 h-3.5" /> Add Rule
        </button>
      </div>
      <table className="w-full text-sm">
        <thead className="text-white/40 text-xs uppercase">
          <tr>
            <th className="text-left px-6 py-3">Rule Type</th>
            <th className="text-left px-6 py-3">Tier</th>
            <th className="text-left px-6 py-3">Stream Range</th>
            <th className="text-left px-6 py-3">Rate %</th>
            <th className="text-left px-6 py-3">Active</th>
            <th className="text-left px-6 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {rules.map(r => (
            <tr key={r.id} className="border-t border-white/5">
              <td className="px-6 py-3 capitalize">{r.rule_type.replace('_', ' ')}</td>
              <td className="px-6 py-3 text-white/60">{r.tier_name || '—'}</td>
              <td className="px-6 py-3 text-white/40">{r.tier_min_streams} – {r.tier_max_streams ?? '∞'}</td>
              <td className="px-6 py-3">
                <input type="number" step="0.1" defaultValue={r.rate_pct}
                  onChange={e => setEdits(ed => ({ ...ed, [r.id]: parseFloat(e.target.value) }))}
                  className="w-20 bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-white" />
              </td>
              <td className="px-6 py-3">{r.is_active ? 'Yes' : 'No'}</td>
              <td className="px-6 py-3">
                <button
                  onClick={() => onUpdate(r, edits[r.id] ?? r.rate_pct)}
                  className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500">
                  Save
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LedgerTable({ ledger, onMark }: { ledger: LedgerEntry[]; onMark: (e: LedgerEntry, s: string) => void }) {
  return (
    <div className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-white/8 text-sm text-white/50 flex items-center gap-2">
        <Wallet className="w-4 h-4" /> Payouts are tracked here, but money movement happens outside the app (bank/UPI). Mark entries as approved/paid once settled.
      </div>
      <table className="w-full text-sm">
        <thead className="text-white/40 text-xs uppercase">
          <tr>
            <th className="text-left px-6 py-3">Partner</th>
            <th className="text-left px-6 py-3">Invoice</th>
            <th className="text-left px-6 py-3">Gross</th>
            <th className="text-left px-6 py-3">Commission</th>
            <th className="text-left px-6 py-3">Status</th>
            <th className="text-left px-6 py-3">Action</th>
          </tr>
        </thead>
        <tbody>
          {ledger.length === 0 && (
            <tr><td colSpan={6} className="px-6 py-10 text-center text-white/30">No commission entries yet.</td></tr>
          )}
          {ledger.map(e => (
            <tr key={e.id} className="border-t border-white/5">
              <td className="px-6 py-3 font-mono text-xs text-white/50">{e.partner_id.slice(0, 8)}</td>
              <td className="px-6 py-3 font-mono text-xs text-white/50">{e.invoice_id.slice(0, 8)}</td>
              <td className="px-6 py-3">{e.currency} {e.gross_amount.toFixed(2)}</td>
              <td className="px-6 py-3 font-semibold text-emerald-400">{e.currency} {e.commission_amount.toFixed(2)}</td>
              <td className="px-6 py-3 capitalize">{e.status}</td>
              <td className="px-6 py-3 flex gap-1.5">
                {e.status !== 'approved' && <button onClick={() => onMark(e, 'approved')} className="text-xs px-2 py-1 rounded-lg bg-white/10 hover:bg-white/20">Approve</button>}
                {e.status !== 'paid' && <button onClick={() => onMark(e, 'paid')} className="text-xs px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500">Mark Paid</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreatePartnerModal({ rules, onClose, onCreated }: {
  rules: CommissionRule[]; onClose: () => void; onCreated: () => void;
}) {
  const [form, setForm] = useState({ name: '', email: '', phone: '', partner_type: 'installer', country: '', commission_rule_id: '' });
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { commission_rule_id, ...rest } = form;
      const payload = commission_rule_id ? { ...rest, commission_rule_id } : rest;
      const { data } = await axios.post('/api/admin/partners', payload, { headers: authHeaders() });
      toast.success(`Partner created — referral code ${data.referral_code}`);
      onCreated();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create partner');
    } finally {
      setSaving(false);
    }
  };

  const rulesForType = rules.filter(r => {
    if (form.partner_type === 'installer') return r.rule_type === 'fixed_pct';
    if (form.partner_type === 'distributor') return r.rule_type === 'tiered_volume';
    return r.rule_type === 'flat_referral';
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4">
      <div className="bg-[#12121a] border border-white/10 rounded-2xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-lg">Invite New Partner</h2>
          <button onClick={onClose} className="text-white/40 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <input required placeholder="Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
          <input required type="email" placeholder="Email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
          <input placeholder="Phone (optional)" value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
          <select value={form.partner_type} onChange={e => setForm(f => ({ ...f, partner_type: e.target.value, commission_rule_id: '' }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2">
            <option value="installer">Installer / Dealer (fixed % cut)</option>
            <option value="distributor">Distributor (volume-tiered)</option>
            <option value="referrer">Freelancer / Referrer (flat %)</option>
          </select>
          <input placeholder="Country code (IN/SG/MY/PH/ID)" value={form.country} onChange={e => setForm(f => ({ ...f, country: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
          <div>
            <label className="text-xs text-white/40 mb-1 block">Commission rule (optional — pin a specific tier now, or leave blank to auto-resolve by type)</label>
            <select value={form.commission_rule_id} onChange={e => setForm(f => ({ ...f, commission_rule_id: e.target.value }))}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2">
              <option value="">Auto-resolve by partner type</option>
              {rulesForType.map(r => (
                <option key={r.id} value={r.id}>{(r.tier_name || r.rule_type.replace('_', ' '))} ({r.rate_pct}%)</option>
              ))}
            </select>
          </div>
          <button type="submit" disabled={saving} className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg font-medium mt-2">
            {saving ? 'Creating...' : 'Create Partner'}
          </button>
        </form>
      </div>
    </div>
  );
}

function AddRuleModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({
    rule_type: 'fixed_pct', product_plan: '*', region: '*', tier_name: '',
    tier_min_streams: 0, tier_max_streams: '', rate_pct: '',
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        rule_type: form.rule_type,
        product_plan: form.product_plan || '*',
        region: form.region || '*',
        tier_name: form.tier_name || null,
        tier_min_streams: Number(form.tier_min_streams) || 0,
        tier_max_streams: form.tier_max_streams === '' ? null : Number(form.tier_max_streams),
        rate_pct: Number(form.rate_pct),
        is_active: true,
      };
      await axios.post('/api/admin/commission-rules', payload, { headers: authHeaders() });
      toast.success('Commission rule created');
      onCreated();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create rule');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4">
      <div className="bg-[#12121a] border border-white/10 rounded-2xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-lg">Add Commission Rule</h2>
          <button onClick={onClose} className="text-white/40 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <select value={form.rule_type} onChange={e => setForm(f => ({ ...f, rule_type: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2">
            <option value="fixed_pct">Fixed % dealer cut</option>
            <option value="tiered_volume">Volume-tiered distributor margin</option>
            <option value="flat_referral">Flat % lifetime referral</option>
          </select>
          <input placeholder="Tier / rule name (e.g. Tier 1, Field Installer)" value={form.tier_name}
            onChange={e => setForm(f => ({ ...f, tier_name: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
          <div className="flex gap-2">
            <input required type="number" step="0.1" placeholder="Rate %" value={form.rate_pct}
              onChange={e => setForm(f => ({ ...f, rate_pct: e.target.value }))}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
          </div>
          {form.rule_type === 'tiered_volume' && (
            <div className="flex gap-2">
              <input type="number" placeholder="Min streams" value={form.tier_min_streams}
                onChange={e => setForm(f => ({ ...f, tier_min_streams: Number(e.target.value) }))}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
              <input type="number" placeholder="Max streams (blank = ∞)" value={form.tier_max_streams}
                onChange={e => setForm(f => ({ ...f, tier_max_streams: e.target.value }))}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
            </div>
          )}
          <input placeholder="Region (default * = all)" value={form.region}
            onChange={e => setForm(f => ({ ...f, region: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2" />
          <button type="submit" disabled={saving} className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg font-medium mt-2">
            {saving ? 'Creating...' : 'Create Rule'}
          </button>
        </form>
      </div>
    </div>
  );
}
