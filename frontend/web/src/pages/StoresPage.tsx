/**
 * Stores (multi-site) management.
 *
 * Before this page existed a "store" was not a real record — it was a slug
 * derived from each camera's free-text location, so a chain could not add a
 * second branch, rename one, or decide which cameras belonged where. This page
 * drives the real `sites` table via /api/stores.
 *
 * Legacy stores (auto-derived from camera location text) are still listed, but
 * shown as read-only with a clear explanation, because there is no row behind
 * them to rename or delete. Assigning their cameras to a real store migrates
 * them.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Store as StoreIcon,
  Plus,
  Trash2,
  Pencil,
  X,
  Loader2,
  Camera as CameraIcon,
  Info,
  Check,
  ArrowRight,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  useStores,
  useCameras,
  useCreateStore,
  useUpdateStore,
  useDeleteStore,
  useAssignCamerasToStore,
  type StoreInput,
} from '../hooks/useApi';
import type { Store } from '../store/useVantagStore';

/* ── helpers ─────────────────────────────────────────────────────────────── */

/**
 * Whether this store is backed by a real `sites` row and can be edited.
 * The backend answers this explicitly via `is_managed` — we do NOT try to
 * guess it from the id shape, because both kinds of store are keyed by slug.
 */
function isRealSite(s: Store): boolean {
  return s.isManaged === true;
}

/* ── Store form modal ────────────────────────────────────────────────────── */

interface StoreModalProps {
  initial?: Partial<StoreInput> & { storeId?: string };
  onClose: () => void;
}

function StoreModal({ initial, onClose }: StoreModalProps) {
  const editing = !!initial?.storeId;
  const [form, setForm] = useState<StoreInput>({
    name:          initial?.name ?? '',
    address:       initial?.address ?? '',
    city:          initial?.city ?? '',
    timezone_name: initial?.timezone_name ?? 'Asia/Kolkata',
    open_time:     initial?.open_time ?? '09:00',
    close_time:    initial?.close_time ?? '21:00',
  });

  const create = useCreateStore();
  const update = useUpdateStore();
  const busy = create.isPending || update.isPending;

  const set = (k: keyof StoreInput, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Store name is required'); return; }
    try {
      if (editing) {
        await update.mutateAsync({ storeId: initial!.storeId!, body: form });
        toast.success('Store updated');
      } else {
        await create.mutateAsync(form);
        toast.success(`"${form.name}" created`);
      }
      onClose();
    } catch (err) {
      toast.error((err as Error).message || 'Could not save store');
    }
  };

  const field = 'w-full bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-vantag-green';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-vantag-card border border-slate-700/60 rounded-2xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/60">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <StoreIcon size={17} className="text-vantag-green" />
            {editing ? 'Edit Store' : 'Add Store'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-5 space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Store name *</label>
            <input className={field} value={form.name} placeholder="Andheri West Branch"
                   onChange={(e) => set('name', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Address</label>
            <input className={field} value={form.address} placeholder="Shop 4, Link Road"
                   onChange={(e) => set('address', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">City</label>
              <input className={field} value={form.city} placeholder="Mumbai"
                     onChange={(e) => set('city', e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Timezone</label>
              <input className={field} value={form.timezone_name}
                     onChange={(e) => set('timezone_name', e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Opens</label>
              <input type="time" className={field} value={form.open_time}
                     onChange={(e) => set('open_time', e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Closes</label>
              <input type="time" className={field} value={form.close_time}
                     onChange={(e) => set('close_time', e.target.value)} />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t border-slate-700/60">
          <button onClick={onClose}
                  className="px-4 py-2 text-sm text-slate-300 hover:text-slate-100">
            Cancel
          </button>
          <button onClick={submit} disabled={busy}
                  className="px-4 py-2 text-sm rounded-lg bg-vantag-green text-slate-900 font-medium disabled:opacity-50 flex items-center gap-2">
            {busy && <Loader2 size={14} className="animate-spin" />}
            {editing ? 'Save' : 'Create Store'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Camera assignment modal ─────────────────────────────────────────────── */

function AssignModal({ store, onClose }: { store: Store; onClose: () => void }) {
  const { data: cameras = [], isLoading } = useCameras();
  const assign = useAssignCamerasToStore();
  const [picked, setPicked] = useState<Set<string>>(
    () => new Set(cameras.filter((c) => c.storeId === store.id).map((c) => c.id)),
  );

  const toggle = (id: string) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });

  const submit = async () => {
    try {
      await assign.mutateAsync({ storeId: store.id, cameraIds: [...picked] });
      toast.success('Cameras assigned');
      onClose();
    } catch (err) {
      toast.error((err as Error).message || 'Could not assign cameras');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-vantag-card border border-slate-700/60 rounded-2xl w-full max-w-lg shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/60">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <CameraIcon size={17} className="text-vantag-green" />
            Cameras in {store.name}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-4 max-h-[55vh] overflow-y-auto space-y-1.5">
          {isLoading && (
            <p className="text-sm text-slate-400 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" /> Loading cameras…
            </p>
          )}
          {!isLoading && cameras.length === 0 && (
            <p className="text-sm text-slate-400">
              No cameras yet. Add cameras first, then assign them here.
            </p>
          )}
          {cameras.map((cam) => {
            const on = picked.has(cam.id);
            return (
              <button key={cam.id} onClick={() => toggle(cam.id)}
                      className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg border text-left transition-colors ${
                        on ? 'bg-vantag-green/10 border-vantag-green/40'
                           : 'bg-slate-800/40 border-slate-700 hover:border-slate-500'}`}>
                <div className="min-w-0">
                  <p className="text-sm text-slate-100 truncate">{cam.name}</p>
                  <p className="text-xs text-slate-500 truncate">{cam.id}</p>
                </div>
                {on && <Check size={16} className="text-vantag-green shrink-0" />}
              </button>
            );
          })}
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t border-slate-700/60">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-300 hover:text-slate-100">
            Cancel
          </button>
          <button onClick={submit} disabled={assign.isPending}
                  className="px-4 py-2 text-sm rounded-lg bg-vantag-green text-slate-900 font-medium disabled:opacity-50 flex items-center gap-2">
            {assign.isPending && <Loader2 size={14} className="animate-spin" />}
            Save assignment
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Page ────────────────────────────────────────────────────────────────── */

export default function StoresPage() {
  const { data: stores = [], isLoading } = useStores();
  const del = useDeleteStore();

  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing]       = useState<Store | null>(null);
  const [assigning, setAssigning]   = useState<Store | null>(null);

  const { real, legacy } = useMemo(() => {
    const r: Store[] = [];
    const l: Store[] = [];
    stores.forEach((s) => (isRealSite(s) ? r : l).push(s));
    return { real: r, legacy: l };
  }, [stores]);

  const remove = async (s: Store) => {
    if (!window.confirm(
      `Delete "${s.name}"?\n\nIts cameras are NOT deleted — they are simply unassigned ` +
      `and go back to being grouped by their location text.`,
    )) return;
    try {
      await del.mutateAsync(s.id);
      toast.success(`"${s.name}" deleted`);
    } catch (err) {
      toast.error((err as Error).message || 'Could not delete store');
    }
  };

  const Card = ({ s, editable }: { s: Store; editable: boolean }) => (
    <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-100 truncate">{s.name}</h3>
          <p className="text-xs text-slate-500 truncate">{s.location || s.address || '—'}</p>
        </div>
        {editable ? (
          <div className="flex items-center gap-1 shrink-0">
            <button onClick={() => setEditing(s)} title="Edit"
                    className="p-1.5 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-700/60">
              <Pencil size={14} />
            </button>
            <button onClick={() => remove(s)} title="Delete"
                    className="p-1.5 rounded-md text-slate-400 hover:text-red-400 hover:bg-slate-700/60">
              <Trash2 size={14} />
            </button>
          </div>
        ) : (
          <span className="shrink-0 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-400">
            auto
          </span>
        )}
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <CameraIcon size={13} /> {s.cameraCount} camera{s.cameraCount === 1 ? '' : 's'}
        </span>
      </div>

      <div className="flex items-center gap-2 pt-1">
        {editable && (
          <button onClick={() => setAssigning(s)}
                  className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:border-slate-500">
            Assign cameras
          </button>
        )}
        <Link to={`/stores/${encodeURIComponent(s.id)}`}
              className="text-xs px-2.5 py-1.5 rounded-lg text-vantag-green hover:underline flex items-center gap-1">
          Analytics <ArrowRight size={12} />
        </Link>
      </div>
    </div>
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center gap-2">
            <StoreIcon size={20} className="text-vantag-green" /> Stores
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Group cameras by branch. Incidents, people count and analytics are reported per store.
          </p>
        </div>
        <button onClick={() => setShowCreate(true)}
                className="px-4 py-2 text-sm rounded-lg bg-vantag-green text-slate-900 font-medium flex items-center gap-2">
          <Plus size={15} /> Add Store
        </button>
      </div>

      {isLoading && (
        <p className="text-sm text-slate-400 flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" /> Loading stores…
        </p>
      )}

      {!isLoading && real.length === 0 && legacy.length === 0 && (
        <div className="bg-vantag-card border border-slate-700/60 rounded-xl p-8 text-center">
          <StoreIcon size={28} className="text-slate-600 mx-auto mb-3" />
          <p className="text-sm text-slate-300">No stores yet.</p>
          <p className="text-xs text-slate-500 mt-1">
            Create your first store, then assign its cameras.
          </p>
        </div>
      )}

      {real.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {real.map((s) => <Card key={s.id} s={s} editable />)}
        </div>
      )}

      {legacy.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-start gap-2 bg-slate-800/40 border border-slate-700/60 rounded-lg px-3 py-2.5">
            <Info size={14} className="text-slate-400 mt-0.5 shrink-0" />
            <p className="text-xs text-slate-400 leading-relaxed">
              These groups were detected automatically from each camera's location text — they are
              not real store records yet, so they can't be renamed or deleted. Create a store above
              and assign these cameras to it to take control of the grouping.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {legacy.map((s) => <Card key={s.id} s={s} editable={false} />)}
          </div>
        </div>
      )}

      {showCreate && <StoreModal onClose={() => setShowCreate(false)} />}
      {editing && (
        <StoreModal
          initial={{
            storeId:       editing.id,
            name:          editing.name,
            address:       editing.address,
            timezone_name: editing.timezone,
            open_time:     editing.openHours?.open,
            close_time:    editing.openHours?.close,
          }}
          onClose={() => setEditing(null)}
        />
      )}
      {assigning && <AssignModal store={assigning} onClose={() => setAssigning(null)} />}
    </div>
  );
}
