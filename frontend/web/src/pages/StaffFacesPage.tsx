import { useState, useRef } from 'react';
import {
  UserCheck,
  Plus,
  Trash2,
  Upload,
  X,
  Loader2,
  ShieldCheck,
  Search,
  Info,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  useWatchlist,
  useAddWatchlistEntry,
  useDeleteWatchlistEntry,
} from '../hooks/useApi';
import { WatchlistEntry } from '../store/useVantagStore';

interface AddStaffModalProps {
  onClose: () => void;
}

function AddStaffModal({ onClose }: AddStaffModalProps) {
  const [name, setName]       = useState('');
  const [notes, setNotes]     = useState('');
  const [file, setFile]       = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const fileRef               = useRef<HTMLInputElement>(null);

  const { mutateAsync, isPending } = useAddWatchlistEntry();

  const handleFile = (f: File | null) => {
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const handleSubmit = async () => {
    if (!name.trim()) { toast.error('Staff name is required'); return; }
    if (!file)        { toast.error('A clear face photo is required'); return; }
    try {
      await mutateAsync({ name, alertLevel: 'STAFF', notes, faceImage: file });
      toast.success(`${name} enrolled as staff`);
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-vantag-card border border-slate-700/60 rounded-2xl w-full max-w-md shadow-2xl">
        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/60">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <UserCheck size={17} className="text-vantag-green" /> Enroll Staff Member
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Photo guidance */}
          <div className="flex items-start gap-2 bg-vantag-green/10 border border-vantag-green/25 rounded-lg px-3 py-2.5">
            <Info size={14} className="text-vantag-green mt-0.5 shrink-0" />
            <p className="text-xs text-slate-300 leading-relaxed">
              Use a clear, front-facing photo in good lighting — no mask, cap or sunglasses.
              One face per photo. Enrolled staff are <span className="text-vantag-green font-medium">whitelisted</span>:
              they will not trigger intruder / no-entry / after-hours alerts.
              <br /><br />
              <span className="text-slate-100 font-medium">Ceiling / angled cameras?</span>{' '}
              One photo gives ~70–80% recognition when cameras look down at an angle.
              For 90%+ accuracy, enroll the <span className="font-medium">same person 2–3 times</span> with
              different photos: straight-on, looking slightly down (how the camera sees them), and a
              side/three-quarter view. Use the same name each time — all photos count toward matching.
            </p>
          </div>

          {/* Face image upload */}
          <div
            onClick={() => fileRef.current?.click()}
            className="flex flex-col items-center justify-center w-full h-36 rounded-xl border-2 border-dashed border-slate-600 bg-slate-800/40 cursor-pointer hover:border-slate-400 transition-colors overflow-hidden relative"
          >
            {preview ? (
              <img src={preview} alt="Preview" className="w-full h-full object-cover" />
            ) : (
              <>
                <Upload size={24} className="text-slate-500 mb-2" />
                <p className="text-sm text-slate-400">Click to upload face photo</p>
                <p className="text-xs text-slate-600 mt-1">PNG, JPG up to 5 MB</p>
              </>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Name */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Staff Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ramesh Kumar"
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-slate-400"
            />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Role / Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="e.g. Cashier, morning shift"
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-slate-400 resize-none"
            />
          </div>
        </div>

        {/* Modal footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-700/60">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isPending}
            className="flex items-center gap-2 px-5 py-2 bg-vantag-green hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-60"
          >
            {isPending && <Loader2 size={14} className="animate-spin" />}
            Enroll Staff
          </button>
        </div>
      </div>
    </div>
  );
}

export default function StaffFacesPage() {
  const [showAddModal, setShowAddModal] = useState(false);
  const [search, setSearch]             = useState('');

  const { data: watchlist = [], isLoading } = useWatchlist();
  const { mutateAsync: deleteEntry, isPending: deleting } = useDeleteWatchlistEntry();

  // Staff entries only (whitelist)
  const staff = watchlist.filter((e) => e.alertLevel === 'STAFF');
  const filtered = staff.filter((e) =>
    e.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = async (entry: WatchlistEntry) => {
    if (!confirm(`Remove "${entry.name}" from enrolled staff?`)) return;
    try {
      await deleteEntry(entry.id);
      toast.success(`${entry.name} removed from staff`);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div className="min-h-screen bg-vantag-dark pb-10">
      {/* ── Header ────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-vantag-dark/95 backdrop-blur border-b border-slate-700/60 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <UserCheck size={22} className="text-vantag-green" />
            <div>
              <h1 className="text-xl font-bold text-slate-100">Staff Faces</h1>
              <p className="text-xs text-slate-400">{staff.length} enrolled staff members</p>
            </div>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-vantag-green hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Plus size={16} /> Enroll Staff
          </button>
        </div>
      </header>

      <div className="px-6 py-6 space-y-6">
        {/* ── Explainer ──────────────────────────────────────────── */}
        <div className="flex items-start gap-3 bg-vantag-card border border-slate-700/60 rounded-xl px-4 py-3.5">
          <ShieldCheck size={18} className="text-vantag-green mt-0.5 shrink-0" />
          <p className="text-sm text-slate-300 leading-relaxed">
            Enrolled staff are recognised by the AI and <span className="font-medium text-slate-100">excluded from
            intruder, no-entry-zone and after-hours alerts</span>. Their sightings are still logged for audit,
            but no alarm is raised. Enroll every employee to reduce false alerts.
          </p>
        </div>

        {/* ── Staff Table ────────────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex-1 max-w-xs">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search staff by name…"
                className="w-full bg-vantag-card border border-slate-700/60 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-slate-400"
              />
            </div>
          </div>

          <div className="bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-12 px-4 py-3 border-b border-slate-700/60 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              <div className="col-span-1" />
              <div className="col-span-4">Name</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Recognitions</div>
              <div className="col-span-2">Enrolled</div>
              <div className="col-span-1" />
            </div>

            {/* Rows */}
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={24} className="animate-spin text-slate-500" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 gap-2 text-slate-500 text-sm">
                <UserCheck size={18} />
                {search ? 'No matching staff' : 'No staff enrolled yet — click "Enroll Staff" to add your first employee'}
              </div>
            ) : (
              <div className="divide-y divide-slate-700/40">
                {filtered.map((entry) => (
                  <div
                    key={entry.id}
                    className="grid grid-cols-12 items-center px-4 py-3 hover:bg-slate-700/20 transition-colors animate-fade-in"
                  >
                    {/* Avatar */}
                    <div className="col-span-1">
                      {entry.faceImageUrl ? (
                        <img
                          src={entry.faceImageUrl}
                          alt={entry.name}
                          className="w-8 h-8 rounded-full object-cover border border-slate-600"
                        />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
                          <UserCheck size={14} className="text-slate-500" />
                        </div>
                      )}
                    </div>

                    {/* Name + notes */}
                    <div className="col-span-4 min-w-0">
                      <p className="text-sm font-medium text-slate-100 truncate">{entry.name}</p>
                      {entry.notes && (
                        <p className="text-xs text-slate-500 truncate">{entry.notes}</p>
                      )}
                    </div>

                    {/* Status badge */}
                    <div className="col-span-2">
                      <span className="text-xs font-semibold px-2 py-0.5 rounded border bg-vantag-green/15 text-vantag-green border-vantag-green/30">
                        STAFF ✓
                      </span>
                    </div>

                    {/* Recognition count */}
                    <div className="col-span-2">
                      <span className="text-sm text-slate-300 font-medium">{entry.matchCount}</span>
                      <span className="text-xs text-slate-500 ml-1">sightings</span>
                    </div>

                    {/* Enrolled at */}
                    <div className="col-span-2">
                      <span className="text-xs text-slate-400">
                        {new Date(entry.addedAt).toLocaleDateString()}
                      </span>
                    </div>

                    {/* Delete */}
                    <div className="col-span-1 flex justify-end">
                      <button
                        onClick={() => handleDelete(entry)}
                        disabled={deleting}
                        className="text-slate-500 hover:text-vantag-red transition-colors"
                        title="Remove staff member"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Enroll Staff Modal */}
      {showAddModal && <AddStaffModal onClose={() => setShowAddModal(false)} />}
    </div>
  );
}
