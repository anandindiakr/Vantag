import { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react';
import { RefreshCw, Save, Trash2, CheckCircle, Loader2, AlertCircle, Undo2 } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { api } from '../hooks/useApi';

// ── Types ─────────────────────────────────────────────────────────────────────

type ZoneType = 'shelf' | 'restricted' | 'queue';

interface Zone {
  id:       string;
  label:    string;
  type:     ZoneType;
  bbox:     [number, number, number, number];  // x1,y1,x2,y2 in image coords (1920×1080)
  maxQueue?: number;
}

interface Rect { x: number; y: number; w: number; h: number }

// Inline popup state
interface NamePopup {
  canvasX: number;
  canvasY: number;
  rect: Rect;
  defaultLabel: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CAMERAS = [
  { id: 'cam-01', label: 'cam-01 — Zone A' },
  { id: 'cam-03', label: 'cam-03 — Zone C' },
  { id: 'cam-04', label: 'cam-04 — Zone D' },
];

const ZONE_META: Record<ZoneType, {
  label: string; emoji: string; color: string; hex: string;
  tagline: string; desc: string; guide: string;
}> = {
  shelf: {
    label:   'Shelf Area',
    emoji:   '📦',
    color:   'green',
    hex:     '#22c55e',
    tagline: 'GREEN box',
    desc:    'Mark where your products are stored',
    guide:   'Click and drag on the camera image to mark a shelf area',
  },
  restricted: {
    label:   'No-Entry Area',
    emoji:   '🚫',
    color:   'red',
    hex:     '#ef4444',
    tagline: 'RED box',
    desc:    'Mark areas staff or nobody should enter',
    guide:   'Click and drag on the camera image to mark a restricted area',
  },
  queue: {
    label:   'Checkout Queue',
    emoji:   '🧍',
    color:   'blue',
    hex:     '#3b82f6',
    tagline: 'BLUE box',
    desc:    'Mark where customers wait to pay',
    guide:   'Click and drag on the camera image to mark the queue area',
  },
};

function uid() { return Math.random().toString(36).slice(2, 8); }

function toImageCoords(
  cx: number, cy: number, cw: number, ch: number,
  iw = 1920, ih = 1080
): [number, number] {
  return [Math.round((cx / cw) * iw), Math.round((cy / ch) * ih)];
}

function toCanvasCoords(
  ix: number, iy: number, cw: number, ch: number,
  iw = 1920, ih = 1080
): [number, number] {
  return [(ix / iw) * cw, (iy / ih) * ch];
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ZoneEditorPage() {
  const [camId,       setCamId]       = useState('cam-03');
  const [snapUrl,     setSnapUrl]     = useState('');
  const [snapLoading, setSnapLoading] = useState(false);
  const [mode,        setMode]        = useState<ZoneType | null>(null);
  const [zones,       setZones]       = useState<Zone[]>([]);
  const [saving,      setSaving]      = useState(false);
  const [testing,     setTesting]     = useState<string | null>(null);
  const [camRes,      setCamRes]      = useState({ width: 1920, height: 1080 });

  // Drawing
  const [isDrawing,   setIsDrawing]   = useState(false);
  const [dragStart,   setDragStart]   = useState<{ x: number; y: number } | null>(null);
  const [currentRect, setCurrentRect] = useState<Rect | null>(null);

  // Inline name popup
  const [namePopup,   setNamePopup]   = useState<NamePopup | null>(null);
  const [nameValue,   setNameValue]   = useState('');

  // Hover highlight
  const [hoveredId,   setHoveredId]   = useState<string | null>(null);

  // Guide animation
  const [guideTick,   setGuideTick]   = useState(0);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef    = useRef<HTMLImageElement | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Pulse animation for guide overlay
  useEffect(() => {
    const id = setInterval(() => setGuideTick((t) => t + 1), 200);
    return () => clearInterval(id);
  }, []);

  // ── Snapshot ──────────────────────────────────────────────────────────────

  const refreshSnapshot = useCallback(async () => {
    setSnapLoading(true);
    try {
      const resp = await api.get(`/cameras/${camId}/snapshot?t=${Date.now()}`, {
        responseType: 'blob',
      });
      setSnapUrl(URL.createObjectURL(resp.data as Blob));
    } catch {
      toast.error('Could not load snapshot. Is the camera online?');
    } finally {
      setSnapLoading(false);
    }
  }, [camId]);

  // Load zones + snapshot on camera change
  useEffect(() => {
    void refreshSnapshot();
    api.get(`/zones/cameras/${camId}`)
      .then(({ data }) => {
        const loaded: Zone[] = [];
        setCamRes(data.resolution ?? { width: 1920, height: 1080 });
        for (const s of data.zones?.shelf_zones ?? []) {
          loaded.push({ id: uid(), label: s.label, bbox: s.bbox, type: 'shelf' });
        }
        for (const q of data.zones?.queue_zones ?? []) {
          loaded.push({ id: uid(), label: q.label, bbox: q.bbox, type: 'queue', maxQueue: q.max_queue });
        }
        for (const r of data.zones?.restricted_zones ?? []) {
          // Backend may store rectangle as 4-point polygon; convert to bbox if needed
          let bbox: [number, number, number, number];
          if (r.bbox) {
            bbox = r.bbox;
          } else if (r.polygon?.length === 4) {
            const xs = r.polygon.map((p: [number, number]) => p[0]);
            const ys = r.polygon.map((p: [number, number]) => p[1]);
            bbox = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
          } else {
            continue; // skip malformed
          }
          loaded.push({ id: uid(), label: r.name ?? `Restricted ${uid()}`, bbox, type: 'restricted' });
        }
        setZones(loaded);
      })
      .catch(() => { /* no zones yet — that's fine */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camId]);

  // ── Canvas draw loop ────────────────────────────────────────────────────────

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // Background / image
    if (imgRef.current && snapUrl) {
      ctx.drawImage(imgRef.current, 0, 0, W, H);
    } else {
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(0, 0, W, H);
    }

    // ── Guide overlay (pulsing dashed box) ──────────────────────────────────
    if (mode && !isDrawing && !namePopup) {
      const phase   = guideTick % 10;     // 0-9
      const opacity = 0.4 + 0.4 * Math.sin((phase / 10) * Math.PI * 2);
      const meta    = ZONE_META[mode];

      const gx = W * 0.2;
      const gy = H * 0.25;
      const gw = W * 0.6;
      const gh = H * 0.4;

      ctx.save();
      ctx.globalAlpha = opacity;
      ctx.strokeStyle = meta.hex;
      ctx.lineWidth   = 2.5;
      ctx.setLineDash([10, 6]);
      ctx.strokeRect(gx, gy, gw, gh);
      ctx.setLineDash([]);
      ctx.globalAlpha = opacity * 0.12;
      ctx.fillStyle   = meta.hex;
      ctx.fillRect(gx, gy, gw, gh);
      ctx.restore();

      // Instruction bubble at bottom of canvas
      const bubble = `${meta.guide}`;
      ctx.font        = 'bold 15px system-ui, sans-serif';
      const tw        = ctx.measureText(bubble).width;
      const bx        = (W - tw - 32) / 2;
      const by        = H - 52;
      ctx.fillStyle   = 'rgba(0,0,0,0.72)';
      ctx.beginPath();
      ctx.roundRect(bx, by, tw + 32, 36, 8);
      ctx.fill();
      ctx.fillStyle   = meta.hex;
      ctx.fillText(bubble, bx + 16, by + 24);
    }

    // ── Saved zones ─────────────────────────────────────────────────────────
    for (const zone of zones) {
      const [cx1, cy1] = toCanvasCoords(zone.bbox[0], zone.bbox[1], W, H, camRes.width, camRes.height);
      const [cx2, cy2] = toCanvasCoords(zone.bbox[2], zone.bbox[3], W, H, camRes.width, camRes.height);
      const hex        = ZONE_META[zone.type].hex;
      const highlighted = hoveredId === zone.id;

      ctx.save();
      ctx.strokeStyle = hex;
      ctx.lineWidth   = highlighted ? 3 : 2;
      ctx.strokeRect(cx1, cy1, cx2 - cx1, cy2 - cy1);
      ctx.fillStyle   = `${hex}${highlighted ? '40' : '22'}`;
      ctx.fillRect(cx1, cy1, cx2 - cx1, cy2 - cy1);

      // Label inside
      ctx.fillStyle   = hex;
      ctx.font        = 'bold 12px system-ui, sans-serif';
      ctx.fillText(zone.label, cx1 + 6, cy1 + 18);
      ctx.restore();
    }

    // ── Live drag rectangle ─────────────────────────────────────────────────
    if (isDrawing && currentRect && mode) {
      const hex = ZONE_META[mode].hex;
      ctx.save();
      ctx.strokeStyle = hex;
      ctx.lineWidth   = 2.5;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(currentRect.x, currentRect.y, currentRect.w, currentRect.h);
      ctx.setLineDash([]);
      ctx.fillStyle   = `${hex}33`;
      ctx.fillRect(currentRect.x, currentRect.y, currentRect.w, currentRect.h);

      // Zone type label while drawing
      ctx.fillStyle   = hex;
      ctx.font        = 'bold 13px system-ui, sans-serif';
      ctx.fillText(ZONE_META[mode].label, currentRect.x + 6, currentRect.y + 20);
      ctx.restore();
    }
  }, [zones, currentRect, isDrawing, mode, snapUrl, camRes, hoveredId, namePopup, guideTick]);

  useEffect(() => { draw(); }, [draw]);

  useEffect(() => {
    if (!snapUrl) return;
    const img  = new Image();
    img.onload = () => { imgRef.current = img; draw(); };
    img.src    = snapUrl;
  }, [snapUrl, draw]);

  // Focus name input when popup appears
  useEffect(() => {
    if (namePopup) {
      setNameValue(namePopup.defaultLabel);
      setTimeout(() => nameInputRef.current?.focus(), 50);
    }
  }, [namePopup]);

  // ── Ctrl+Z undo ────────────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        setZones((z) => z.slice(0, -1));
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // ── Canvas event handlers ─────────────────────────────────────────────────

  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!mode || namePopup) return;
    const pos = getPos(e);
    setIsDrawing(true);
    setDragStart(pos);
    setCurrentRect({ x: pos.x, y: pos.y, w: 0, h: 0 });
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || !dragStart) return;
    const pos = getPos(e);
    setCurrentRect({
      x: Math.min(dragStart.x, pos.x),
      y: Math.min(dragStart.y, pos.y),
      w: Math.abs(pos.x - dragStart.x),
      h: Math.abs(pos.y - dragStart.y),
    });
  };

  const onMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || !currentRect || !mode) return;
    setIsDrawing(false);
    const { x, y, w, h } = currentRect;
    if (w < 12 || h < 12) { setCurrentRect(null); return; }

    // Position the inline popup at center of drawn rect
    const popupX = x + w / 2;
    const popupY = y + h / 2;
    const zoneCount = zones.filter((z) => z.type === mode).length + 1;
    const defaultLabel =
      mode === 'shelf'      ? `Shelf ${zoneCount}` :
      mode === 'restricted' ? `Restricted ${zoneCount}` :
                              `Queue Lane ${zoneCount}`;

    setNamePopup({ canvasX: popupX, canvasY: popupY, rect: currentRect, defaultLabel });
    void e;
  };

  // ── Confirm zone name ─────────────────────────────────────────────────────

  const confirmZone = () => {
    if (!namePopup || !mode) return;
    const label = nameValue.trim() || namePopup.defaultLabel;
    const canvas = canvasRef.current!;
    const { x, y, w, h } = namePopup.rect;

    const [x1, y1] = toImageCoords(x,     y,     canvas.width, canvas.height, camRes.width, camRes.height);
    const [x2, y2] = toImageCoords(x + w, y + h, canvas.width, canvas.height, camRes.width, camRes.height);

    const newZone: Zone = {
      id: uid(), label, type: mode, bbox: [x1, y1, x2, y2],
      ...(mode === 'queue' ? { maxQueue: 5 } : {}),
    };
    setZones((z) => [...z, newZone]);
    setNamePopup(null);
    setCurrentRect(null);
    setDragStart(null);
  };

  const cancelZone = () => {
    setNamePopup(null);
    setCurrentRect(null);
    setDragStart(null);
  };

  const onNameKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') confirmZone();
    if (e.key === 'Escape') cancelZone();
  };

  // ── Save zones ────────────────────────────────────────────────────────────

  const saveZones = async () => {
    setSaving(true);
    try {
      const body = {
        shelf_zones: zones
          .filter((z) => z.type === 'shelf')
          .map((z) => ({ label: z.label, bbox: z.bbox, zone_type: 'shelf' })),
        queue_zones: zones
          .filter((z) => z.type === 'queue')
          .map((z) => ({ label: z.label, bbox: z.bbox, zone_type: 'queue', max_queue: z.maxQueue ?? 5 })),
        restricted_zones: zones
          .filter((z) => z.type === 'restricted')
          .map((z) => {
            // Store as 4-corner polygon (backend accepts both formats)
            const [x1, y1, x2, y2] = z.bbox;
            return { name: z.label, polygon: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]], severity: 'critical' };
          }),
      };
      await api.put(`/zones/cameras/${camId}`, body);
      toast.success('Zones saved! AI pipeline reloads within 5 seconds.');
    } catch {
      toast.error('Failed to save zones.');
    } finally {
      setSaving(false);
    }
  };

  // ── Test a zone ───────────────────────────────────────────────────────────

  const testZone = async (zone: Zone) => {
    setTesting(zone.id);
    try {
      const eventType =
        zone.type === 'restricted' ? 'restricted_zone' :
        zone.type === 'queue'      ? 'queue_breach'     : 'inventory_movement';

      // Capture the canvas as evidence only when camera image is actually loaded.
      // If imgRef.current is null (snapshot not yet loaded), sending a blank black
      // JPEG is misleading — skip capture instead so backend stores no snapshot.
      const snapshotB64 = (imgRef.current && snapUrl)
        ? canvasRef.current?.toDataURL('image/jpeg', 0.80) ?? ''
        : '';

      await api.post('/demo/trigger', {
        event_type:   eventType,
        camera_id:    camId,
        severity:     zone.type === 'restricted' ? 'critical' : 'medium',
        zone_name:    zone.label,
        zone_label:   ZONE_META[zone.type].label,
        zone_bbox:    zone.bbox,
        snapshot_b64: snapshotB64,
      });
      toast.success(`Test event fired for "${zone.label}" — check Incidents page`);
    } catch {
      toast.error('Test failed');
    } finally {
      setTesting(null);
    }
  };

  const deleteZone = (id: string) => setZones((z) => z.filter((zz) => zz.id !== id));

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-vantag-bg text-slate-100 p-4 lg:p-6 space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Zone Editor</h1>
        <p className="text-slate-400 text-sm mt-1">
          Mark your shelves, restricted areas, and checkout queues — then the AI knows exactly where to watch.
        </p>
      </div>

      {/* ── Step 1: Zone type cards ───────────────────────────────────────── */}
      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-300">
          Step 1 — What do you want to mark on the camera?
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {(Object.entries(ZONE_META) as [ZoneType, typeof ZONE_META['shelf']][]).map(([type, meta]) => {
            const selected = mode === type;
            return (
              <button
                key={type}
                onClick={() => setMode(selected ? null : type)}
                className={clsx(
                  'relative text-left rounded-2xl border-2 p-5 transition-all duration-200',
                  selected
                    ? 'shadow-lg scale-[1.02]'
                    : 'border-slate-700 bg-vantag-card opacity-75 hover:opacity-100 hover:border-slate-500'
                )}
                style={selected ? {
                  borderColor: meta.hex,
                  background:  `${meta.hex}18`,
                  boxShadow:   `0 0 0 3px ${meta.hex}33`,
                } : {}}
              >
                {selected && (
                  <span
                    className="absolute top-3 right-3 text-xs font-bold px-2 py-0.5 rounded-full"
                    style={{ background: meta.hex, color: '#fff' }}
                  >
                    Selected
                  </span>
                )}
                <div className="text-3xl mb-2">{meta.emoji}</div>
                <div className="font-bold text-base text-slate-100 mb-0.5">{meta.label}</div>
                <div className="text-xs font-semibold mb-2" style={{ color: meta.hex }}>{meta.tagline}</div>
                <div className="text-xs text-slate-400 leading-relaxed">{meta.desc}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Step 2: Camera + canvas ──────────────────────────────────────── */}
      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-300">
          Step 2 — {mode
            ? `Drag a ${ZONE_META[mode].label} box on the camera image below`
            : 'Select a zone type above, then drag on the camera image'}
        </p>

        {/* Camera picker + snapshot */}
        <div className="flex flex-wrap gap-3 items-center">
          <select
            value={camId}
            onChange={(e) => setCamId(e.target.value)}
            className="bg-vantag-card border border-slate-600 rounded-lg px-3 py-2 text-slate-200 text-sm"
          >
            {CAMERAS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <button
            onClick={refreshSnapshot}
            disabled={snapLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-vantag-card border border-slate-600 text-slate-300 hover:border-slate-400 text-sm transition-colors disabled:opacity-50"
          >
            {snapLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Refresh Snapshot
          </button>
          {zones.length > 0 && (
            <button
              onClick={() => setZones((z) => z.slice(0, -1))}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 text-sm"
              title="Undo last zone (Ctrl+Z)"
            >
              <Undo2 size={14} /> Undo
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

          {/* Canvas area */}
          <div className="xl:col-span-2">
            <div className="relative rounded-xl overflow-hidden border border-slate-700/60 bg-slate-900">
              {/* No snapshot placeholder */}
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
                width={960}
                height={540}
                className={clsx(
                  'w-full block',
                  mode && !namePopup ? 'cursor-crosshair' : 'cursor-default'
                )}
                onMouseDown={onMouseDown}
                onMouseMove={onMouseMove}
                onMouseUp={onMouseUp}
              />

              {/* Inline name popup */}
              {namePopup && mode && (() => {
                const canvas = canvasRef.current;
                if (!canvas) return null;
                const rect   = canvas.getBoundingClientRect();
                const scaleX = rect.width  / canvas.width;
                const scaleY = rect.height / canvas.height;
                const px = namePopup.canvasX * scaleX;
                const py = namePopup.canvasY * scaleY;
                const meta = ZONE_META[mode];
                return (
                  <div
                    className="absolute z-20 transform -translate-x-1/2 -translate-y-1/2"
                    style={{ left: px, top: py }}
                  >
                    <div
                      className="rounded-xl shadow-2xl p-4 space-y-3 min-w-[240px]"
                      style={{
                        background:  '#1e293b',
                        border:      `2px solid ${meta.hex}`,
                        boxShadow:   `0 0 24px ${meta.hex}44`,
                      }}
                    >
                      <p className="text-xs font-semibold" style={{ color: meta.hex }}>
                        {meta.emoji} Name this {meta.label}
                      </p>
                      <input
                        ref={nameInputRef}
                        value={nameValue}
                        onChange={(e) => setNameValue(e.target.value)}
                        onKeyDown={onNameKeyDown}
                        placeholder={namePopup.defaultLabel}
                        className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2"
                        style={{ '--tw-ring-color': meta.hex } as React.CSSProperties}
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={confirmZone}
                          className="flex-1 py-2 rounded-lg text-sm font-semibold text-white transition-colors"
                          style={{ background: meta.hex }}
                        >
                          Add Zone
                        </button>
                        <button
                          onClick={cancelZone}
                          className="px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 border border-slate-600"
                        >
                          Cancel
                        </button>
                      </div>
                      <p className="text-[11px] text-slate-500">Press Enter to confirm, Esc to cancel</p>
                    </div>
                  </div>
                );
              })()}
            </div>

            {/* Save button */}
            <div className="flex justify-between items-center mt-3">
              <p className="text-xs text-slate-500">
                {zones.length === 0
                  ? 'No zones yet — draw some on the image above'
                  : `${zones.length} zone${zones.length !== 1 ? 's' : ''} ready to save`}
              </p>
              <button
                onClick={saveZones}
                disabled={saving || zones.length === 0}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-vantag-red hover:bg-red-600 text-white font-semibold text-sm transition-colors disabled:opacity-50 shadow-lg shadow-red-900/30"
              >
                {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                {saving ? 'Saving…' : 'Save All Zones'}
              </button>
            </div>
          </div>

          {/* Zone list sidebar */}
          <div className="space-y-3">
            <h3 className="font-semibold text-slate-300 text-sm">
              Step 3 — Zones Defined ({zones.length})
            </h3>

            {zones.length === 0 ? (
              <div className="rounded-xl border border-slate-700/60 p-6 text-center text-slate-500 text-sm">
                <AlertCircle size={24} className="mx-auto mb-2 opacity-40" />
                No zones yet.
                <br />Select a zone type and drag on the image.
              </div>
            ) : (
              <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
                {zones.map((zone) => {
                  const meta = ZONE_META[zone.type];
                  return (
                    <div
                      key={zone.id}
                      className={clsx(
                        'rounded-xl border p-3 space-y-2 transition-all cursor-pointer',
                        hoveredId === zone.id
                          ? 'border-opacity-100 bg-slate-800'
                          : 'border-slate-700/60 bg-vantag-card'
                      )}
                      style={hoveredId === zone.id ? { borderColor: meta.hex } : {}}
                      onMouseEnter={() => setHoveredId(zone.id)}
                      onMouseLeave={() => setHoveredId(null)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span
                            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                            style={{ background: meta.hex }}
                          />
                          <span className="text-sm font-medium text-slate-200 truncate">{zone.label}</span>
                        </div>
                        <span
                          className="text-[10px] font-bold px-2 py-0.5 rounded-full flex-shrink-0"
                          style={{ background: `${meta.hex}22`, color: meta.hex, border: `1px solid ${meta.hex}44` }}
                        >
                          {meta.label}
                        </span>
                      </div>

                      <p className="text-[10px] text-slate-600 font-mono">
                        [{zone.bbox.join(', ')}]
                      </p>

                      <div className="flex gap-2">
                        <button
                          onClick={() => testZone(zone)}
                          disabled={testing === zone.id}
                          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs hover:bg-blue-500/20 transition-colors disabled:opacity-50"
                        >
                          {testing === zone.id
                            ? <Loader2 size={11} className="animate-spin" />
                            : <CheckCircle size={11} />}
                          Test Event
                        </button>
                        <button
                          onClick={() => deleteZone(zone.id)}
                          className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs hover:bg-red-500/20 transition-colors"
                          title="Delete zone"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Legend */}
            <div className="rounded-xl border border-slate-700/60 bg-vantag-card p-4 space-y-2.5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Zone Legend</p>
              {(Object.entries(ZONE_META) as [ZoneType, typeof ZONE_META['shelf']][]).map(([type, meta]) => (
                <div key={type} className="flex items-start gap-2.5 text-xs text-slate-400">
                  <span className="w-3 h-3 rounded-sm flex-shrink-0 mt-0.5" style={{ background: meta.hex }} />
                  <div>
                    <span className="font-semibold" style={{ color: meta.hex }}>{meta.label}</span>
                    <span className="ml-1">— {meta.desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
