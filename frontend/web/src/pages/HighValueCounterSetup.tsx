import { useState, useRef, useEffect, useCallback } from 'react';
import {
  RefreshCw, Save, Trash2, Loader2, CheckCircle,
  Undo2, PlayCircle, Gem, MousePointerClick,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { api, useCameras } from '../hooks/useApi';

// ── Types ─────────────────────────────────────────────────────────────────────

type PolyType = 'counter' | 'tray' | 'case' | 'exit' | 'approach';
type Point = [number, number];           // image coords (e.g. 1920×1080)
type CanvasPoint = [number, number];     // canvas coords (960×540)

interface PolyMeta {
  key:       PolyType;
  label:     string;
  emoji:     string;
  hex:       string;
  desc:      string;
  detector:  string;
  eventType: string;                     // demo event fired by "Test"
  severity:  string;
}

const POLY_META: Record<PolyType, PolyMeta> = {
  counter: {
    key: 'counter', label: 'Serving Counter', emoji: '🧍', hex: '#f59e0b',
    desc: 'Where a customer stands to view items. Gates hand reach-in and tray change.',
    detector: 'Case Hand Reach + Tray Change', eventType: 'jewelry_handover', severity: 'high',
  },
  tray: {
    key: 'tray', label: 'Display Tray', emoji: '💍', hex: '#eab308',
    desc: 'The velvet tray / case opening a hand reaches into.',
    detector: 'Case Hand Reach + Tray Change', eventType: 'jewelry_tray', severity: 'high',
  },
  case: {
    key: 'case', label: 'Display Case', emoji: '🪟', hex: '#ef4444',
    desc: 'The case area a suspect must enter before fleeing.',
    detector: 'Grab & Run', eventType: 'grab_and_run', severity: 'critical',
  },
  exit: {
    key: 'exit', label: 'Exit Door', emoji: '🚪', hex: '#f97316',
    desc: 'The door / exit of the room.',
    detector: 'Grab & Run', eventType: 'grab_and_run', severity: 'critical',
  },
  approach: {
    key: 'approach', label: 'Approach Corridor', emoji: '➡️', hex: '#38bdf8',
    desc: 'Optional — the corridor toward the counter (a person must pass through it first).',
    detector: 'Grab & Run (optional gate)', eventType: 'grab_and_run', severity: 'critical',
  },
};

const POLY_ORDER: PolyType[] = ['counter', 'tray', 'case', 'exit', 'approach'];

function toImageCoords(cx: number, cy: number, cw: number, ch: number, iw = 1920, ih = 1080): Point {
  return [Math.round((cx / cw) * iw), Math.round((cy / ch) * ih)];
}

function toCanvasCoords(ix: number, iy: number, cw: number, ch: number, iw = 1920, ih = 1080): CanvasPoint {
  return [(ix / iw) * cw, (iy / ih) * ch];
}

const CANVAS_W = 960;
const CANVAS_H = 540;
const CLOSE_PX = 12;   // click within this many canvas px of the first vertex to close

// ── Component ─────────────────────────────────────────────────────────────────

export default function HighValueCounterSetup() {
  const [camId,     setCamId]     = useState('');
  const [snapUrl,   setSnapUrl]   = useState('');
  const [snapLoading, setSnapLoading] = useState(false);
  const [mode,      setMode]      = useState<PolyType | null>(null);
  const [draft,     setDraft]     = useState<CanvasPoint[]>([]);   // in-progress polygon (canvas coords)
  const [polys,     setPolys]     = useState<Record<PolyType, Point[] | null>>({
    counter: null, tray: null, case: null, exit: null, approach: null,
  });
  const [camRes,    setCamRes]     = useState({ width: 1920, height: 1080 });
  const [saving,    setSaving]     = useState(false);
  const [testing,   setTesting]    = useState<PolyType | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef    = useRef<HTMLImageElement | null>(null);
  const snapshotRequestRef = useRef(0);
  const { data: liveCameras = [], isLoading: camsLoading, isError: camsError } = useCameras();

  const cameras = liveCameras.map((camera) => ({
    id: camera.id,
    label: `${camera.id} — ${camera.name}${camera.location ? ` · ${camera.location}` : ''}`,
  }));

  // ── Camera selection ────────────────────────────────────────────────────────
  useEffect(() => {
    if (liveCameras.length === 0) { setCamId(''); return; }
    setCamId((current) =>
      current && liveCameras.some((camera) => camera.id === current)
        ? current
        : liveCameras[0].id
    );
  }, [liveCameras]);

  // ── Snapshot ────────────────────────────────────────────────────────────────
  const refreshSnapshot = useCallback(async () => {
    if (!camId) return;
    const requestId = ++snapshotRequestRef.current;
    const requestedCameraId = camId;
    setSnapLoading(true);
    setSnapUrl((current) => { if (current) URL.revokeObjectURL(current); return ''; });
    imgRef.current = null;
    try {
      const resp = await api.get(`/cameras/${camId}/snapshot?t=${Date.now()}`, { responseType: 'blob' });
      if (requestId === snapshotRequestRef.current && requestedCameraId === camId) {
        setSnapUrl(URL.createObjectURL(resp.data as Blob));
      }
    } catch {
      if (requestId === snapshotRequestRef.current) {
        toast.error('Could not load snapshot. Is the camera online?');
      }
    } finally {
      if (requestId === snapshotRequestRef.current) setSnapLoading(false);
    }
  }, [camId]);

  // ── Load saved polygons + snapshot on camera change ─────────────────────────
  useEffect(() => {
    if (!camId) { setPolys({ counter: null, tray: null, case: null, exit: null, approach: null }); setSnapUrl(''); imgRef.current = null; return; }
    setPolys({ counter: null, tray: null, case: null, exit: null, approach: null });
    setDraft([]);
    setMode(null);
    setCamRes({ width: 1920, height: 1080 });
    void refreshSnapshot();
    api.get(`/zones/cameras/${camId}/high-value-counter`)
      .then(({ data }) => {
        setCamRes(data.resolution ?? { width: 1920, height: 1080 });
        const z = data.zones ?? {};
        setPolys({
          counter:  Array.isArray(z.counter_polygon)  ? z.counter_polygon  : null,
          tray:     Array.isArray(z.tray_polygon)     ? z.tray_polygon     : null,
          case:     Array.isArray(z.case_polygon)     ? z.case_polygon     : null,
          exit:     Array.isArray(z.exit_polygon)     ? z.exit_polygon     : null,
          approach: Array.isArray(z.approach_polygon) ? z.approach_polygon : null,
        });
      })
      .catch(() => {
        // First-time setup: no polygons saved yet is not an error.
      });
  }, [camId, refreshSnapshot]);

  // ── Canvas draw loop ────────────────────────────────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
    if (imgRef.current && snapUrl) {
      ctx.drawImage(imgRef.current, 0, 0, CANVAS_W, CANVAS_H);
    } else {
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
    }

    const renderPoly = (pts: CanvasPoint[], hex: string, label: string, closed: boolean) => {
      if (pts.length === 0) return;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i += 1) ctx.lineTo(pts[i][0], pts[i][1]);
      if (closed && pts.length >= 3) ctx.closePath();
      ctx.strokeStyle = hex;
      ctx.lineWidth = 2.5;
      ctx.setLineDash(closed ? [] : [6, 3]);
      ctx.stroke();
      if (closed && pts.length >= 3) {
        ctx.fillStyle = `${hex}22`;
        ctx.fill();
      }
      for (const [x, y] of pts) {
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = hex;
        ctx.fill();
      }
      ctx.font = 'bold 12px system-ui, sans-serif';
      ctx.fillStyle = hex;
      ctx.fillText(label, pts[0][0] + 8, pts[0][1] - 8);
      ctx.restore();
    };

    // Saved polygons (image coords → canvas coords)
    for (const type of POLY_ORDER) {
      const poly = polys[type];
      if (!poly || poly.length < 3) continue;
      const meta = POLY_META[type];
      const pts = poly.map(([ix, iy]) =>
        toCanvasCoords(ix, iy, CANVAS_W, CANVAS_H, camRes.width, camRes.height)
      );
      renderPoly(pts, meta.hex, meta.label, true);
    }

    // In-progress draft
    if (mode && draft.length > 0) {
      const meta = POLY_META[mode];
      renderPoly(draft, meta.hex, meta.label, false);
    }

    // Empty-state hint
    if (!imgRef.current && !snapUrl && !snapLoading) {
      ctx.fillStyle = 'rgba(148,163,184,0.7)';
      ctx.font = '15px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Load a camera snapshot, then click points to draw a polygon', CANVAS_W / 2, CANVAS_H / 2);
      ctx.textAlign = 'start';
    }
  }, [snapUrl, snapLoading, polys, draft, mode, camRes]);

  useEffect(() => { draw(); }, [draw]);

  useEffect(() => {
    if (!snapUrl) return;
    const img = new Image();
    img.onload = () => { imgRef.current = img; draw(); };
    img.src = snapUrl;
  }, [snapUrl, draw]);

  // ── Pointer handling (point-and-click vertices) ─────────────────────────────
  const getPos = (e: React.PointerEvent<HTMLCanvasElement>): CanvasPoint => {
    const canvas = canvasRef.current!;
    const r = canvas.getBoundingClientRect();
    const scaleX = canvas.width / r.width;
    const scaleY = canvas.height / r.height;
    const x = Math.max(0, Math.min(canvas.width, (e.clientX - r.left) * scaleX));
    const y = Math.max(0, Math.min(canvas.height, (e.clientY - r.top) * scaleY));
    return [x, y];
  };

  const commitDraft = useCallback(() => {
    if (!mode || draft.length < 3) return;
    const poly: Point[] = draft.map(([cx, cy]) =>
      toImageCoords(cx, cy, CANVAS_W, CANVAS_H, camRes.width, camRes.height)
    );
    setPolys((prev) => ({ ...prev, [mode]: poly }));
    setDraft([]);
    toast.success(`${POLY_META[mode].label} polygon saved — click "Save" to persist.`);
  }, [mode, draft, camRes]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!mode) return;
    e.preventDefault();
    const pos = getPos(e);

    // Click near the first vertex with ≥3 points closes the polygon.
    if (draft.length >= 3) {
      const [fx, fy] = draft[0];
      const d = Math.hypot(pos[0] - fx, pos[1] - fy);
      if (d <= CLOSE_PX) { commitDraft(); return; }
    }
    setDraft((d) => [...d, pos]);
  };

  const onDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    commitDraft();
  };

  const undoVertex = () => setDraft((d) => d.slice(0, -1));

  const clearPoly = (type: PolyType) => {
    setPolys((prev) => ({ ...prev, [type]: null }));
    if (mode === type) setDraft([]);
  };

  // ── Save / Test ─────────────────────────────────────────────────────────────
  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/zones/cameras/${camId}/high-value-counter`, {
        counter_polygon:  polys.counter,
        tray_polygon:     polys.tray,
        case_polygon:     polys.case,
        exit_polygon:     polys.exit,
        approach_polygon: polys.approach,
      });
      toast.success('High-Value Counter zones saved! The AI pipeline picks them up on the next cycle.');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save zones.');
    } finally {
      setSaving(false);
    }
  };

  const testPoly = async (type: PolyType) => {
    const meta = POLY_META[type];
    setTesting(type);
    try {
      await api.post('/demo/trigger', {
        event_type: meta.eventType,
        camera_id:  camId,
        severity:   meta.severity,
      });
      toast.success(`Test "${meta.label}" event fired — check Incidents page`);
    } catch {
      toast.error('Test failed.');
    } finally {
      setTesting(null);
    }
  };

  const anyPoly = POLY_ORDER.some((t) => polys[t] && polys[t]!.length >= 3);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-vantag-bg text-slate-100 p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <Gem size={24} className="text-amber-300" />
            High-Value Counter Setup
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Jewellery · Watches · Luxury goods — draw the counter, tray, case and exit polygons.
            No shelves and no POS required.
          </p>
        </div>
        <button
          onClick={save}
          disabled={saving || !anyPoly}
          className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-vantag-red hover:bg-red-600 text-white font-semibold text-sm transition-colors disabled:opacity-50 shadow-lg shadow-red-900/30"
        >
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          {saving ? 'Saving…' : 'Save Zones'}
        </button>
      </div>

      {/* Step 1 — polygon tools */}
      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-300">Step 1 — Choose a polygon to draw</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {POLY_ORDER.map((type) => {
            const meta = POLY_META[type];
            const selected = mode === type;
            const hasPoly = polys[type] && polys[type]!.length >= 3;
            return (
              <div
                key={type}
                className={clsx(
                  'relative rounded-2xl border-2 p-4 transition-all duration-200',
                  selected ? 'shadow-lg scale-[1.02]' : 'border-slate-700 bg-vantag-card opacity-80 hover:opacity-100 hover:border-slate-500'
                )}
                style={selected ? { borderColor: meta.hex, background: `${meta.hex}18`, boxShadow: `0 0 0 3px ${meta.hex}33` } : {}}
              >
                {selected && (
                  <span className="absolute top-2 right-2 text-xs font-bold px-2 py-0.5 rounded-full" style={{ background: meta.hex, color: '#fff' }}>
                    Drawing
                  </span>
                )}
                <div className="text-2xl mb-1">{meta.emoji}</div>
                <div className="font-bold text-sm text-slate-100 mb-0.5">{meta.label}</div>
                <div className="text-[11px] font-semibold mb-2" style={{ color: meta.hex }}>{meta.detector}</div>
                <div className="text-xs text-slate-400 leading-relaxed mb-3">{meta.desc}</div>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setMode(selected ? null : type); setDraft([]); }}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-semibold border transition-colors"
                    style={{ borderColor: meta.hex, color: meta.hex, background: `${meta.hex}14` }}
                  >
                    <MousePointerClick size={13} />
                    {selected ? 'Stop' : 'Draw'}
                  </button>
                  {hasPoly && (
                    <>
                      <button
                        onClick={() => testPoly(type)}
                        disabled={testing === type}
                        className="flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs hover:bg-blue-500/20 transition-colors disabled:opacity-50"
                        title="Fire a test event"
                      >
                        {testing === type ? <Loader2 size={12} className="animate-spin" /> : <PlayCircle size={12} />}
                      </button>
                      <button
                        onClick={() => clearPoly(type)}
                        className="flex items-center justify-center px-2 py-1.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs hover:bg-red-500/20 transition-colors"
                        title="Clear this polygon"
                      >
                        <Trash2 size={12} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Step 2 — camera + canvas */}
      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-300">
          Step 2 — {mode
            ? `Click points on the camera image to outline the ${POLY_META[mode].label}. Double-click (or click the first point) to finish.`
            : 'Select a polygon above, then click points on the camera image.'}
        </p>

        <div className="flex flex-wrap gap-3 items-center">
          <select
            value={camId}
            onChange={(e) => setCamId(e.target.value)}
            disabled={camsLoading}
            className="bg-vantag-card border border-slate-600 rounded-lg px-3 py-2 text-slate-200 text-sm disabled:opacity-50"
          >
            {camsLoading
              ? <option>Loading cameras…</option>
              : camsError
                ? <option value="">Could not load cameras</option>
                : cameras.length === 0
                  ? <option value="">No cameras configured</option>
                  : cameras.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <button
            onClick={refreshSnapshot}
            disabled={snapLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-vantag-card border border-slate-600 text-slate-300 hover:border-slate-400 text-sm transition-colors disabled:opacity-50"
          >
            {snapLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Refresh Snapshot
          </button>
          {mode && draft.length > 0 && (
            <>
              <button
                onClick={undoVertex}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 text-sm"
                title="Undo last vertex"
              >
                <Undo2 size={14} /> Undo Point
              </button>
              <button
                onClick={commitDraft}
                disabled={draft.length < 3}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 text-sm disabled:opacity-40"
                title="Finish polygon"
              >
                <CheckCircle size={14} /> Finish ({draft.length} pts)
              </button>
            </>
          )}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="xl:col-span-2">
            <div className="relative rounded-xl overflow-hidden border border-slate-700/60 bg-slate-900">
              {!snapUrl && !snapLoading && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10">
                  <RefreshCw size={36} className="text-slate-600" />
                  <p className="text-slate-500 text-sm font-medium">Click "Refresh Snapshot" to load the camera view</p>
                  <button
                    onClick={refreshSnapshot}
                    className="px-5 py-2.5 rounded-lg bg-vantag-red text-white text-sm font-semibold hover:bg-red-600 transition-colors"
                  >
                    Load Camera Image
                  </button>
                </div>
              )}
              <canvas
                ref={canvasRef}
                width={CANVAS_W}
                height={CANVAS_H}
                className={clsx('w-full block touch-none select-none', mode ? 'cursor-crosshair' : 'cursor-default')}
                onPointerDown={onPointerDown}
                onDoubleClick={onDoubleClick}
              />
            </div>
            <p className="text-xs text-slate-500 mt-2">
              {draft.length === 0
                ? 'Click points to begin a polygon. Double-click or click near the first point to close it.'
                : `${draft.length} point${draft.length !== 1 ? 's' : ''} placed — double-click or click the first point to finish.`}
            </p>
          </div>

          {/* Summary sidebar */}
          <div className="space-y-3">
            <h3 className="font-semibold text-slate-300 text-sm">Zones Defined</h3>
            {!anyPoly ? (
              <div className="rounded-xl border border-slate-700/60 p-6 text-center text-slate-500 text-sm">
                No polygons yet — draw one above.
              </div>
            ) : (
              <div className="space-y-2">
                {POLY_ORDER.map((type) => {
                  const poly = polys[type];
                  if (!poly || poly.length < 3) return null;
                  const meta = POLY_META[type];
                  return (
                    <div key={type} className="rounded-xl border border-slate-700/60 bg-vantag-card p-3">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-2 text-sm font-medium text-slate-200">
                          <span className="w-2.5 h-2.5 rounded-full" style={{ background: meta.hex }} />
                          {meta.emoji} {meta.label}
                        </span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{ background: `${meta.hex}22`, color: meta.hex }}>
                          {poly.length} pts
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-500 font-mono mt-1">
                        [{poly.map((p) => p.join(',')).join(' | ')}]
                      </p>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="rounded-xl border border-amber-600/40 bg-amber-950/30 p-4 space-y-2 text-xs text-amber-100/80">
              <p className="font-semibold text-amber-200">Tips for jewellery counters</p>
              <p>• <span className="text-amber-100 font-medium">Counter</span> = the serving surface a customer stands at.</p>
              <p>• <span className="text-amber-100 font-medium">Tray</span> = the exact velvet tray / case opening a hand reaches into.</p>
              <p>• <span className="text-amber-100 font-medium">Case + Exit</span> must be on the same camera for Grab &amp; Run.</p>
              <p>• Keep polygons tight — a hand-sized tray is far more accurate than a loose box.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
