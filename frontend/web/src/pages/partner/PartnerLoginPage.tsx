import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Handshake, Eye, EyeOff, ArrowRight } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';

/**
 * Partner Portal login — deliberately separate from the tenant /login page.
 * Uses its own token (`vantag_partner_token`) so a partner session can
 * never be confused with, or escalate into, a tenant/camera session.
 */
export default function PartnerLoginPage() {
  const nav = useNavigate();
  const [form, setForm] = useState({ email: '', password: '' });
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await axios.post('/api/partner/login', form);
      localStorage.setItem('vantag_partner_token', data.access_token);
      localStorage.setItem('vantag_partner', JSON.stringify({
        id: data.partner_id,
        name: data.name,
        referral_code: data.referral_code,
        partner_type: data.partner_type,
      }));
      nav('/partner/dashboard');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(99,102,241,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(99,102,241,0.03)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="relative w-full max-w-md">
        <div className="flex justify-center mb-8">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
              <Handshake className="w-5 h-5" />
            </div>
            <span className="text-xl font-bold">Partner Portal</span>
          </Link>
        </div>
        <div className="bg-white/3 border border-white/8 rounded-2xl p-8">
          <h1 className="text-2xl font-bold mb-2 text-center">Partner sign in</h1>
          <p className="text-white/40 text-sm text-center mb-6">
            Confidential access — view your referrals &amp; commission earnings only.
          </p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Email address</label>
              <input type="email" required value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-emerald-500/50 transition-colors"
                placeholder="you@partner.com" />
            </div>
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} required value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 pr-12 text-white placeholder-white/20 focus:outline-none focus:border-emerald-500/50 transition-colors"
                  placeholder="••••••••" />
                <button type="button" onClick={() => setShowPw(s => !s)} className="absolute right-4 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <button type="submit" disabled={loading}
              className="w-full py-3.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all mt-2">
              {loading ? 'Signing in...' : <><span>Sign In</span><ArrowRight className="w-4 h-4" /></>}
            </button>
          </form>
          <p className="text-center text-white/40 text-sm mt-6">
            Partner accounts are created by invitation only. Contact your account manager if you need access.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
