import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Maximize2, Minimize2, X, ExternalLink, MapPin } from 'lucide-react';
import clsx from 'clsx';
import type { Camera } from '../store/useVantagStore';

const SNAPSHOT_REFRESH_MS = 3000;

const NO_SIGNAL_SVG =
  'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">' +
  '<rect fill="%231E293B" width="320" height="180"/>' +
  '<circle cx="160" cy="78" r="26" fill="none" stroke="%23475569" stroke-width="3"/>' +
  '<path d="M160 104 v14 M160 136 l-14 -16 M160 136 l14 -16" stroke="%23475569" stroke-width="3" fill="none" stroke-linecap="round"/>' +
  '<text fill="%2364748B" font-family="sans-serif" font-size="13" text-anchor="middle" x="160" y="162">No Signal</text>' +
  '</svg>';

interface CameraTileProps {
  camera: Camera;
  /** Display name of the store this camera belongs to */
  storeName: string;
  onRemove?: () => void;
  onExpand?: () => void;
  expanded?: boolean;
  className?: string;
}

/**
 * A single live camera stream tile for the Multi-Store Wall.
 *
 * Streams are MJPEG served by the backend at /api/cameras/{id}/stream. The
 * JWT is passed as a query param because browsers cannot attach Authorization
 * headers to <img> requests (same pattern as StoreDetail / CameraView).
 */
export default function CameraTile({
  camera,
  storeName,
  onRemove,
  onExpand,
  expanded = false,
  className,
}: CameraTileProps) {
  const navigate = useNavigate();
  const [snapshotError, setSnapshotError] = useState(false);
  const [tick, setTick] = useState(0);

  // Use the same authenticated snapshot relay as the Cameras page. The
  // edge agent publishes JPEG snapshots to this endpoint; the MJPEG stream
  // endpoint can legitimately have no direct RTSP source on the VPS.
  useEffect(() => {
    if (!camera.online) {
      setSnapshotError(false);
      return undefined;
    }

    const interval = window.setInterval(() => {
      setTick((current) => current + 1);
      // Retry after a transient relay/network failure instead of leaving the
      // tile permanently stuck on its first error state.
      setSnapshotError(false);
    }, SNAPSHOT_REFRESH_MS);

    return () => window.clearInterval(interval);
  }, [camera.id, camera.online]);

  const authToken = localStorage.getItem('vantag_token') ?? '';
  const snapshotSrc = `/api/cameras/${encodeURIComponent(camera.id)}/snapshot?t=${tick}&token=${encodeURIComponent(authToken)}`;

  const openFullView = () => navigate(`/cameras/${encodeURIComponent(camera.storeId)}/${encodeURIComponent(camera.id)}`);

  return (
    <div
      className={clsx(
        'group overflow-hidden transition-colors',
        expanded
          ? 'fixed inset-0 z-50 rounded-none border-0 bg-black'
          : 'relative bg-black rounded-xl border',
        !expanded && (camera.online ? 'border-slate-700/60' : 'border-slate-800'),
        className
      )}
    >
      {/* ── Stream ─────────────────────────────────────────────────── */}
      {snapshotError || !camera.online ? (
        <div
          className={clsx(
            'bg-slate-900 flex items-center justify-center',
            expanded ? 'w-full h-full' : 'w-full aspect-video'
          )}
        >
          <img src={NO_SIGNAL_SVG} alt="No signal" className="w-48 h-28 opacity-80" />
        </div>
      ) : (
        <img
          key={tick}
          src={snapshotSrc}
          alt={`${camera.name} live stream`}
          className={clsx(
            'w-full cursor-pointer',
            expanded ? 'h-full object-contain' : 'aspect-video object-cover'
          )}
          onClick={openFullView}
          onError={() => setSnapshotError(true)}
        />
      )}

      {/* ── Store badge (top-left) ────────────────────────────────── */}
      <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5 max-w-[70%] px-2 py-1 rounded-md bg-black/60 backdrop-blur-sm border border-white/10">
        <MapPin size={11} className="text-vantag-green shrink-0" />
        <span className="text-[11px] font-medium text-slate-100 truncate">{storeName}</span>
      </div>

      {/* ── Hover action buttons (top-right) ──────────────────────── */}
      <div className={clsx(
        'absolute top-2 right-2 flex items-center gap-1 transition-opacity',
        expanded ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
      )}>
        {onExpand && (
          <button
            onClick={(e) => { e.stopPropagation(); onExpand(); }}
            className="p-1.5 rounded-lg bg-black/60 text-white hover:bg-black/80 border border-white/10 transition-colors"
            title={expanded ? 'Minimize' : 'Expand to fullscreen'}
          >
            {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); openFullView(); }}
          className="p-1.5 rounded-lg bg-black/60 text-white hover:bg-black/80 border border-white/10 transition-colors"
          title="Open full camera view"
        >
          <ExternalLink size={13} />
        </button>
        {onRemove && !expanded && (
          <button
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            className="p-1.5 rounded-lg bg-black/60 text-red-400 hover:bg-red-900/70 border border-white/10 transition-colors"
            title="Remove from wall"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {/* ── Bottom overlay: camera name + status ──────────────────── */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-3 pb-2 pt-8">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-slate-100 truncate">{camera.name}</span>
          <div className="flex items-center gap-1.5 shrink-0">
            <div
              className={clsx(
                'w-1.5 h-1.5 rounded-full',
                camera.online ? 'bg-vantag-green animate-pulse' : 'bg-slate-500'
              )}
            />
            <span className={clsx('text-[10px] font-semibold tracking-wide', camera.online ? 'text-vantag-green' : 'text-slate-400')}>
              {camera.online ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
