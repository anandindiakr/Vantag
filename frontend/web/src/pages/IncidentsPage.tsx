import { useState, useMemo } from 'react';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  SortAsc,
  SortDesc,
  Filter,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useIncidents, useGenerateReport } from '../hooks/useApi';
import { Severity, EventType, Incident } from '../store/useVantagStore';

type SortKey = 'ts' | 'severity' | 'riskScore';
type SortDir  = 'asc' | 'desc';

const SEVERITY_ORDER: Record<Severity, number> = {
  CRITICAL: 4,
  HIGH:     3,
  MEDIUM:   2,
  LOW:      1,
};

const EVENT_TYPE_LABELS: Record<EventType, string> = {
  sweep:           'Sweep',
  dwell:           'Dwell',
  empty_shelf:     'Empty Shelf',
  watchlist_match: 'Watchlist Match',
  queue_alert:     'Queue Alert',
  door_event:      'Door Event',
  loitering:       'Loitering',
  crowd:           'Crowd',
  theft_attempt:   'Theft Attempt',
  system:          'System',
};

function SeverityBadge({ s }: { s: Severity }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold',
        s === 'CRITICAL' || s === 'HIGH'
          ? 'bg-vantag-red/20 text-vantag-red'
          : s === 'MEDIUM'
          ? 'bg-vantag-amber/20 text-vantag-amber'
          : 'bg-vantag-green/20 text-vantag-green'
      )}
    >
      {s}
    </span>
  );
}

export default function IncidentsPage() {
  const [page, setPage]               = useState(1);
  const [sortKey, setSortKey]         = useState<SortKey>('ts');
  const [sortDir, setSortDir]         = useState<SortDir>('desc');
  const [severityFilter, setSeverityFilter] = useState<Severity | 'ALL'>('ALL');
  const [typeFilter, setTypeFilter]   = useState<EventType | 'all'>('all');
  const [downloadingId, setDownloadingId]   = useState<string | null>(null);

  const { data, isLoading, isFetching } = useIncidents(null, page);
  const { mutateAsync: generateReport } = useGenerateReport();

  const items: Incident[] = useMemo(() => {
    let list = data?.items ?? [];

    // Filter
    if (severityFilter !== 'ALL') {
      list = list.filter((i) => i.severity === severityFilter);
    }
    if (typeFilter !== 'all') {
      list = list.filter((i) => i.type === typeFilter);
    }

    // Sort
    list = [...list].sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'ts') {
        cmp = new Date(a.ts).getTime() - new Date(b.ts).getTime();
      } else if (sortKey === 'severity') {
        cmp = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
      } else if (sortKey === 'riskScore') {
        cmp = a.riskScore - b.riskScore;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return list;
  }, [data, severityFilter, typeFilter, sortKey, sortDir]);

  const totalPages = data?.pages ?? 1;

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const handleDownload = async (incident: Incident) => {
    setDownloadingId(incident.id);
    try {
      const blob = await generateReport(incident.id);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `incident-${incident.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Report downloaded');
    } catch (err) {
      toast.error(`Failed to download report: ${(err as Error).message}`);
    } finally {
      setDownloadingId(null);
    }
  };

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <SortAsc size={12} className="text-slate-600" />;
    return sortDir === 'asc'
      ? <SortAsc size={12} className="text-vantag-red" />
      : <SortDesc size={12} className="text-vantag-red" />;
  }

  return (
    <div className="min-h-screen bg-vantag-dark pb-10">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle size={22} className="text-vantag-red" />
            <div>
              <h1 className="text-xl font-bold text-slate-100">Incident Log</h1>
              <p className="text-xs text-slate-400">
                {data?.total ?? 0} total incidents
                {isFetching && !isLoading && (
                  <span className="ml-2 text-slate-600">· Refreshing…</span>
                )}
              </p>
            </div>
          </div>
        </div>
      </header>

      <div className="px-6 py-6 space-y-4">
        {/* ── Filters ─────────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <Filter size={13} />
            <span>Filter:</span>
          </div>

          {/* Severity filter */}
          <div className="flex gap-1">
            {(['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((s) => (
              <button
                key={s}
                onClick={() => { setSeverityFilter(s); setPage(1); }}
                className={clsx(
                  'text-xs px-2.5 py-1 rounded-lg border transition-colors font-medium',
                  severityFilter === s
                    ? s === 'ALL'
                      ? 'bg-slate-500 text-white border-slate-400'
                      : s === 'CRITICAL' || s === 'HIGH'
                      ? 'bg-vantag-red/20 text-vantag-red border-vantag-red/40'
                      : s === 'MEDIUM'
                      ? 'bg-vantag-amber/20 text-vantag-amber border-vantag-amber/40'
                      : 'bg-vantag-green/20 text-vantag-green border-vantag-green/40'
                    : 'border-slate-700/60 text-slate-500 hover:text-slate-300 hover:border-slate-500'
                )}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Event type filter */}
          <select
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value as EventType | 'all'); setPage(1); }}
            className="bg-vantag-card border border-slate-700/60 rounded-lg px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-slate-400"
          >
            <option value="all">All Event Types</option>
            {(Object.entries(EVENT_TYPE_LABELS) as [EventType, string][]).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>

        {/* ── Table ─────────────────────────────────────────────────── */}
        <div className="bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden">
          {/* Column headers */}
          <div className="grid grid-cols-12 px-4 py-3 border-b border-slate-700/60 text-xs font-semibold text-slate-500 uppercase tracking-wider">
            <button
              className="col-span-2 flex items-center gap-1 hover:text-slate-300 transition-colors"
              onClick={() => handleSort('ts')}
            >
              Timestamp <SortIcon col="ts" />
            </button>
            <div className="col-span-2">Store / Camera</div>
            <div className="col-span-2">Event Type</div>
            <button
              className="col-span-1 flex items-center gap-1 hover:text-slate-300 transition-colors"
              onClick={() => handleSort('severity')}
            >
              Severity <SortIcon col="severity" />
            </button>
            <button
              className="col-span-1 flex items-center gap-1 hover:text-slate-300 transition-colors"
              onClick={() => handleSort('riskScore')}
            >
              Risk <SortIcon col="riskScore" />
            </button>
            <div className="col-span-3">Description</div>
            <div className="col-span-1" />
          </div>

          {/* Rows */}
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={28} className="animate-spin text-slate-500" />
            </div>
          ) : items.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-slate-500 text-sm gap-2">
              No incidents match the current filters
            </div>
          ) : (
            <div className="divide-y divide-slate-700/40">
              {items.map((inc) => (
                <div
                  key={inc.id}
                  className={clsx(
                    'grid grid-cols-12 items-center px-4 py-3 gap-2 hover:bg-slate-700/15 transition-colors text-sm animate-fade-in',
                    inc.severity === 'CRITICAL' && 'border-l-2 border-vantag-red'
                  )}
                >
                  {/* Timestamp */}
                  <div className="col-span-2">
                    <p className="text-slate-200 text-xs font-mono">
                      {new Date(inc.ts).toLocaleDateString()}
                    </p>
                    <p className="text-slate-500 text-xs font-mono">
                      {new Date(inc.ts).toLocaleTimeString()}
                    </p>
                  </div>

                  {/* Store / Camera */}
                  <div className="col-span-2 min-w-0">
                    <p className="text-xs text-slate-200 truncate font-medium">{inc.storeName}</p>
                    <p className="text-xs text-slate-500 truncate">{inc.cameraName}</p>
                  </div>

                  {/* Event type */}
                  <div className="col-span-2">
                    <span className="text-xs text-slate-300 bg-slate-800/60 px-2 py-0.5 rounded">
                      {EVENT_TYPE_LABELS[inc.type] ?? inc.type}
                    </span>
                  </div>

                  {/* Severity */}
                  <div className="col-span-1">
                    <SeverityBadge s={inc.severity} />
                  </div>

                  {/* Risk score */}
                  <div className="col-span-1">
                    <span
                      className={clsx(
                        'text-sm font-bold tabular-nums',
                        inc.riskScore >= 75
                          ? 'text-vantag-red'
                          : inc.riskScore >= 50
                          ? 'text-vantag-amber'
                          : 'text-vantag-green'
                      )}
                    >
                      {inc.riskScore}
                    </span>
                  </div>

                  {/* Description */}
                  <div className="col-span-3 min-w-0">
                    <p className="text-xs text-slate-300 truncate">{inc.description}</p>
                    {inc.resolved && (
                      <span className="text-xs text-vantag-green">Resolved</span>
                    )}
                  </div>

                  {/* Download */}
                  <div className="col-span-1 flex justify-end">
                    <button
                      onClick={() => handleDownload(inc)}
                      disabled={downloadingId === inc.id}
                      title="Download report"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-slate-700/40 transition-colors disabled:opacity-40"
                    >
                      {downloadingId === inc.id ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Download size={14} />
                      )}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Pagination ─────────────────────────────────────────────── */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Page {page} of {totalPages} · {data?.total ?? 0} incidents
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-vantag-card border border-slate-700/60 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={13} /> Prev
              </button>

              {/* Page numbers */}
              <div className="flex gap-1">
                {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                  const p = Math.max(1, Math.min(page - 3 + i, totalPages - 6 + i));
                  return (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={clsx(
                        'w-8 h-8 rounded-lg text-xs font-medium transition-colors',
                        p === page
                          ? 'bg-vantag-red text-white'
                          : 'bg-vantag-card border border-slate-700/60 text-slate-400 hover:text-slate-200'
                      )}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-vantag-card border border-slate-700/60 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next <ChevronRight size={13} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
