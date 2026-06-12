import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Shield, ArrowRight, CheckCircle } from 'lucide-react';
import axios from 'axios';
import { useRegion } from '../../hooks/useRegion';

export default function ForgotPassword() {
  const region = useRegion();
  const [email, setEmail]     = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent]       = useState(false);
  const [error, setError]     = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await axios.post('/api/auth/forgot-password', { email });
      setSent(true);
    } catch {
      setError('Something went wrong. Please try again.');
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

        <div className="bg-white/3 border border-white/8 rounded-2xl p-8">
          {sent ? (
            <div className="text-center">
              <CheckCircle className="w-14 h-14 text-green-400 mx-auto mb-4" />
              <h1 className="text-2xl font-bold mb-2">Check your email</h1>
              <p className="text-white/50 text-sm mb-6">
                If <strong className="text-white">{email}</strong> is registered, we've sent a
                password-reset link. It expires in 30 minutes.
              </p>
              <Link to="/login" className="text-violet-400 hover:text-violet-300 text-sm">
                Back to Sign In
              </Link>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-bold mb-2 text-center">Forgot password?</h1>
              <p className="text-white/40 text-sm text-center mb-6">
                Enter your email and we'll send you a reset link.
              </p>

              {error && (
                <p className="text-red-400 text-sm text-center mb-4">{error}</p>
              )}

              <form onSubmit={submit} className="space-y-4">
                <div>
                  <label className="text-sm text-white/60 block mb-1.5">Email address</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 transition-colors"
                    placeholder="you@shop.com"
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all"
                >
                  {loading ? 'Sending…' : <><span>Send Reset Link</span><ArrowRight className="w-4 h-4" /></>}
                </button>
              </form>

              <p className="text-center text-white/40 text-sm mt-6">
                Remember it? <Link to="/login" className="text-violet-400 hover:text-violet-300">Sign in</Link>
              </p>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
