// frontend/web/src/pages/auth/VerifyEmail.tsx
// OTP email verification page shown right after registration.

import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Shield, MailCheck, RefreshCw, ArrowRight, Loader2, Terminal } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';

const api = axios.create({ baseURL: '/api' });

export default function VerifyEmail() {
  const nav = useNavigate();
  const location = useLocation();
  const email: string = (location.state as any)?.email || '';

  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [countdown, setCountdown] = useState(60);
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Auto-send OTP on mount if email is known
  useEffect(() => {
    if (email) sendOtp(true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Countdown timer for resend
  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const fillOtpBoxes = (code: string) => {
    const digits = code.split('');
    setOtp(digits);
    // focus last box
    inputRefs.current[5]?.focus();
  };

  const sendOtp = async (silent = false) => {
    if (!email) { toast.error('No email address found. Please register again.'); return; }
    setResending(true);
    try {
      const { data } = await api.post('/auth/send-otp', { email });
      if (data.dev_mode && data.otp) {
        // SMTP not configured — auto-fill the code and show a dev banner
        setDevOtp(data.otp);
        fillOtpBoxes(data.otp);
        if (!silent) toast.success('Dev mode: code auto-filled below.');
      } else if (!silent) {
        toast.success('New code sent! Check your inbox.');
        setCountdown(60);
        setDevOtp(null);
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Could not send code');
    } finally {
      setResending(false);
    }
  };

  const handleDigit = (idx: number, val: string) => {
    const digit = val.replace(/\D/g, '').slice(-1);
    const next = [...otp];
    next[idx] = digit;
    setOtp(next);
    if (digit && idx < 5) inputRefs.current[idx + 1]?.focus();
    if (next.every(d => d)) handleVerify(next.join(''));
  };

  const handleKeyDown = (idx: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !otp[idx] && idx > 0) {
      inputRefs.current[idx - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (pasted.length === 6) {
      setOtp(pasted.split(''));
      handleVerify(pasted);
    }
  };

  const handleVerify = async (code?: string) => {
    const finalCode = code || otp.join('');
    if (finalCode.length < 6) { toast.error('Enter the 6-digit code'); return; }
    setLoading(true);
    try {
      await api.post('/auth/verify-email', { email, otp: finalCode });
      toast.success('Email verified! Setting up your account...');
      // Navigate to onboarding — token should already be in localStorage from register
      nav('/onboarding', { replace: true });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Verification failed');
      setOtp(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(99,102,241,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(99,102,241,0.03)_1px,transparent_1px)] bg-[size:60px_60px]" />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative w-full max-w-md"
      >
        <div className="bg-white/3 border border-white/8 rounded-2xl p-8 text-center">
          {/* Logo */}
          <div className="flex items-center justify-center gap-2 mb-8">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
              <Shield className="w-4 h-4" />
            </div>
            <span className="text-lg font-bold">Vantag</span>
          </div>

          <div className="w-16 h-16 rounded-2xl bg-violet-600/20 flex items-center justify-center mx-auto mb-6">
            <MailCheck className="w-8 h-8 text-violet-400" />
          </div>

          <h1 className="text-2xl font-bold mb-2">Check your email</h1>
          <p className="text-white/40 text-sm mb-2">
            We sent a 6-digit code to
          </p>
          <p className="text-violet-300 text-sm font-medium mb-8 break-all">
            {email || 'your email address'}
          </p>

          {/* Dev-mode banner: shown when SMTP not configured */}
          {devOtp && (
            <div className="mb-6 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-start gap-2 text-left">
              <Terminal className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-xs text-amber-400 font-semibold">Dev mode — SMTP not configured</p>
                <p className="text-xs text-amber-300/70 mt-0.5">
                  Code auto-filled: <span className="font-mono font-bold">{devOtp}</span>
                  <br />Set <code className="bg-white/10 px-1 rounded">VANTAG_SMTP_USER</code> in your <code className="bg-white/10 px-1 rounded">.env</code> to send real emails.
                </p>
              </div>
            </div>
          )}

          {/* OTP input boxes */}
          <div className="flex gap-2 justify-center mb-8" onPaste={handlePaste}>
            {otp.map((digit, idx) => (
              <input
                key={idx}
                ref={el => { inputRefs.current[idx] = el; }}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={digit}
                onChange={e => handleDigit(idx, e.target.value)}
                onKeyDown={e => handleKeyDown(idx, e)}
                className={`w-11 h-14 text-center text-xl font-bold bg-white/5 border-2 rounded-xl transition-all focus:outline-none
                  ${digit ? 'border-violet-500 text-white' : 'border-white/10 text-white/30'}
                  focus:border-violet-400`}
              />
            ))}
          </div>

          {/* Verify button */}
          <button
            onClick={() => handleVerify()}
            disabled={loading || otp.join('').length < 6}
            className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all mb-4"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
            {loading ? 'Verifying...' : 'Verify Email'}
          </button>

          {/* Resend */}
          <button
            onClick={() => sendOtp()}
            disabled={resending || countdown > 0}
            className="flex items-center justify-center gap-2 text-sm text-white/40 hover:text-white/70 disabled:opacity-40 mx-auto transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${resending ? 'animate-spin' : ''}`} />
            {countdown > 0 ? `Resend in ${countdown}s` : resending ? 'Sending...' : 'Resend code'}
          </button>

          <p className="text-xs text-white/20 mt-6">
            Wrong email? <button onClick={() => nav('/register')} className="text-violet-400 hover:underline">Go back and register again</button>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
