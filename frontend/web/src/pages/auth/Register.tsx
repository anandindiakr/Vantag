import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Shield, Eye, EyeOff, ArrowRight } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';

const COUNTRIES = [
  { code: 'IN', name: '🇮🇳 India', lang: 'hi' },
  { code: 'SG', name: '🇸🇬 Singapore', lang: 'en' },
  { code: 'MY', name: '🇲🇾 Malaysia', lang: 'ms' },
];

export default function Register() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    phone: '',
    country: params.get('country') || 'IN',
    plan_id: params.get('plan') || 'starter',
  });

  const up = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password.length < 8) { toast.error('Password must be at least 8 characters'); return; }
    setLoading(true);
    try {
      const country = COUNTRIES.find(c => c.code === form.country);
      const { data } = await axios.post('/api/auth/register', { ...form, language: country?.lang || 'en' });
      localStorage.setItem('vantag_token', data.access_token);
      localStorage.setItem('vantag_tenant', JSON.stringify({ id: data.tenant_id, plan: data.plan_id, step: 1 }));
      toast.success('Account created! Please verify your email.');
      nav('/verify-email', { state: { email: form.email } });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-4 py-12">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(99,102,241,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(99,102,241,0.03)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="relative w-full max-w-md">
        <div className="flex justify-center mb-8">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
              <Shield className="w-5 h-5" />
            </div>
            <span className="text-xl font-bold">Vantag</span>
          </Link>
        </div>
        <div className="bg-white/3 border border-white/8 rounded-2xl p-8">
          <h1 className="text-2xl font-bold mb-2 text-center">Create your account</h1>
          <p className="text-white/40 text-sm text-center mb-8">14-day free trial · No credit card required</p>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Shop Name</label>
              <input required value={form.name} onChange={e => up('name', e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                placeholder="My Retail Shop" />
            </div>
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Email</label>
              <input type="email" required value={form.email} onChange={e => up('email', e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                placeholder="owner@shop.com" />
            </div>
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Phone Number</label>
              <input type="tel" value={form.phone} onChange={e => up('phone', e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                placeholder="+91 98765 43210" />
            </div>
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Country</label>
              <select value={form.country} onChange={e => up('country', e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-violet-500/50 transition-colors">
                {COUNTRIES.map(c => <option key={c.code} value={c.code} className="bg-gray-900">{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} required value={form.password} onChange={e => up('password', e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 pr-12 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                  placeholder="Min 8 characters" />
                <button type="button" onClick={() => setShowPw(s => !s)} className="absolute right-4 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <button type="submit" disabled={loading}
              className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all mt-2">
              {loading ? 'Creating account...' : <><span>Create Account</span><ArrowRight className="w-4 h-4" /></>}
            </button>
          </form>
          <p className="text-center text-white/40 text-sm mt-6">
            Already have an account? <Link to="/login" className="text-violet-400 hover:text-violet-300">Sign in</Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
