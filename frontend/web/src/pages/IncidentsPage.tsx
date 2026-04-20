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
  Camera,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useIncidents, useGenerateReport, useStores } from '../hooks/useApi';
import { Severity, EventType, Incident } from '../store/useVantagStore';

// ── Lightbox ──────────────────────────────────────────────────────────────────
function EvidenceLightbox({ url, onClose }: { url: string; onClose: () => void }) {
  const [imgError, setImgError] = useState(false);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative max-w-4xl w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-white/60 hover:text-white flex items-center gap-1 text-sm"
        >
          <X size={16} /> Close
        </button>
        {imgError ? (
          <div className="w-full rounded-xl border border-slate-600 bg-slate-800 flex flex-col items-center justify-center py-20 gap-3">
            <Camera size={36} className="text-slate-500" />
            <p className="text-slate-400 text-sm">Snapshot not available</p>
            <p className="text-slate-600 text-xs">The evidence image was captured before the camera frame loaded.</p>
          </div>
        ) : (
          <img
            src={url}
            alt="Evidence snapshot"
            className="w-full rounded-xl border border-slate-600 shadow-2xl"
            onError={() => setImgError(true)}
          />
        )}
        <p className="text-center text-xs text-slate-400 mt-3">
          Camera snapshot captured at the moment of detection — zone highlighted in colour
        </p>
      </div>
    </div>
  );
}

type SortKey = 'ts' | 'severity' | 'riskScore';
type SortDir  = 'asc' | 'desc';

const SEVERITY_ORDER: Record<Severity, number> = {
  CRITICAL: 4,
  HIGH:     3,
  MEDIUM:   2,
  LOW:      1,
};

const EVENT_TYPE_LABELS: Record<EventType, string> = {
  sweep:               'Sweep',
  dwell:               'Dwell',
  empty_shelf:         'Empty Shelf',
  watchlist_match:     'Watchlist Match',
  queue_alert:         'Queue Alert',
  door_event:          'Door Event',
  loitering:           'Loitering',
  crowd:               'Crowd',
  theft_attempt:       'Theft Attempt',
  system:              'System',
  // New AI analyzers
  shoplifting:         'Shoplifting',
  inventory_movement:  'Inventory Move',
  restricted_zone:     'Restricted Zone',
  queue_length:        'Queue Breach',
  fall_detection:      'Fall Detected',
  tamper:              'Camera Tamper',
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
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  // Collect all store IDs so we can aggregate incidents across them
  const { data: stores = [] } = useStores();
  const storeIds = useMemo(() => stores.map((s) => s.id).filter(Boolean), [stores]);

  const { data, isLoading, isFetching } = useIncidents(null, page, storeIds, typeFilter);
  const { mutateAsync: generateReport } = useGenerateReport();

  const items: Incident[] = useMemo(() => {
    let list = data?.items ?? [];

    // Severity filter is still client-side (fast, no server round-trip needed)
    if (severityFilter !== 'ALL') {
      list = list.filter((i) => i.severity === severityFilter);
    }
    // NOTE: typeFilter is now passed to the server — no client-side type filter needed.

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

  const totalPages   = data?.pages ?? 1;
  const serverTotal  = data?.total ?? 0;
  const filtersActive = severityFilter !== 'ALL' || typeFilter !== 'all';

  const clearFilters = () => { setSeverityFilter('ALL'); setTypeFilter('all'); setPage(1); };

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
      {/* Evidence lightbox */}
      {lightboxUrl && (
        <EvidenceLightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />
      )}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle size={22} className="text-vantag-red" />
            <div>
              <h1 className="text-xl font-bold text-slate-100">Incident Log</h1>
              <p className="text-xs text-slate-400">
                {filtersActive
                  ? <>{items.length} shown · <span className="text-slate-500">{serverTotal} total</span></>
                  : <>{serverTotal} total incidents</>
                }
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

          {/* Clear filters — only visible when a filter is active */}
          {filtersActive && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-vantag-red/10 border border-vantag-red/40 text-vantag-red text-xs hover:bg-vantag-red/20 transition-colors"
            >
              <X size={11} /> Clear Filters
            </button>
          )}
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
            <div className="col-span-3">Description &amp; Evidence</div>
            <div className="col-span-1" />
          </div>

          {/* Rows */}
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={28} className="animate-spin text-slate-500" />
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-500 text-sm gap-3">
              {filtersActive ? (
                <>
                  <Filter size={28} className="opacity-30" />
                  <p className="font-medium text-slate-400">No incidents match the active filters</p>
                  <p className="text-xs text-slate-600">
                    {serverTotal} total incidents in database — filters are hiding them all
                  </p>
                  <button
                    onClick={clearFilters}
                    className="mt-1 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-vantag-red/10 border border-vantag-red/40 text-vantag-red text-xs hover:bg-vantag-red/20 transition-colors"
                  >
                    <X size={12} /> Clear All Filters — Show All {serverTotal} Incidents
                  </button>
                </>
              ) : (
                <>
                  <AlertTriangle size={28} className="opacity-30" />
                  <span>No incidents recorded yet — try firing a test event from Zone Editor</span>
                </>
              )}
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

                  {/* Description + Evidence */}
                  <div className="col-span-3 min-w-0 space-y-1.5">
                    <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">
                      {inc.description}
                    </p>
                    {inc.snapshotUrl && (
                      <button
                        onClick={() => setLightboxUrl(inc.snapshotUrl!)}
                        className="flex items-center gap-1.5 group mt-1"
                        title="View evidence snapshot"
                      >
                        <img
                          src={inc.snapshotUrl}
                          alt="Evidence"
                          className="h-9 rounded border border-slate-600 group-hover:border-slate-400 transition-colors object-cover"
                          style={{ aspectRatio: '16/9', width: 'auto' }}
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                        />
                        <span className="text-[10px] text-slate-500 group-hover:text-slate-300 transition-colors flex items-center gap-1">
                          <Camera size={10} /> View evidence
                        </span>
                      </button>
                    )}
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
              Page {page} of {totalPages} ·{' '}
              {filtersActive
                ? <span><span className="text-vantag-red font-semibold">{items.length}</span> shown (filtered from {serverTotal})</span>
                : <span>{serverTotal} total incidents</span>
              }
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-vantag-card border border-slate-700/60 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={13} /> Prev
              </button>

              {/* Page numbers — simple window around current page */}
              <div className="flex gap-1">
                {(() => {
                  // Build a unique, sorted list of page numbers to show
                  const window = 2;
                  const nums = new Set([1, totalPages]);
                  for (let i = Math.max(1, page - window); i <= Math.min(totalPages, page + window); i++) nums.add(i);
                  const sorted = Array.from(nums).sort((a, b) => a - b);

                  const buttons: React.ReactNode[] = [];
                  sorted.forEach((p, idx) => {
                    if (idx > 0 && p - sorted[idx - 1] > 1) {
                      buttons.push(
                        <span key={`gap-${p}`} className="w-8 h-8 flex items-center justify-center text-slate-500 text-xs">…</span>
                      );
                    }
                    buttons.push(
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
                  });
                  return buttons;
                })()}
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
