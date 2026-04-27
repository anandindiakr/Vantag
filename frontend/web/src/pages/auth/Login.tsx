import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Shield, Eye, EyeOff, ArrowRight, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useRegion } from '../../hooks/useRegion';
import { LanguageSelector } from '../../components/LanguageSelector';

export default function Login() {
  const nav = useNavigate();
  const region = useRegion();
  const [form, setForm] = useState({ email: '', password: '' });
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('reason') === 'session_expired') setSessionExpired(true);
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await axios.post('/api/auth/login', form);
      localStorage.setItem('vantag_token', data.access_token);
      localStorage.setItem('vantag_tenant', JSON.stringify({ id: data.tenant_id, name: data.name, plan: data.plan_id, step: data.onboarding_step }));
      if (data.onboarding_step < 6) {
        nav('/onboarding');
      } else {
        nav('/dashboard');
      }
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
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
              <Shield className="w-5 h-5" />
            </div>
            <span className="text-xl font-bold">{region.brandShort}</span>
          </Link>
        </div>
        <div className="absolute top-0 right-0">
          <LanguageSelector variant="light" />
        </div>
        <div className="bg-white/3 border border-white/8 rounded-2xl p-8">
          <h1 className="text-2xl font-bold mb-2 text-center">Welcome back</h1>
          <p className="text-white/40 text-sm text-center mb-6">Sign in to your {region.brandShort} account</p>

          {/* Session expired banner */}
          {sessionExpired && (
            <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3 mb-5 text-amber-300 text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>Your session has expired. Please sign in again to continue.</span>
            </div>
          )}

          {/* Demo quick-login */}
          <button
            type="button"
            onClick={() => {
              setForm({ email: 'demo@vantag.io', password: 'demo1234' });
              setTimeout(() => {
                document.getElementById('vantag-login-submit')?.click();
              }, 80);
            }}
            className="w-full mb-6 py-2.5 rounded-xl border border-violet-500/40 bg-violet-500/8 text-violet-300 text-sm font-semibold hover:bg-violet-500/16 transition-all flex items-center justify-center gap-2"
          >
            <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
            Try Demo Account — no signup needed
          </button>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Email address</label>
              <input type="email" required value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                placeholder="you@shop.com" />
            </div>
            <div>
              <label className="text-sm text-white/60 block mb-1.5">Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} required value={form.password} onChange={e => setForm(f => ({...f, password: e.target.value}))}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 pr-12 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                  placeholder="••••••••" />
                <button type="button" onClick={() => setShowPw(s => !s)} className="absolute right-4 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <div className="flex justify-end mt-1.5">
                <Link to="/forgot-password" className="text-xs text-white/30 hover:text-violet-400 transition-colors">
                  Forgot password?
                </Link>
              </div>
            </div>
            <button type="submit" id="vantag-login-submit" disabled={loading}
              className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all mt-2">
              {loading ? 'Signing in...' : <><span>Sign In</span><ArrowRight className="w-4 h-4" /></>}
            </button>
          </form>
          <p className="text-center text-white/40 text-sm mt-6">
            No account? <Link to="/register" className="text-violet-400 hover:text-violet-300">Start free trial</Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
