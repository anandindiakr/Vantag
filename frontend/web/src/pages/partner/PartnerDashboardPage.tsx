import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  Handshake, Copy, LogOut, Users, Wallet, Clock, CheckCircle2, QrCode,
  ChevronDown, ChevronRight, Percent,
} from 'lucide-react';

interface MeResp {
  id: string; name: string; email: string; phone: string | null;
  partner_type: string; referral_code: string; referral_link: string;
  status: string; created_at: string;
  commission_rule: { id: string; rule_type: string; tier_name: string | null; rate_pct: number } | null;
}
interface PaymentHistoryEntry {
  invoice_id: string; amount: number; currency: string; status: string;
  invoice_number: string | null; created_at: string;
  commission_amount: number | null; commission_status: string | null;
}
interface Referral {
  tenant_id: string; name: string; country: string; plan_id: string;
  status: string; referred_at: string;
  subscription: {
    plan_id: string; status: string; amount: number | null; currency: string;
    current_period_end: string | null; cancel_at_period_end: boolean;
  } | null;
  payment_history: PaymentHistoryEntry[];
}
interface Earning {
  id: string; tenant_id: string; invoice_id: string; gross_amount: number;
  currency: string; commission_amount: number; rate_pct: number;
  status: string; computed_at: string; paid_at: string | null;
}

function partnerApi() {
  const token = localStorage.getItem('vantag_partner_token');
  return axios.create({
    baseURL: '/api/partner',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export default function PartnerDashboardPage() {
  const nav = useNavigate();
  const [me, setMe] = useState<MeResp | null>(null);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [earnings, setEarnings] = useState<Earning[]>([]);
  const [totals, setTotals] = useState<Record<string, number>>({});
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const api = partnerApi();
    try {
      const [meRes, refRes, earnRes] = await Promise.all([
        api.get('/me'),
        api.get('/me/referrals'),
        api.get('/me/earnings', { params: statusFilter ? { status_filter: statusFilter } : {} }),
      ]);
      setMe(meRes.data);
      setReferrals(refRes.data.referrals);
      setEarnings(earnRes.data.entries);
      setTotals(earnRes.data.totals_by_currency || {});
    } catch (err: any) {
      if (err?.response?.status === 401) {
        localStorage.removeItem('vantag_partner_token');
        localStorage.removeItem('vantag_partner');
        nav('/partner/login');
      } else {
        toast.error(err?.response?.data?.detail || 'Failed to load partner data');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!localStorage.getItem('vantag_partner_token')) {
      nav('/partner/login');
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const logout = () => {
    localStorage.removeItem('vantag_partner_token');
    localStorage.removeItem('vantag_partner');
    nav('/partner/login');
  };

  const copyLink = () => {
    if (!me) return;
    navigator.clipboard.writeText(me.referral_link);
    toast.success('Referral link copied');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const activeCount = referrals.filter(r => r.status === 'active' || r.status === 'trial').length;
  const pendingTotal = earnings.filter(e => e.status === 'pending').reduce((s, e) => s + e.commission_amount, 0);
  const paidTotal = earnings.filter(e => e.status === 'paid').reduce((s, e) => s + e.commission_amount, 0);
  const qrUrl = me ? `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(me.referral_link)}` : '';

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <header className="border-b border-white/8 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
            <Handshake className="w-4 h-4" />
          </div>
          <div>
            <div className="font-semibold">{me?.name}</div>
            <div className="text-xs text-white/40 capitalize">{me?.partner_type} partner</div>
          </div>
        </div>
        <button onClick={logout} className="flex items-center gap-2 text-sm text-white/50 hover:text-white/90 px-3 py-2 rounded-lg hover:bg-white/5">
          <LogOut className="w-4 h-4" /> Sign out
        </button>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {/* Referral link / QR */}
        <section className="bg-white/3 border border-white/8 rounded-2xl p-6 flex flex-col md:flex-row items-center gap-6">
          <img src={qrUrl} alt="Referral QR code" className="w-32 h-32 rounded-xl bg-white p-2" />
          <div className="flex-1 min-w-0">
            <div className="text-xs uppercase tracking-wide text-white/40 mb-1">Your permanent referral code</div>
            <div className="text-2xl font-bold text-emerald-400 mb-3">{me?.referral_code}</div>
            <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5">
              <span className="text-sm text-white/70 truncate flex-1">{me?.referral_link}</span>
              <button onClick={copyLink} className="text-white/50 hover:text-white flex-shrink-0">
                <Copy className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-white/30 mt-2 flex items-center gap-1">
              <QrCode className="w-3 h-3" /> Share this link or QR — every customer who signs up through it is permanently linked to you.
            </p>
          </div>
          {me?.commission_rule && (
            <div className="flex-shrink-0 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-5 py-4 text-center">
              <div className="flex items-center justify-center gap-1 text-xs uppercase tracking-wide text-emerald-400/80 mb-1">
                <Percent className="w-3 h-3" /> Your commission
              </div>
              <div className="text-3xl font-bold text-emerald-400">{me.commission_rule.rate_pct}%</div>
              <div className="text-xs text-white/40 mt-1">{me.commission_rule.tier_name || me.commission_rule.rule_type.replace('_', ' ')}</div>
            </div>
          )}
        </section>

        {/* Summary cards */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={<Users className="w-4 h-4" />} label="Total referred" value={String(referrals.length)} />
          <StatCard icon={<CheckCircle2 className="w-4 h-4" />} label="Active / trial" value={String(activeCount)} />
          <StatCard icon={<Clock className="w-4 h-4" />} label="Pending commission" value={fmtMoney(pendingTotal, totals)} />
          <StatCard icon={<Wallet className="w-4 h-4" />} label="Paid to date" value={fmtMoney(paidTotal, totals)} />
        </section>

        {/* My referrals */}
        <section className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-white/8 font-semibold">My Referrals</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-white/40 text-xs uppercase">
                <tr>
                  <th className="text-left px-6 py-3"></th>
                  <th className="text-left px-6 py-3">Customer</th>
                  <th className="text-left px-6 py-3">Country</th>
                  <th className="text-left px-6 py-3">Subscription</th>
                  <th className="text-left px-6 py-3">Price</th>
                  <th className="text-left px-6 py-3">Status</th>
                  <th className="text-left px-6 py-3">Referred</th>
                </tr>
              </thead>
              <tbody>
                {referrals.length === 0 && (
                  <tr><td colSpan={7} className="px-6 py-8 text-center text-white/30">No referrals yet — share your link above to get started.</td></tr>
                )}
                {referrals.map(r => (
                  <ReferralRow key={r.tenant_id} r={r} />
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* My earnings */}
        <section className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-white/8 flex items-center justify-between">
            <span className="font-semibold">My Earnings</span>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm">
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="paid">Paid</option>
            </select>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-white/40 text-xs uppercase">
                <tr>
                  <th className="text-left px-6 py-3">Invoice</th>
                  <th className="text-left px-6 py-3">Gross</th>
                  <th className="text-left px-6 py-3">Rate</th>
                  <th className="text-left px-6 py-3">Commission</th>
                  <th className="text-left px-6 py-3">Status</th>
                  <th className="text-left px-6 py-3">Computed</th>
                </tr>
              </thead>
              <tbody>
                {earnings.length === 0 && (
                  <tr><td colSpan={6} className="px-6 py-8 text-center text-white/30">No commission entries yet.</td></tr>
                )}
                {earnings.map(e => (
                  <tr key={e.id} className="border-t border-white/5">
                    <td className="px-6 py-3 text-white/60 truncate max-w-[140px]">{e.invoice_id}</td>
                    <td className="px-6 py-3">{e.currency} {e.gross_amount.toFixed(2)}</td>
                    <td className="px-6 py-3 text-white/60">{e.rate_pct}%</td>
                    <td className="px-6 py-3 font-semibold text-emerald-400">{e.currency} {e.commission_amount.toFixed(2)}</td>
                    <td className="px-6 py-3"><StatusPill status={e.status} /></td>
                    <td className="px-6 py-3 text-white/40">{new Date(e.computed_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

function fmtMoney(amount: number, totals: Record<string, number>) {
  const currencies = Object.keys(totals);
  const currency = currencies[0] || 'USD';
  return `${currency} ${amount.toFixed(2)}`;
}

function ReferralRow({ r }: { r: Referral }) {
  const [open, setOpen] = useState(false);
  const sub = r.subscription;
  return (
    <>
      <tr className="border-t border-white/5 cursor-pointer hover:bg-white/3" onClick={() => setOpen(o => !o)}>
        <td className="px-3 py-3 text-white/40">
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </td>
        <td className="px-6 py-3">{r.name}</td>
        <td className="px-6 py-3 text-white/60">{r.country}</td>
        <td className="px-6 py-3 text-white/60 capitalize">{sub?.plan_id || r.plan_id}</td>
        <td className="px-6 py-3 text-white/60">
          {sub?.amount != null ? `${sub.currency} ${sub.amount.toFixed(2)}` : '—'}
        </td>
        <td className="px-6 py-3"><StatusPill status={sub?.status || r.status} /></td>
        <td className="px-6 py-3 text-white/40">{new Date(r.referred_at).toLocaleDateString()}</td>
      </tr>
      {open && (
        <tr className="border-t border-white/5 bg-white/2">
          <td colSpan={7} className="px-6 py-4">
            <div className="text-xs uppercase tracking-wide text-white/40 mb-2">Payment history</div>
            {r.payment_history.length === 0 ? (
              <div className="text-sm text-white/30">No invoices yet for this customer.</div>
            ) : (
              <table className="w-full text-xs">
                <thead className="text-white/40 uppercase">
                  <tr>
                    <th className="text-left py-1.5 pr-4">Invoice #</th>
                    <th className="text-left py-1.5 pr-4">Amount</th>
                    <th className="text-left py-1.5 pr-4">Status</th>
                    <th className="text-left py-1.5 pr-4">Date</th>
                    <th className="text-left py-1.5 pr-4">Your commission</th>
                  </tr>
                </thead>
                <tbody>
                  {r.payment_history.map(p => (
                    <tr key={p.invoice_id} className="border-t border-white/5">
                      <td className="py-1.5 pr-4 text-white/60">{p.invoice_number || p.invoice_id.slice(0, 8)}</td>
                      <td className="py-1.5 pr-4">{p.currency} {p.amount.toFixed(2)}</td>
                      <td className="py-1.5 pr-4"><StatusPill status={p.status} /></td>
                      <td className="py-1.5 pr-4 text-white/40">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="py-1.5 pr-4 font-medium text-emerald-400">
                        {p.commission_amount != null ? `${p.currency} ${p.commission_amount.toFixed(2)} (${p.commission_status})` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="bg-white/3 border border-white/8 rounded-2xl p-5">
      <div className="flex items-center gap-2 text-white/40 text-xs uppercase tracking-wide mb-2">{icon}{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: 'bg-emerald-500/15 text-emerald-400', trial: 'bg-sky-500/15 text-sky-400',
    pending: 'bg-amber-500/15 text-amber-400', approved: 'bg-violet-500/15 text-violet-400',
    paid: 'bg-emerald-500/15 text-emerald-400', suspended: 'bg-rose-500/15 text-rose-400',
    cancelled: 'bg-white/10 text-white/50',
  };
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium capitalize ${styles[status] || 'bg-white/10 text-white/50'}`}>
      {status}
    </span>
  );
}
