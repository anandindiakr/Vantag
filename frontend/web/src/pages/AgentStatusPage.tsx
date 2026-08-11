/**
 * AgentStatusPage — /agent-status
 *
 * Shows all Edge Agents registered to this tenant with live status,
 * last heartbeat age, device type, and camera count.
 * Polls every 30 seconds.  A "Trigger Scan" button fires a LAN camera
 * discovery scan on the agent's next heartbeat.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  MonitorCheck,
  Wifi,
  WifiOff,
  RefreshCw,
  Radar,
  Clock,
  Camera,
  Cpu,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface AgentItem {
  agent_id: string;
  device_type: string;
  device_name: string;
  status: 'online' | 'offline';
  last_heartbeat: string | null;
  last_heartbeat_age_seconds: number | null;
  camera_count: number;
  capabilities: Record<string, unknown> | null;
  created_at: string | null;
  model_status: {
    architecture?: string;
    provider?: string;
    avg_inference_ms?: number;
    inference_count?: number;
    is_preferred?: boolean;
  } | null;
  model_status_stale: boolean;
}

interface AIQuality {
  confirmed: number;
  false_positive: number;
  uncertain: number;
  reviewed: number;
  quality_proxy: number | null;
  false_positive_rate: number | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function relativeTime(seconds: number | null): string {
  if (seconds === null) return 'Never';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function deviceIcon(deviceType: string) {
  if (deviceType === 'windows') return '🖥️';
  if (deviceType === 'android') return '📱';
  if (deviceType === 'raspberry_pi') return '🍓';
  if (deviceType === 'mac') return '💻';
  return '⚙️';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function AgentStatusPage() {
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState<string | null>(null); // agent_id
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [quality, setQuality] = useState<AIQuality | null>(null);

  const fetchAgents = useCallback(async () => {
    const token = localStorage.getItem('vantag_token');
    if (!token) return;
    try {
      const res = await fetch('/api/edge/agents', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAgents(data.agents ?? []);
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Agent fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchQuality = useCallback(async () => {
    const token = localStorage.getItem('vantag_token');
    if (!token) return;
    try {
      const res = await fetch('/api/system/ai-quality', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setQuality(await res.json());
    } catch {
      // Quality metrics are diagnostic and must not affect agent status.
    }
  }, []);

  // Initial fetch + 30-second poll
  useEffect(() => {
    fetchAgents();
    fetchQuality();
    const id = setInterval(() => {
      fetchAgents();
      fetchQuality();
    }, 30_000);
    return () => clearInterval(id);
  }, [fetchAgents, fetchQuality]);

  const triggerScan = async (agentId: string) => {
    const token = localStorage.getItem('vantag_token');
    if (!token) return;
    setScanning(agentId);
    try {
      const res = await fetch('/api/cameras/scan-request', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast.success('LAN scan queued — the agent will run it on its next heartbeat (within ~30 s).');
    } catch {
      toast.error('Failed to trigger scan. Ensure the backend is reachable.');
    } finally {
      setScanning(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  const onlineCount = agents.filter((a) => a.status === 'online').length;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-violet-500/10 ring-1 ring-violet-500/30">
            <MonitorCheck size={22} className="text-violet-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-100">Edge Agent Status</h1>
            <p className="text-sm text-slate-400">
              {agents.length === 0
                ? 'No agents registered yet'
                : `${onlineCount} / ${agents.length} online`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-slate-500">
              Last refresh: {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchAgents}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-300 bg-slate-700/60 hover:bg-slate-700 transition-colors"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Agents"
          value={agents.length}
          icon={<Cpu size={18} className="text-violet-400" />}
          color="violet"
        />
        <StatCard
          label="Online"
          value={onlineCount}
          icon={<CheckCircle2 size={18} className="text-emerald-400" />}
          color="emerald"
        />
        <StatCard
          label="Offline"
          value={agents.length - onlineCount}
          icon={<AlertCircle size={18} className="text-slate-400" />}
          color="slate"
        />
        <div className="rounded-xl border border-slate-700/60 bg-cyan-500/10 p-4">
          <p className="text-xs text-slate-400">AI reviewed quality</p>
          <p className="text-2xl font-bold text-slate-100">
            {quality?.quality_proxy == null ? '—' : `${Math.round(quality.quality_proxy * 100)}%`}
          </p>
          <p className="text-xs text-slate-500">
            {quality?.reviewed ?? 0} reviewed · labels improve future tuning
          </p>
        </div>
      </div>

      {/* Agent table */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-500">
          <Loader2 size={24} className="animate-spin mr-2" />
          Loading agents…
        </div>
      ) : agents.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/60 bg-slate-800/60">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Device
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Last Heartbeat
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Cameras
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/40">
              {agents.map((agent) => (
                <AgentRow
                  key={agent.agent_id}
                  agent={agent}
                  isTriggeringScanning={scanning === agent.agent_id}
                  onTriggerScan={() => triggerScan(agent.agent_id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Help text */}
      <div className="rounded-xl border border-slate-700/40 bg-slate-800/30 p-4 text-sm text-slate-400 space-y-1">
        <p className="font-medium text-slate-300">How agents appear here</p>
        <p>
          An agent is <span className="text-emerald-400 font-medium">Online</span> when it has sent a heartbeat within the last 5 minutes.
          Agents heartbeat every 30 seconds. If the agent is running but shows offline, check that it can reach the backend URL in its <code className="bg-slate-700 px-1 rounded">config.json</code>.
        </p>
        <p>
          <span className="text-violet-400 font-medium">Trigger Scan</span> asks the agent to scan the store LAN for cameras on its next heartbeat. Discovered cameras appear in{' '}
          <a href="/cameras/manage" className="text-violet-400 underline underline-offset-2">
            Manage Cameras
          </a>.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: 'violet' | 'emerald' | 'slate';
}) {
  const bg = { violet: 'bg-violet-500/10', emerald: 'bg-emerald-500/10', slate: 'bg-slate-700/30' }[color];
  const ring = { violet: 'ring-violet-500/20', emerald: 'ring-emerald-500/20', slate: 'ring-slate-600/30' }[color];
  return (
    <div className={clsx('rounded-xl border p-4 flex items-center gap-3', bg, 'border-slate-700/60')}>
      <div className={clsx('flex items-center justify-center w-9 h-9 rounded-lg ring-1', bg, ring)}>
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-100">{value}</p>
        <p className="text-xs text-slate-400">{label}</p>
      </div>
    </div>
  );
}

function AgentRow({
  agent,
  isTriggeringScanning,
  onTriggerScan,
}: {
  agent: AgentItem;
  isTriggeringScanning: boolean;
  onTriggerScan: () => void;
}) {
  const online = agent.status === 'online';
  return (
    <tr className="hover:bg-slate-800/40 transition-colors">
      {/* Device */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{deviceIcon(agent.device_type)}</span>
          <div>
            <p className="font-medium text-slate-200">{agent.device_name}</p>
            <p className="text-xs text-slate-500 capitalize">{agent.device_type}</p>
            {agent.model_status && !agent.model_status_stale && (
              <p className="text-[11px] text-cyan-400/80">
                {agent.model_status.is_preferred ? 'YOLO26' : agent.model_status.architecture ?? 'Detector'}
                {agent.model_status.avg_inference_ms != null
                  ? ` · ${agent.model_status.avg_inference_ms.toFixed(1)} ms`
                  : ''}
              </p>
            )}
          </div>
        </div>
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          {online ? (
            <Wifi size={14} className="text-emerald-400" />
          ) : (
            <WifiOff size={14} className="text-slate-500" />
          )}
          <span
            className={clsx(
              'text-xs font-semibold px-2 py-0.5 rounded-full',
              online
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-slate-700/60 text-slate-500'
            )}
          >
            {online ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      </td>

      {/* Last heartbeat */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Clock size={13} />
          <span className="text-sm">
            {relativeTime(agent.last_heartbeat_age_seconds)}
          </span>
        </div>
      </td>

      {/* Camera count */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Camera size={13} />
          <span className="text-sm">{agent.camera_count}</span>
        </div>
      </td>

      {/* Actions */}
      <td className="px-4 py-3">
        <button
          onClick={onTriggerScan}
          disabled={isTriggeringScanning || !online}
          title={online ? 'Trigger LAN camera scan' : 'Agent must be online to trigger a scan'}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
            online && !isTriggeringScanning
              ? 'bg-violet-500/15 text-violet-400 hover:bg-violet-500/25 ring-1 ring-violet-500/30'
              : 'bg-slate-700/40 text-slate-600 cursor-not-allowed'
          )}
        >
          {isTriggeringScanning ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Radar size={12} />
          )}
          Trigger Scan
        </button>
      </td>
    </tr>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center space-y-4">
      <div className="flex items-center justify-center w-14 h-14 rounded-full bg-slate-800 ring-1 ring-slate-700">
        <MonitorCheck size={28} className="text-slate-500" />
      </div>
      <div>
        <p className="text-slate-300 font-medium">No Edge Agents registered</p>
        <p className="text-slate-500 text-sm mt-1">
          Download and run the Edge Agent on your store PC to see it here.
        </p>
      </div>
      <a
        href="/download"
        className="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-colors"
      >
        Install Edge Agent
      </a>
    </div>
  );
}
