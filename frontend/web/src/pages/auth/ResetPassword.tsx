import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Shield, Eye, EyeOff, ArrowRight, CheckCircle, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { useRegion } from '../../hooks/useRegion';

export default function ResetPassword() {
  const region   = useRegion();
  const nav      = useNavigate();

  // Extract token from ?token= query parameter
  const token = new URLSearchParams(window.location.search).get('token') || '';

  const [password, setPassword]   = useState('');
  const [confirm, setConfirm]     = useState('');
  const [showPw, setShowPw]       = useState(false);
  const [loading, setLoading]     = useState(false);
  const [done, setDone]           = useState(false);
  const [error, setError]         = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await axios.post('/api/auth/reset-password', { token, new_password: password });
      setDone(true);
      setTimeout(() => nav('/login'), 3000);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Reset failed. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-4 text-white">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-amber-400 mx-auto mb-4" />
          <p className="text-white/60 mb-4">Invalid or missing reset token.</p>
          <Link to="/forgot-password" className="text-violet-400 hover:text-violet-300">
            Request a new reset link
          </Link>
        </div>
      </div>
    );
  }

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

        <div className="bg-white/3 border border-white/8 rounded-2xl p-8">
          {done ? (
            <div className="text-center">
              <CheckCircle className="w-14 h-14 text-green-400 mx-auto mb-4" />
              <h1 className="text-2xl font-bold mb-2">Password reset!</h1>
              <p className="text-white/50 text-sm">Redirecting you to sign in…</p>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-bold mb-2 text-center">Set new password</h1>
              <p className="text-white/40 text-sm text-center mb-6">
                Choose a strong password for your account.
              </p>

              {error && (
                <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 mb-4 text-red-300 text-sm">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <form onSubmit={submit} className="space-y-4">
                <div>
                  <label className="text-sm text-white/60 block mb-1.5">New password</label>
                  <div className="relative">
                    <input
                      type={showPw ? 'text' : 'password'}
                      required
                      minLength={8}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 pr-12 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                      placeholder="At least 8 characters"
                    />
                    <button type="button" onClick={() => setShowPw(s => !s)} className="absolute right-4 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60">
                      {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="text-sm text-white/60 block mb-1.5">Confirm password</label>
                  <input
                    type={showPw ? 'text' : 'password'}
                    required
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                    placeholder="Repeat password"
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all mt-2"
                >
                  {loading ? 'Resetting…' : <><span>Reset Password</span><ArrowRight className="w-4 h-4" /></>}
                </button>
              </form>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
