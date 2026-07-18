import { useQuery } from '@tanstack/react-query';
import { Users, Camera, Clock, RefreshCw, AlertTriangle, TrendingUp, Printer } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../hooks/useApi';

// ─── Types (match GET /api/edge/people-counts) ──────────────────────────────
interface CameraCount {
  camera_id: string;
  person_count: number;
  age_seconds: number;
  stale: boolean;
}

interface HourlyPeak {
  hour: string;       // e.g. "2026-07-17T14:00"
  peak_count: number;
}

interface PeopleCountsResponse {
  total_people: number;
  cameras: CameraCount[];
  hourly_peaks: HourlyPeak[];
  updated_at: string;
}

async function fetchPeopleCounts(): Promise<PeopleCountsResponse> {
  const { data } = await api.get<PeopleCountsResponse>('/edge/people-counts');
  return data;
}

// Build a light-themed, print-friendly report in a new window.
function printReport(data: PeopleCountsResponse | undefined) {
  if (!data) return;
  const now = new Date().toLocaleString();
  const rows = data.cameras
    .map(
      (c) => `<tr>
        <td>${c.camera_id}</td>
        <td style="text-align:center;font-weight:bold">${c.person_count}</td>
        <td>${c.age_seconds < 60 ? `${c.age_seconds}s ago` : `${Math.floor(c.age_seconds / 60)}m ago`}</td>
        <td>${c.stale ? 'STALE' : 'LIVE'}</td>
      </tr>`
    )
    .join('');
  const peakRows = data.hourly_peaks
    .map((p) => {
      const label = p.hour.includes('T') ? p.hour.replace('T', ' ') : p.hour;
      return `<tr><td>${label}</td><td style="text-align:center;font-weight:bold">${p.peak_count}</td></tr>`;
    })
    .join('');
  const html = `<!doctype html><html><head><title>People Count Report</title>
    <style>
      body { font-family: Arial, Helvetica, sans-serif; color: #1e293b; margin: 32px; }
      h1 { font-size: 20px; margin-bottom: 2px; }
      .sub { color: #64748b; font-size: 12px; margin-bottom: 20px; }
      .cards { display: flex; gap: 16px; margin-bottom: 24px; }
      .card { border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 20px; }
      .card .label { font-size: 11px; text-transform: uppercase; color: #64748b; }
      .card .value { font-size: 26px; font-weight: bold; }
      table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13px; }
      th, td { border: 1px solid #cbd5e1; padding: 6px 10px; text-align: left; }
      th { background: #f1f5f9; font-size: 11px; text-transform: uppercase; color: #475569; }
      h2 { font-size: 14px; margin: 20px 0 8px; }
      .footer { font-size: 10px; color: #94a3b8; margin-top: 24px; }
    </style></head><body>
    <h1>People Count Report</h1>
    <div class="sub">Generated: ${now} &nbsp;|&nbsp; Data updated: ${data.updated_at}</div>
    <div class="cards">
      <div class="card"><div class="label">People in store (live)</div><div class="value">${data.total_people}</div></div>
      <div class="card"><div class="label">Cameras reporting</div><div class="value">${data.cameras.filter((c) => !c.stale).length} / ${data.cameras.length}</div></div>
      <div class="card"><div class="label">Peak (24h)</div><div class="value">${data.hourly_peaks.length ? Math.max(...data.hourly_peaks.map((p) => p.peak_count)) : 0}</div></div>
    </div>
    <h2>Per-camera counts</h2>
    <table><thead><tr><th>Camera</th><th>People</th><th>Last update</th><th>Status</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="4">No data</td></tr>'}</tbody></table>
    <h2>Hourly footfall peaks (last 24h)</h2>
    <table><thead><tr><th>Hour</th><th>Peak occupancy</th></tr></thead>
    <tbody>${peakRows || '<tr><td colspan="2">No history yet</td></tr>'}</tbody></table>
    <div class="footer">Counts are produced by YOLO person detection on the Edge Agent. Overlapping camera views may double-count.</div>
    <script>window.onload = function () { window.print(); };</script>
    </body></html>`;
  const w = window.open('', '_blank', 'width=900,height=700');
  if (w) {
    w.document.write(html);
    w.document.close();
  }
}

// ─── Page ────────────────────────────────────────────────────────────────────
export default function PeopleCountPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['people-counts'],
    queryFn: fetchPeopleCounts,
    refetchInterval: 10_000, // live refresh every 10s
  });

  const cameras = data?.cameras ?? [];
  const peaks = data?.hourly_peaks ?? [];
  const liveCameras = cameras.filter((c) => !c.stale);
  const maxPeak = Math.max(1, ...peaks.map((p) => p.peak_count));

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-3">
            <Users className="text-violet-400" size={26} />
            People Count
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Live person counts per camera, detected by the Edge Agent (YOLO). Updates with every agent heartbeat (~30s).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => printReport(data)}
            disabled={!data}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-sm text-white transition-colors"
          >
            <Printer size={15} />
            Print report
          </button>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm text-slate-200 border border-slate-700 transition-colors"
          >
            <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-red-900/20 border border-red-500/30 text-red-300 text-sm">
          <AlertTriangle size={18} />
          Failed to load people counts: {(error as Error)?.message ?? 'unknown error'}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-vantag-card border border-slate-700/60">
          <p className="text-xs uppercase tracking-wider text-slate-500">People in store (live)</p>
          <p className="text-4xl font-bold text-slate-100 mt-2">
            {isLoading ? '—' : data?.total_people ?? 0}
          </p>
          <p className="text-xs text-slate-500 mt-1">Sum across all live cameras</p>
        </div>
        <div className="p-5 rounded-2xl bg-vantag-card border border-slate-700/60">
          <p className="text-xs uppercase tracking-wider text-slate-500">Cameras reporting</p>
          <p className="text-4xl font-bold text-slate-100 mt-2">
            {isLoading ? '—' : `${liveCameras.length} / ${cameras.length}`}
          </p>
          <p className="text-xs text-slate-500 mt-1">Stale after 2 min without heartbeat</p>
        </div>
        <div className="p-5 rounded-2xl bg-vantag-card border border-slate-700/60">
          <p className="text-xs uppercase tracking-wider text-slate-500">Today's peak</p>
          <p className="text-4xl font-bold text-slate-100 mt-2">
            {isLoading ? '—' : peaks.length ? Math.max(...peaks.map((p) => p.peak_count)) : 0}
          </p>
          <p className="text-xs text-slate-500 mt-1">Highest hourly occupancy (24h)</p>
        </div>
      </div>

      {/* Per-camera table */}
      <div className="rounded-2xl bg-vantag-card border border-slate-700/60 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700/60 flex items-center gap-2">
          <Camera size={16} className="text-slate-400" />
          <h2 className="text-sm font-semibold text-slate-200">Per-camera counts</h2>
        </div>
        {isLoading ? (
          <div className="p-8 text-center text-slate-500 text-sm">Loading…</div>
        ) : cameras.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">
            No counts yet. Make sure the Windows Edge Agent (v1.5+) is running — person counts
            arrive with each heartbeat once cameras are streaming.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-700/60">
                <th className="px-5 py-3">Camera</th>
                <th className="px-5 py-3">People</th>
                <th className="px-5 py-3">Last update</th>
                <th className="px-5 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {cameras.map((c) => (
                <tr key={c.camera_id} className="border-b border-slate-800/60 last:border-0">
                  <td className="px-5 py-3 font-medium text-slate-200">{c.camera_id}</td>
                  <td className="px-5 py-3">
                    <span className={clsx(
                      'inline-flex items-center justify-center min-w-[2rem] px-2 py-0.5 rounded-lg font-bold',
                      c.stale ? 'bg-slate-700/50 text-slate-500' : 'bg-violet-500/15 text-violet-300'
                    )}>
                      {c.person_count}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-slate-400">
                    <span className="inline-flex items-center gap-1.5">
                      <Clock size={13} />
                      {c.age_seconds < 60 ? `${c.age_seconds}s ago` : `${Math.floor(c.age_seconds / 60)}m ago`}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span className={clsx(
                      'text-xs font-medium px-2 py-0.5 rounded',
                      c.stale
                        ? 'text-amber-400 bg-amber-500/10'
                        : 'text-vantag-green bg-vantag-green/10'
                    )}>
                      {c.stale ? 'STALE' : 'LIVE'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Hourly peaks chart (simple bars, last 24h) */}
      <div className="rounded-2xl bg-vantag-card border border-slate-700/60">
        <div className="px-5 py-4 border-b border-slate-700/60 flex items-center gap-2">
          <TrendingUp size={16} className="text-slate-400" />
          <h2 className="text-sm font-semibold text-slate-200">Hourly footfall peaks (last 24h)</h2>
        </div>
        <div className="p-5">
          {peaks.length === 0 ? (
            <p className="text-center text-slate-500 text-sm py-4">
              No history yet — peaks accumulate as the Edge Agent keeps reporting.
            </p>
          ) : (
            <div className="flex items-end gap-1 h-40">
              {peaks.map((p) => {
                const hourLabel = p.hour.includes('T') ? p.hour.split('T')[1]?.slice(0, 5) : p.hour;
                return (
                  <div key={p.hour} className="flex-1 flex flex-col items-center gap-1 group">
                    <span className="text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity">
                      {p.peak_count}
                    </span>
                    <div
                      className="w-full rounded-t bg-violet-500/60 group-hover:bg-violet-400 transition-colors"
                      style={{ height: `${Math.max(4, (p.peak_count / maxPeak) * 100)}%` }}
                    />
                    <span className="text-[9px] text-slate-600 rotate-0 whitespace-nowrap">{hourLabel}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Accuracy note */}
      <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/40 text-xs text-slate-400 leading-relaxed">
        <strong className="text-slate-300">Accuracy note:</strong> counts come from YOLO person detection
        on each camera frame. Overlapping camera views may count the same person twice — position cameras
        to cover distinct areas, or use the entrance camera alone for exact footfall. Typical accuracy for a
        clear overhead/angled view is 90–95%.
      </div>
    </div>
  );
}
