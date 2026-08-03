/**
 * SystemHealthTab.tsx — Admin → System Health.
 *
 * Why this page exists
 * --------------------
 * Two capabilities used to fail invisibly:
 *
 *  1. The Edge Agent could fall back from YOLO26 to the older YOLOv8 detector,
 *     and the only trace was a console warning on the customer's own laptop.
 *     This page shows the architecture each agent VERIFIED by reading its
 *     loaded ONNX graph's output shape — so "YOLO26 is active" is a measured
 *     fact shown with its evidence, never an assumption.
 *
 *  2. A swallowed backend exception (the AI Assistant's missing dependency)
 *     produced no log line at all, so the only way to investigate was SSH.
 *     The Server Logs panel tails the backend's real log file.
 *
 * Honesty rules enforced here:
 *  - An agent that stopped heartbeating is shown as STALE, never as
 *    "confirmed active" from its last-known status.
 *  - If no log file exists on the server, the panel says so and prints the
 *    exact reason plus the command to run — it never renders fake log lines.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  Activity, AlertTriangle, CheckCircle2, Cpu, FileText, Mail,
  RefreshCw, ShieldCheck, XCircle,
} from 'lucide-react';

function authHeaders() {
  const token = localStorage.getItem('vantag_token') || '';
  return { Authorization: `Bearer ${token}` };
}

interface FaultRow {
  component: string;
  summary: string | null;
  detail: string | null;
  occurrences: number;
  first_seen: string | null;
  last_seen: string | null;
  last_alert_at: string | null;
  resolved_at: string | null;
  impact: string;
}

interface AgentRow {
  tenant_id: string;
  agent_id: string;
  agent_version: string;
  age_seconds: number;
  stale: boolean;
  status: {
    architecture?: string;
    is_preferred?: boolean;
    model?: string;
    expected_model?: string;
    ultralytics?: string;
    onnx_output_shape?: (number | string)[];
    acquire_error?: string | null;
    error?: string | null;
  };
}

interface HealthSnapshot {
  healthy: boolean;
  degraded_count: number;
  degraded: FaultRow[];
  faults: FaultRow[];
  agents: AgentRow[];
  fallback_agent_count: number;
  admin_alert_email: string;
  alert_cooldown_minutes: number;
  generated_at: string;
}

interface LogsResponse {
  source: string;
  reason?: string;
  checked_paths?: string[];
  fallback_command?: string;
  line_count?: number;
  lines: string[];
}

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString() : '—';

export default function SystemHealthTab() {
  const [snap, setSnap] = useState<HealthSnapshot | null>(null);
  const [logs, setLogs] = useState<LogsResponse | null>(null);
  const [logFilter, setLogFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [logLoading, setLogLoading] = useState(false);
  const [testing, setTesting] = useState(false);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get('/api/admin/system-health', { headers: authHeaders() });
      setSnap(data);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Could not load system health');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    setLogLoading(true);
    try {
      const params = new URLSearchParams({ lines: '300' });
      if (logFilter.trim()) params.set('contains', logFilter.trim());
      const { data } = await axios.get(`/api/admin/logs?${params}`, { headers: authHeaders() });
      setLogs(data);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Could not read logs');
    } finally {
      setLogLoading(false);
    }
  }, [logFilter]);

  useEffect(() => {
    fetchHealth();
    fetchLogs();
    // Auto-refresh health so a fallback shows up without a manual reload.
    const t = setInterval(fetchHealth, 30_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendTestAlert = async () => {
    setTesting(true);
    try {
      const { data } = await axios.post(
        '/api/admin/system-health/test-alert', {}, { headers: authHeaders() },
      );
      toast.success(data.message || 'Test alert sent');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Test alert failed');
    } finally {
      setTesting(false);
    }
  };

  const liveAgents = (snap?.agents || []).filter((a) => !a.stale);
  const yolo26Agents = liveAgents.filter((a) => a.status?.is_preferred === true);

  return (
    <div className="space-y-6">
      {/* ── Summary ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Activity size={18} className="text-cyan-400" /> System Health
          </h2>
          <p className="text-xs text-white/40 mt-0.5">
            Measured state only. Nothing here is assumed healthy by default.
            {snap && <> Last read {fmt(snap.generated_at)}.</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={sendTestAlert}
            disabled={testing}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-sm disabled:opacity-50"
          >
            <Mail size={14} /> {testing ? 'Sending…' : 'Send test alert'}
          </button>
          <button
            onClick={() => { fetchHealth(); fetchLogs(); }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-sm"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className={`rounded-xl border p-4 ${
          snap?.healthy
            ? 'bg-emerald-500/10 border-emerald-500/30'
            : 'bg-red-500/10 border-red-500/30'
        }`}>
          <div className="flex items-center gap-2 text-sm text-white/60">
            {snap?.healthy ? <CheckCircle2 size={16} className="text-emerald-400" />
                           : <AlertTriangle size={16} className="text-red-400" />}
            Overall
          </div>
          <div className="text-2xl font-bold mt-1">
            {snap ? (snap.healthy ? 'Healthy' : `${snap.degraded_count} issue(s)`) : '—'}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="flex items-center gap-2 text-sm text-white/60">
            <Cpu size={16} className="text-cyan-400" /> Detector (YOLO26)
          </div>
          <div className="text-2xl font-bold mt-1">
            {snap ? `${yolo26Agents.length}/${liveAgents.length}` : '—'}
            <span className="text-sm font-normal text-white/40 ml-2">
              live agents confirmed
            </span>
          </div>
          {snap && snap.fallback_agent_count > 0 && (
            <div className="text-xs text-red-300 mt-1">
              {snap.fallback_agent_count} agent(s) on the YOLOv8 fallback
            </div>
          )}
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="flex items-center gap-2 text-sm text-white/60">
            <Mail size={16} className="text-amber-400" /> Admin alerts
          </div>
          <div className="text-sm font-medium mt-2 break-all">
            {snap?.admin_alert_email || '—'}
          </div>
          <div className="text-xs text-white/40 mt-1">
            Repeat faults suppressed for {snap?.alert_cooldown_minutes ?? '—'} min
          </div>
        </div>
      </div>

      {/* ── Detector status per agent ──────────────────────────────────── */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 flex items-center gap-2">
          <ShieldCheck size={16} className="text-cyan-400" />
          <h3 className="font-semibold text-sm">Edge Agent detector verification</h3>
          <span className="text-xs text-white/30 ml-2">
            architecture read from each agent's loaded ONNX graph — not from the filename
          </span>
        </div>
        {!snap?.agents?.length ? (
          <div className="p-6 text-sm text-white/40">
            No agent has reported detector status yet. Agents report this on every
            heartbeat (~30s) once running agent v1.5.1 or newer.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-white/40 border-b border-white/10">
                <tr>
                  <th className="text-left px-4 py-2">Agent</th>
                  <th className="text-left px-4 py-2">Version</th>
                  <th className="text-left px-4 py-2">Detector</th>
                  <th className="text-left px-4 py-2">ONNX output shape</th>
                  <th className="text-left px-4 py-2">Ultralytics</th>
                  <th className="text-left px-4 py-2">Last heartbeat</th>
                </tr>
              </thead>
              <tbody>
                {snap.agents.map((a) => {
                  const ok = a.status?.is_preferred === true;
                  return (
                    <tr key={`${a.tenant_id}-${a.agent_id}`} className="border-b border-white/5">
                      <td className="px-4 py-3 font-mono text-xs text-white/70">
                        {a.agent_id.slice(0, 8)}…
                      </td>
                      <td className="px-4 py-3 text-white/60">{a.agent_version || '—'}</td>
                      <td className="px-4 py-3">
                        {a.stale ? (
                          <span className="inline-flex items-center gap-1.5 text-white/40">
                            <XCircle size={14} /> Stale — not reporting
                          </span>
                        ) : ok ? (
                          <span className="inline-flex items-center gap-1.5 text-emerald-400">
                            <CheckCircle2 size={14} /> YOLO26 active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-red-400">
                            <AlertTriangle size={14} /> Fallback: {a.status?.architecture || 'unknown'}
                          </span>
                        )}
                        {!a.stale && !ok && a.status?.acquire_error && (
                          <div className="text-[11px] text-red-300/70 mt-1 max-w-md">
                            {a.status.acquire_error}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-white/50">
                        {a.status?.onnx_output_shape
                          ? `[${a.status.onnx_output_shape.join(', ')}]`
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-white/50 text-xs">
                        {a.status?.ultralytics || '—'}
                      </td>
                      <td className="px-4 py-3 text-white/50 text-xs">
                        {a.age_seconds < 90
                          ? `${Math.round(a.age_seconds)}s ago`
                          : `${Math.round(a.age_seconds / 60)}m ago`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Faults ─────────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 flex items-center gap-2">
          <AlertTriangle size={16} className="text-amber-400" />
          <h3 className="font-semibold text-sm">Recorded faults</h3>
        </div>
        {!snap?.faults?.length ? (
          <div className="p-6 text-sm text-white/40">
            No faults recorded since the backend last started. Faults appear here
            the moment a component fails — they are no longer swallowed silently.
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {snap.faults.map((f) => (
              <div key={f.component} className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-white/10">
                        {f.component}
                      </span>
                      {f.resolved_at ? (
                        <span className="text-xs text-emerald-400">resolved</span>
                      ) : (
                        <span className="text-xs text-red-400">active</span>
                      )}
                      <span className="text-xs text-white/40">
                        ×{f.occurrences}
                      </span>
                    </div>
                    <div className="text-sm mt-1.5">{f.summary}</div>
                    {f.impact && (
                      <div className="text-xs text-amber-300/70 mt-1">{f.impact}</div>
                    )}
                    {f.detail && (
                      <pre className="text-[11px] text-white/50 mt-2 whitespace-pre-wrap bg-black/30 rounded p-2 max-h-40 overflow-auto">
                        {f.detail}
                      </pre>
                    )}
                  </div>
                  <div className="text-right text-[11px] text-white/40 shrink-0">
                    <div>first {fmt(f.first_seen)}</div>
                    <div>last {fmt(f.last_seen)}</div>
                    <div>emailed {fmt(f.last_alert_at)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Server logs ────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3 flex-wrap">
          <FileText size={16} className="text-cyan-400" />
          <h3 className="font-semibold text-sm">Server logs</h3>
          {logs?.source && logs.source !== 'unavailable' && (
            <span className="text-xs font-mono text-white/30">{logs.source}</span>
          )}
          <div className="flex-1" />
          <input
            value={logFilter}
            onChange={(e) => setLogFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchLogs()}
            placeholder="Filter (e.g. ERROR, yolo, openai)"
            className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs w-56 focus:outline-none focus:border-cyan-500/50"
          />
          <button
            onClick={fetchLogs}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs"
          >
            <RefreshCw size={12} className={logLoading ? 'animate-spin' : ''} /> Tail
          </button>
        </div>

        {logs?.source === 'unavailable' ? (
          <div className="p-4 text-sm text-amber-300/80 space-y-2">
            <p>{logs.reason}</p>
            {logs.fallback_command && (
              <p className="text-xs text-white/50">
                Read them directly with:{' '}
                <code className="px-1.5 py-0.5 rounded bg-black/40 font-mono">
                  {logs.fallback_command}
                </code>
              </p>
            )}
          </div>
        ) : (
          <pre className="p-4 text-[11px] leading-relaxed font-mono text-white/70 max-h-96 overflow-auto whitespace-pre-wrap">
            {logs?.lines?.length
              ? logs.lines.join('\n')
              : logLoading ? 'Loading…' : 'No matching log lines.'}
          </pre>
        )}
      </div>
    </div>
  );
}
