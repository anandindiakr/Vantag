import { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react';
import { RefreshCw, Save, Trash2, CheckCircle, Loader2, AlertCircle, Undo2, Pencil, X, Check, Users } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { api, useCameras } from '../hooks/useApi';
import InfoTooltip from '../components/InfoTooltip';

// ── Types ─────────────────────────────────────────────────────────────────────

type ZoneType = 'shelf' | 'restricted' | 'queue' | 'people_count' | 'exclusion';

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
  people_count: {
    label:   'People Count Area',
    emoji:   '👥',
    color:   'violet',
    hex:     '#a78bfa',
    tagline: 'PURPLE box',
    desc:    'Count people only inside this area',
    guide:   'Click and drag on the camera image to mark the people-count area',
  },
  exclusion: {
    label:   'Excluded Area',
    emoji:   '⬛',
    color:   'slate',
    hex:     '#64748b',
    tagline: 'GRAY box',
    desc:    'Ignore this area completely — no alerts, no counting',
    guide:   'Click and drag over a sidewalk, mirror, TV or other out-of-scope area to exclude it from ALL detection',
  },
};

// Default name given to a freshly drawn zone, per zone type.
//
// Declared as a Record<ZoneType, string> ON PURPOSE: TypeScript now refuses
// to compile if a new ZoneType is added without a name here. The previous
// implementation was an if/else chain that ended in an *unguarded* fallback
// (`: `People Count ${n}``), so drawing an "Excluded Area" produced a zone
// labelled "People Count 1". It was still correctly SAVED as an exclusion
// zone, but both the zone list and the stored config then claimed the user
// had set up people counting — when in reality that area was excluded from
// ALL detection (including people counting), i.e. the exact opposite.
const ZONE_LABEL_PREFIX: Record<ZoneType, string> = {
  shelf:        'Shelf',
  restricted:   'Restricted',
  queue:        'Queue Lane',
  people_count: 'People Count',
  exclusion:    'Excluded Area',
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
  const [camId,       setCamId]       = useState('');
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

  // Inline rename (edit) state
  const [editingId,   setEditingId]   = useState<string | null>(null);
  const [editValue,   setEditValue]   = useState('');
  const [deletingId,  setDeletingId]  = useState<string | null>(null);

  // Guide animation
  const [guideTick,   setGuideTick]   = useState(0);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef    = useRef<HTMLImageElement | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const snapshotRequestRef = useRef(0);
  const { data: liveCameras = [], isLoading: camsLoading, isError: camsError } = useCameras();
  const cameras = liveCameras.map((camera) => ({
    id: camera.id,
    label: `${camera.id} — ${camera.name}${camera.location ? ` · ${camera.location}` : ''}`,
  }));

  // Pulse animation for guide overlay
  useEffect(() => {
    const id = setInterval(() => setGuideTick((t) => t + 1), 200);
    return () => clearInterval(id);
  }, []);

  // ── Fetch tenant cameras ───────────────────────────────────────────────────

  useEffect(() => {
    if (liveCameras.length === 0) {
      setCamId('');
      return;
    }
    setCamId((current) =>
      current && liveCameras.some((camera) => camera.id === current)
        ? current
        : liveCameras[0].id
    );
  }, [liveCameras]);

  // ── Snapshot ──────────────────────────────────────────────────────────────

  const refreshSnapshot = useCallback(async () => {
    if (!camId) return;
    const requestId = ++snapshotRequestRef.current;
    const requestedCameraId = camId;
    setSnapLoading(true);
    setSnapUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return '';
    });
    imgRef.current = null;
    try {
      const resp = await api.get(`/cameras/${camId}/snapshot?t=${Date.now()}`, {
        responseType: 'blob',
      });
      if (
        requestId === snapshotRequestRef.current &&
        requestedCameraId === camId
      ) {
        setSnapUrl(URL.createObjectURL(resp.data as Blob));
      }
    } catch {
      if (requestId === snapshotRequestRef.current) {
        toast.error('Could not load snapshot. Is the camera online?');
      }
    } finally {
      if (requestId === snapshotRequestRef.current) {
        setSnapLoading(false);
      }
    }
  }, [camId]);

  // Load zones + snapshot on camera change
  useEffect(() => {
    if (!camId) {
      setZones([]);
      setSnapUrl('');
      imgRef.current = null;
      return;
    }
    setZones([]);
    setCamRes({ width: 1920, height: 1080 });
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
        for (const p of data.zones?.people_count_zones ?? []) {
          loaded.push({ id: uid(), label: p.label, bbox: p.bbox, type: 'people_count' });
        }
        for (const e of data.zones?.exclusion_zones ?? []) {
          loaded.push({ id: uid(), label: e.label, bbox: e.bbox, type: 'exclusion' });
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
      .catch((error) => {
        setZones([]);
        const message = error instanceof Error ? error.message : 'Could not load camera zones.';
        toast.error(message);
      });
  }, [camId, refreshSnapshot]);

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

  // Convert a pointer event to canvas-internal coordinates. The canvas is
  // internally 960×540 but rendered stretched (w-full), so we must scale the
  // display-pixel cursor position back into the canvas coordinate system — this
  // is what makes the drawn box track the cursor exactly.
  const getPos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current!;
    const r = canvas.getBoundingClientRect();
    const scaleX = canvas.width / r.width;
    const scaleY = canvas.height / r.height;
    const x = Math.max(0, Math.min(canvas.width, (e.clientX - r.left) * scaleX));
    const y = Math.max(0, Math.min(canvas.height, (e.clientY - r.top) * scaleY));
    return { x, y };
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!mode || namePopup) return;
    e.preventDefault();
    // Capture the pointer so dragging keeps working even if the cursor briefly
    // leaves the canvas, and the release is always delivered here.
    try { canvasRef.current?.setPointerCapture(e.pointerId); } catch { /* noop */ }
    const pos = getPos(e);
    setIsDrawing(true);
    setDragStart(pos);
    setCurrentRect({ x: pos.x, y: pos.y, w: 0, h: 0 });
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isDrawing || !dragStart) return;
    const pos = getPos(e);
    setCurrentRect({
      x: Math.min(dragStart.x, pos.x),
      y: Math.min(dragStart.y, pos.y),
      w: Math.abs(pos.x - dragStart.x),
      h: Math.abs(pos.y - dragStart.y),
    });
  };

  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    try { canvasRef.current?.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    if (!isDrawing || !currentRect || !mode) return;
    setIsDrawing(false);
    const { x, y, w, h } = currentRect;
    if (w < 12 || h < 12) { setCurrentRect(null); return; }

    // Position the inline popup at center of drawn rect
    const popupX = x + w / 2;
    const popupY = y + h / 2;
    const zoneCount = zones.filter((z) => z.type === mode).length + 1;
    const defaultLabel = `${ZONE_LABEL_PREFIX[mode]} ${zoneCount}`;

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

  // Build the API request body from a given zone list (used by save, delete, and rename)
  const buildZonesBody = (list: Zone[]) => ({
    shelf_zones: list
      .filter((z) => z.type === 'shelf')
      .map((z) => ({ label: z.label, bbox: z.bbox, zone_type: 'shelf' })),
    queue_zones: list
      .filter((z) => z.type === 'queue')
      .map((z) => ({ label: z.label, bbox: z.bbox, zone_type: 'queue', max_queue: z.maxQueue ?? 5 })),
    people_count_zones: list
      .filter((z) => z.type === 'people_count')
      .map((z) => ({ label: z.label, bbox: z.bbox, zone_type: 'people_count' })),
    exclusion_zones: list
      .filter((z) => z.type === 'exclusion')
      .map((z) => ({ label: z.label, bbox: z.bbox, zone_type: 'exclusion' })),
    restricted_zones: list
      .filter((z) => z.type === 'restricted')
      .map((z) => {
        // Store as 4-corner polygon (backend accepts both formats)
        const [x1, y1, x2, y2] = z.bbox;
        return { name: z.label, polygon: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]], severity: 'critical' };
      }),
  });

  // Shared persistence helper — PUTs the given zone list to the backend.
  // Returns true on success, false on failure (and surfaces the real error message).
  const persistZones = async (list: Zone[], successMsg?: string): Promise<boolean> => {
    try {
      await api.put(`/zones/cameras/${camId}`, buildZonesBody(list));
      if (successMsg) toast.success(successMsg);
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save zones.';
      toast.error(message);
      return false;
    }
  };

  const saveZones = async () => {
    setSaving(true);
    try {
      await persistZones(zones, 'Zones saved! AI pipeline reloads within 5 seconds.');
    } finally {
      setSaving(false);
    }
  };

  // ── Test a zone ───────────────────────────────────────────────────────────

  const testZone = async (zone: Zone) => {
    setTesting(zone.id);
    try {
      if (zone.type === 'people_count') {
        toast.success(`People counting is configured for "${zone.label}"`);
        return;
      }

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

  const deleteZone = async (id: string) => {
    const previous = zones;
    const next = zones.filter((zz) => zz.id !== id);
    setDeletingId(id);
    setZones(next);
    const ok = await persistZones(next, 'Zone deleted.');
    if (!ok) setZones(previous); // roll back on failure
    setDeletingId(null);
  };

  // ── Rename a zone ─────────────────────────────────────────────────────────

  const startEditZone = (zone: Zone) => {
    setEditingId(zone.id);
    setEditValue(zone.label);
  };

  const cancelEditZone = () => {
    setEditingId(null);
    setEditValue('');
  };

  const confirmEditZone = async (id: string) => {
    const trimmed = editValue.trim();
    if (!trimmed) { cancelEditZone(); return; }
    const previous = zones;
    const next = zones.map((zz) => (zz.id === id ? { ...zz, label: trimmed } : zz));
    setZones(next);
    setEditingId(null);
    setEditValue('');
    const ok = await persistZones(next, 'Zone renamed.');
    if (!ok) setZones(previous); // roll back on failure
  };

  const onEditKeyDown = (e: KeyboardEvent<HTMLInputElement>, id: string) => {
    if (e.key === 'Enter') confirmEditZone(id);
    if (e.key === 'Escape') cancelEditZone();
  };

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
        <p className="text-sm font-semibold text-slate-300 flex items-center gap-1">
          Step 1 — What do you want to mark on the camera?
          <InfoTooltip text="Zones tell the AI where to watch. Mark shelves for inventory tracking, restricted areas for security, and queue lanes for checkout monitoring." />
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
        <p className="text-sm font-semibold text-slate-300 flex items-center gap-1">
          Step 2 — {mode
            ? `Drag a ${ZONE_META[mode].label} box on the camera image below`
            : 'Select a zone type above, then drag on the camera image'}
          <InfoTooltip text="Click and drag on the camera image to draw a zone box. You can draw multiple zones of any type. Changes are saved when you click 'Save All Zones'." />
        </p>

        {/* Camera picker + snapshot */}
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
                  : cameras.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)
            }
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
                  'w-full block touch-none select-none',
                  mode && !namePopup ? 'cursor-crosshair' : 'cursor-default'
                )}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerUp}
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
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <span
                            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                            style={{ background: meta.hex }}
                          />
                          {editingId === zone.id ? (
                            <input
                              autoFocus
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onKeyDown={(e) => onEditKeyDown(e, zone.id)}
                              onClick={(e) => e.stopPropagation()}
                              className="min-w-0 flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-sm text-slate-100 focus:outline-none focus:ring-1"
                              style={{ '--tw-ring-color': meta.hex } as React.CSSProperties}
                            />
                          ) : (
                            <span className="text-sm font-medium text-slate-200 truncate">{zone.label}</span>
                          )}
                        </div>
                        {editingId === zone.id ? (
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <button
                              onClick={() => confirmEditZone(zone.id)}
                              className="p-1 rounded text-green-400 hover:bg-green-500/10"
                              title="Confirm rename (Enter)"
                            >
                              <Check size={13} />
                            </button>
                            <button
                              onClick={cancelEditZone}
                              className="p-1 rounded text-slate-400 hover:bg-slate-700"
                              title="Cancel rename (Esc)"
                            >
                              <X size={13} />
                            </button>
                          </div>
                        ) : (
                          <span
                            className="text-[10px] font-bold px-2 py-0.5 rounded-full flex-shrink-0"
                            style={{ background: `${meta.hex}22`, color: meta.hex, border: `1px solid ${meta.hex}44` }}
                          >
                            {meta.label}
                          </span>
                        )}
                      </div>

                      <p className="text-[10px] text-slate-600 font-mono">
                        [{zone.bbox.join(', ')}]
                      </p>

                      <div className="flex gap-2">
                        <button
                          onClick={() => testZone(zone)}
                          disabled={zone.type === 'exclusion' || testing === zone.id || deletingId === zone.id}
                          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs hover:bg-blue-500/20 transition-colors disabled:opacity-50"
                        >
                          {zone.type === 'people_count'
                            ? <Users size={11} />
                            : testing === zone.id
                            ? <Loader2 size={11} className="animate-spin" />
                            : <CheckCircle size={11} />}
                          {zone.type === 'people_count'
                            ? 'Counting Area'
                            : zone.type === 'exclusion'
                            ? 'Ignored Area'
                            : 'Test Event'}
                        </button>
                        <button
                          onClick={() => startEditZone(zone)}
                          disabled={deletingId === zone.id}
                          className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-500/10 border border-slate-500/30 text-slate-300 text-xs hover:bg-slate-500/20 transition-colors disabled:opacity-50"
                          title="Rename zone"
                        >
                          <Pencil size={11} />
                        </button>
                        <button
                          onClick={() => deleteZone(zone.id)}
                          disabled={deletingId === zone.id}
                          className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs hover:bg-red-500/20 transition-colors disabled:opacity-50"
                          title="Delete zone"
                        >
                          {deletingId === zone.id
                            ? <Loader2 size={11} className="animate-spin" />
                            : <Trash2 size={11} />}
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
