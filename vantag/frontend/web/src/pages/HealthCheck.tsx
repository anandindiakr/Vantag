// frontend/web/src/pages/HealthCheck.tsx
// System Health Check dashboard — runs real probes via backend and displays results.

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle2, XCircle, RefreshCw, Activity, AlertTriangle,
  Clock,
} from 'lucide-react';
import clsx from 'clsx';
import { api } from '../hooks/useApi';
import toast from 'react-hot-toast';

// ─── Types ────────────────────────────────────────────────────────────────────

interface CheckItem {
  name: string;
  ok: boolean;
  latency_ms: number | null;
  detail: string;
}

interface HealthCheckResponse {
  checks: CheckItem[];
  overall: 'healthy' | 'degraded' | 'broken';
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function overallBadge(overall: HealthCheckResponse['overall']) {
  if (overall === 'healthy') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 rounded-full text-sm font-bold">
        <CheckCircle2 className="w-4 h-4" /> All Systems Healthy
      </span>
    );
  }
  if (overall === 'degraded') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 rounded-full text-sm font-bold">
        <AlertTriangle className="w-4 h-4" /> Degraded
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-red-500/15 text-red-400 border border-red-500/30 rounded-full text-sm font-bold">
      <XCircle className="w-4 h-4" /> System Broken
    </span>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function HealthCheck() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HealthCheckResponse | null>(null);
  const [lastRun, setLastRun] = useState<Date | null>(null);

  const runCheck = async () => {
    setLoading(true);
    try {
      const res = await api.get<HealthCheckResponse>('/system/health-check');
      setResult(res.data);
      setLastRun(new Date());
      if (res.data.overall === 'healthy') toast.success('All systems healthy!');
      else if (res.data.overall === 'degraded') toast('Some checks failed.', { icon: '⚠️' });
      else toast.error('Critical systems are down!');
    } catch (err: unknown) {
      toast.error((err as Error).message ?? 'Health check failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Activity className="w-6 h-6 text-violet-400" />
            System Health Check
          </h1>
          <p className="text-white/40 text-sm mt-1">
            Real-time probe of all external services and internal subsystems.
          </p>
        </div>
        <button
          onClick={runCheck}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl text-sm font-semibold text-white transition-all"
        >
          {loading
            ? <RefreshCw className="w-4 h-4 animate-spin" />
            : <RefreshCw className="w-4 h-4" />}
          {loading ? 'Running…' : result ? 'Re-run Checks' : 'Run Health Check'}
        </button>
      </div>

      {/* Loading state */}
      {loading && !result && (
        <div className="flex flex-col items-center justify-center py-24 gap-4 text-white/40">
          <RefreshCw className="w-8 h-8 animate-spin text-violet-400" />
          <p className="text-sm">Probing all services… (up to 10 s)</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !result && (
        <div className="flex flex-col items-center justify-center py-24 gap-4 text-white/20">
          <Activity className="w-12 h-12" />
          <p className="text-sm">Click &quot;Run Health Check&quot; to probe all services.</p>
        </div>
      )}

      {/* Results */}
      <AnimatePresence>
        {result && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            {/* Overall badge */}
            <div className="flex items-center justify-between mb-5">
              {overallBadge(result.overall)}
              {lastRun && (
                <span className="flex items-center gap-1.5 text-xs text-white/30">
                  <Clock className="w-3.5 h-3.5" />
                  Last run: {lastRun.toLocaleTimeString()}
                </span>
              )}
            </div>

            {/* Stats bar */}
            <div className="grid grid-cols-3 gap-3 mb-5">
              {[
                {
                  label: 'Total',
                  value: result.checks.length,
                  color: 'text-violet-400',
                  bg: 'bg-violet-500/10',
                },
                {
                  label: 'Passing',
                  value: result.checks.filter((c) => c.ok).length,
                  color: 'text-emerald-400',
                  bg: 'bg-emerald-500/10',
                },
                {
                  label: 'Failing',
                  value: result.checks.filter((c) => !c.ok).length,
                  color: 'text-red-400',
                  bg: 'bg-red-500/10',
                },
              ].map(({ label, value, color, bg }) => (
                <div key={label} className={clsx('rounded-xl border border-white/8 p-4 text-center', bg)}>
                  <p className={clsx('text-2xl font-black', color)}>{value}</p>
                  <p className="text-xs text-white/40 mt-0.5">{label}</p>
                </div>
              ))}
            </div>

            {/* Check rows */}
            <div className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
              <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-4 px-4 py-2 border-b border-white/8 text-xs font-semibold text-white/30 uppercase tracking-wider">
                <span>Status</span>
                <span>Service</span>
                <span className="text-right">Latency</span>
                <span className="text-right">Detail</span>
              </div>

              {result.checks.map((check, i) => (
                <motion.div
                  key={check.name}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className={clsx(
                    'grid grid-cols-[auto_1fr_auto_auto] items-center gap-4 px-4 py-3 transition-colors',
                    i % 2 === 0 ? 'bg-white/1' : 'bg-transparent',
                    'hover:bg-white/5',
                  )}
                >
                  {/* Status icon */}
                  <div className="flex items-center">
                    {check.ok ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                    )}
                  </div>

                  {/* Name */}
                  <span className="text-sm font-medium text-white">{check.name}</span>

                  {/* Latency */}
                  <span className="text-xs text-white/30 text-right whitespace-nowrap">
                    {check.latency_ms != null ? `${check.latency_ms} ms` : '—'}
                  </span>

                  {/* Detail */}
                  <span
                    className={clsx(
                      'text-xs text-right max-w-[180px] truncate',
                      check.ok ? 'text-white/40' : 'text-red-400',
                    )}
                    title={check.detail}
                  >
                    {check.detail}
                  </span>
                </motion.div>
              ))}
            </div>

            {/* Refresh button (bottom) */}
            <div className="flex justify-center mt-6">
              <button
                onClick={runCheck}
                disabled={loading}
                className="flex items-center gap-2 px-5 py-2 bg-white/5 hover:bg-white/10 border border-white/10 disabled:opacity-40 rounded-xl text-sm font-medium text-white/70 transition-all"
              >
                <RefreshCw className={clsx('w-4 h-4', loading && 'animate-spin')} />
                {loading ? 'Running…' : 'Refresh'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
