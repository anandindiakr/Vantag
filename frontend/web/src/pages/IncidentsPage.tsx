import { useEffect, useMemo, useState } from 'react';
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
  CheckCircle2,
  ThumbsDown,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useIncidents, useGenerateReport, useStores, api } from '../hooks/useApi';
import { Severity, EventType, Incident } from '../store/useVantagStore';

// ── Lightbox ──────────────────────────────────────────────────────────────────
function LightboxImage({ url, caption }: { url: string; caption: string }) {
  const [imgError, setImgError] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    setImgError(false);
    setImageUrl(null);
    const requestUrl = url.startsWith('/api/') ? url.slice(4) : url;
    api.get(requestUrl, { responseType: 'blob' })
      .then(({ data }) => {
        objectUrl = URL.createObjectURL(data as Blob);
        setImageUrl(objectUrl);
      })
      .catch(() => setImgError(true));
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  return (
    <div>
      {imgError ? (
        <div className="w-full rounded-xl border border-slate-600 bg-slate-800 flex flex-col items-center justify-center py-20 gap-3">
          <Camera size={36} className="text-slate-500" />
          <p className="text-slate-400 text-sm">Snapshot not available</p>
          <p className="text-slate-600 text-xs">The evidence image was captured before the camera frame loaded.</p>
        </div>
      ) : imageUrl ? (
        <img
          src={imageUrl}
          alt={caption}
          className="w-full rounded-xl border border-slate-600 shadow-2xl"
          onError={() => setImgError(true)}
        />
      ) : (
        <div className="w-full rounded-xl border border-slate-600 bg-slate-800 flex items-center justify-center py-20">
          <Loader2 size={28} className="animate-spin text-slate-500" />
        </div>
      )}
      <p className="text-center text-xs text-slate-400 mt-3">{caption}</p>
    </div>
  );
}

function EvidenceLightbox({
  url,
  personUrl,
  personSecondsAgo,
  onClose,
}: {
  url: string;
  personUrl?: string;
  personSecondsAgo?: number;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm overflow-y-auto py-8"
      onClick={onClose}
    >
      <div
        className={clsx('relative w-full mx-4', personUrl ? 'max-w-6xl grid grid-cols-1 md:grid-cols-2 gap-4' : 'max-w-4xl')}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-white/60 hover:text-white flex items-center gap-1 text-sm"
        >
          <X size={16} /> Close
        </button>
        <LightboxImage
          url={url}
          caption="Camera snapshot captured at the moment of detection — zone highlighted in colour"
        />
        {personUrl && (
          <LightboxImage
            url={personUrl}
            caption={
              typeof personSecondsAgo === 'number'
                ? `Last person seen at this zone ~${Math.round(personSecondsAgo)}s before the change was confirmed`
                : 'Last person seen at this zone before the change was confirmed'
            }
          />
        )}
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
  STAFF:    0,
};

const EVENT_TYPE_LABELS: Record<EventType, string> = {
  shoplifting:        'Shoplifting',
  inventory_movement: 'Inventory Move',
  restricted_zone:    'Restricted Zone',
  queue_breach:       'Queue Breach',
  fall_detected:      'Fall Detected',
  loitering:          'Loitering',
  face_match:         'Face Match',
  tamper:             'Camera Tamper',
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
  const [lightbox, setLightbox] = useState<{ url: string; personUrl?: string; personSecondsAgo?: number } | null>(null);
  const [purging, setPurging]         = useState(false);
  const [labelingId, setLabelingId]   = useState<string | null>(null);
  const qc = useQueryClient();

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

  const handleFeedback = async (incident: Incident, verdict: 'confirmed' | 'false_positive') => {
    setLabelingId(incident.id);
    try {
      await api.post('/system/ai-feedback', {
        event_id: incident.id,
        verdict,
      });
      toast.success(verdict === 'confirmed' ? 'Detection marked confirmed' : 'False positive recorded for AI tuning');
    } catch (err) {
      toast.error(`Could not save AI feedback: ${(err as Error).message}`);
    } finally {
      setLabelingId(null);
    }
  };

  const handlePurgeDemo = async () => {
    if (!window.confirm('Remove all DEMO (synthetic test) incidents? Real incidents will be preserved.')) return;
    setPurging(true);
    try {
      const res = await api.delete('/demo/clear');
      toast.success(`Purged ${res.data?.cleared ?? 0} demo incident(s)`);
      await qc.invalidateQueries();
    } catch (err) {
      toast.error(`Failed to purge demo data: ${(err as Error).message}`);
    } finally {
      setPurging(false);
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
      {lightbox && (
        <EvidenceLightbox
          url={lightbox.url}
          personUrl={lightbox.personUrl}
          personSecondsAgo={lightbox.personSecondsAgo}
          onClose={() => setLightbox(null)}
        />
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
          <button
            onClick={handlePurgeDemo}
            disabled={purging}
            title="Remove all synthetic demo incidents (real incidents are preserved)"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/40 text-purple-300 text-xs hover:bg-purple-500/20 transition-colors disabled:opacity-40"
          >
            {purging ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
            Purge Demo Data
          </button>
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
                  <div className="col-span-2 flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs text-slate-300 bg-slate-800/60 px-2 py-0.5 rounded">
                      {EVENT_TYPE_LABELS[inc.type] ?? inc.type}
                    </span>
                    {inc.isDemo && (
                      <span
                        title="Synthetic test incident — generated for demo purposes, not a real detection"
                        className="text-[10px] font-bold tracking-wider text-purple-300 bg-purple-500/15 border border-purple-500/40 px-1.5 py-0.5 rounded"
                      >
                        DEMO
                      </span>
                    )}
                    {!inc.isDemo && inc.metadata?.source === 'edge_agent' && (
                      <span
                        title="Received from the Windows Edge Agent. This is not a simulated event."
                        className="text-[10px] font-bold tracking-wider text-cyan-300 bg-cyan-500/15 border border-cyan-500/40 px-1.5 py-0.5 rounded"
                      >
                        EDGE
                      </span>
                    )}
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
                        onClick={() =>
                          setLightbox({
                            url: inc.snapshotUrl!,
                            personUrl: inc.metadata?.person_snapshot_url as string | undefined,
                            personSecondsAgo: inc.metadata?.person_seen_seconds_ago as number | undefined,
                          })
                        }
                        className="flex items-center gap-1.5 group mt-1"
                        title="View evidence snapshot"
                      >
                        <span className="h-9 w-16 rounded border border-slate-600 group-hover:border-slate-400 transition-colors bg-slate-800 flex items-center justify-center">
                          <Camera size={13} className="text-slate-500" />
                        </span>
                        <span className="text-[10px] text-slate-500 group-hover:text-slate-300 transition-colors flex items-center gap-1">
                          <Camera size={10} /> View evidence
                        </span>
                      </button>
                    )}
                    {inc.resolved && (
                      <span className="text-xs text-vantag-green">Resolved</span>
                    )}
                    {!inc.isDemo && (
                      <div className="flex items-center gap-1 pt-1">
                        <span className="text-[10px] text-slate-600 mr-1">AI review</span>
                        <button
                          onClick={() => handleFeedback(inc, 'confirmed')}
                          disabled={labelingId === inc.id}
                          title="Confirm this detection"
                          className="inline-flex items-center gap-1 px-1.5 py-1 rounded text-[10px] text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 disabled:opacity-40"
                        >
                          <CheckCircle2 size={11} /> Confirm
                        </button>
                        <button
                          onClick={() => handleFeedback(inc, 'false_positive')}
                          disabled={labelingId === inc.id}
                          title="Mark as false positive"
                          className="inline-flex items-center gap-1 px-1.5 py-1 rounded text-[10px] text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 disabled:opacity-40"
                        >
                          <ThumbsDown size={11} /> False positive
                        </button>
                      </div>
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
