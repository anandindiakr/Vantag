import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { MapPin, Camera, ChevronRight, AlertOctagon, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { Store, Severity } from '../store/useVantagStore';
import { useVantagStore } from '../store/useVantagStore';
import { useRiskScore } from '../hooks/useApi';

interface RiskScoreCardProps {
  store: Store;
}

function severityColor(s: Severity): string {
  switch (s) {
    case 'CRITICAL':
    case 'HIGH':   return 'text-vantag-red';
    case 'MEDIUM': return 'text-vantag-amber';
    default:       return 'text-vantag-green';
  }
}

function severityBg(s: Severity): string {
  switch (s) {
    case 'CRITICAL':
    case 'HIGH':   return 'bg-vantag-red/15 text-vantag-red border-vantag-red/30';
    case 'MEDIUM': return 'bg-vantag-amber/15 text-vantag-amber border-vantag-amber/30';
    default:       return 'bg-vantag-green/15 text-vantag-green border-vantag-green/30';
  }
}

function severityBorder(s: Severity): boolean {
  return s === 'HIGH' || s === 'CRITICAL';
}

export default function RiskScoreCard({ store }: RiskScoreCardProps) {
  const navigate = useNavigate();

  // Self-contained polling — each card fetches its own risk score every 10 s
  const { data: riskScore, isLoading } = useRiskScore(store.id);

  // Sync polled score into Zustand so the Dashboard alert banner stays current
  const updateRiskScore = useVantagStore((s) => s.updateRiskScore);
  useEffect(() => {
    if (riskScore) updateRiskScore(riskScore.storeId, riskScore);
  }, [riskScore, updateRiskScore]);

  const severity  = riskScore?.severity ?? 'LOW';
  const score     = riskScore?.score    ?? 0;
  const isHigh    = severityBorder(severity);

  const sparkData = (riskScore?.history ?? [])
    .slice(-10)
    .map((h) => ({ score: h.score }));

  const sparkColor =
    severity === 'HIGH' || severity === 'CRITICAL'
      ? '#EF4444'
      : severity === 'MEDIUM'
      ? '#F59E0B'
      : '#10B981';

  return (
    <div
      className={clsx(
        'relative bg-vantag-card rounded-xl border p-5 flex flex-col gap-4 transition-all duration-200 hover:ring-1 hover:ring-slate-500/50 cursor-pointer',
        isHigh
          ? 'border-vantag-red/60 animate-pulse-border'
          : 'border-slate-700/60'
      )}
      onClick={() => navigate(`/stores/${store.id}`)}
    >
      {/* HIGH badge indicator */}
      {isHigh && (
        <div className="absolute top-3 right-3">
          <AlertOctagon size={16} className="text-vantag-red animate-pulse" />
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-slate-100 truncate">{store.name}</h3>
          <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-400">
            <MapPin size={11} />
            <span className="truncate">{store.location}</span>
          </div>
        </div>
      </div>

      {/* Risk Score + Severity */}
      {isLoading ? (
        <div className="flex items-center gap-2 text-slate-500">
          <Loader2 size={18} className="animate-spin" />
          <span className="text-sm">Loading risk…</span>
        </div>
      ) : (
        <div className="flex items-end gap-3">
          <div className={clsx('text-5xl font-extrabold tabular-nums leading-none', severityColor(severity))}>
            {score}
          </div>
          <div className="flex flex-col gap-1 pb-0.5">
            <span
              className={clsx(
                'text-xs font-semibold px-2 py-0.5 rounded border',
                severityBg(severity)
              )}
            >
              {severity}
            </span>
            <span className="text-xs text-slate-500">risk score</span>
          </div>
        </div>
      )}

      {/* Sparkline */}
      <div className="h-14">
        {sparkData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkData}>
              <Tooltip
                contentStyle={{
                  background: '#0F172A',
                  border: '1px solid rgba(100,116,139,0.3)',
                  borderRadius: '6px',
                  fontSize: '12px',
                  color: '#F1F5F9',
                }}
                formatter={(v: number) => [v, 'Score']}
                labelFormatter={() => ''}
              />
              <Line
                type="monotone"
                dataKey="score"
                stroke={sparkColor}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-xs text-slate-600">
            No history yet
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-slate-700/60">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Camera size={12} />
          <span>{store.cameraCount} cameras</span>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); navigate(`/stores/${store.id}`); }}
          className="flex items-center gap-1 text-xs font-medium text-vantag-red hover:text-red-400 transition-colors"
        >
          View Store <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}
