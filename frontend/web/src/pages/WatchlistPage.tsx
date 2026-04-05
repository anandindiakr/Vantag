import { useState, useRef } from 'react';
import {
  Users,
  Plus,
  Trash2,
  Upload,
  X,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Search,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import {
  useWatchlist,
  useWatchlistMatches,
  useAddWatchlistEntry,
  useDeleteWatchlistEntry,
} from '../hooks/useApi';
import { Severity, WatchlistEntry } from '../store/useVantagStore';

const ALERT_LEVELS: Severity[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

function alertBadge(level: Severity) {
  return clsx(
    'text-xs font-semibold px-2 py-0.5 rounded border',
    level === 'CRITICAL' || level === 'HIGH'
      ? 'bg-vantag-red/15 text-vantag-red border-vantag-red/30'
      : level === 'MEDIUM'
      ? 'bg-vantag-amber/15 text-vantag-amber border-vantag-amber/30'
      : 'bg-vantag-green/15 text-vantag-green border-vantag-green/30'
  );
}

interface AddPersonModalProps {
  onClose: () => void;
}

function AddPersonModal({ onClose }: AddPersonModalProps) {
  const [name, setName]           = useState('');
  const [alertLevel, setAlertLevel] = useState<Severity>('MEDIUM');
  const [notes, setNotes]         = useState('');
  const [file, setFile]           = useState<File | null>(null);
  const [preview, setPreview]     = useState<string | null>(null);
  const fileRef                   = useRef<HTMLInputElement>(null);

  const { mutateAsync, isPending } = useAddWatchlistEntry();

  const handleFile = (f: File | null) => {
    setFile(f);
    if (f) {
      const url = URL.createObjectURL(f);
      setPreview(url);
    } else {
      setPreview(null);
    }
  };

  const handleSubmit = async () => {
    if (!name.trim()) { toast.error('Name is required'); return; }
    if (!file)        { toast.error('Face image is required'); return; }
    try {
      await mutateAsync({ name, alertLevel, notes, faceImage: file });
      toast.success(`${name} added to watchlist`);
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
          <h2 className="text-base font-semibold text-slate-100">Add to Watchlist</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
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
                <p className="text-sm text-slate-400">Click to upload face image</p>
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
            <label className="block text-xs font-medium text-slate-400 mb-1">Full Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="John Doe"
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-slate-400"
            />
          </div>

          {/* Alert level */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Alert Level *</label>
            <div className="flex gap-2">
              {ALERT_LEVELS.map((level) => (
                <button
                  key={level}
                  onClick={() => setAlertLevel(level)}
                  className={clsx(
                    'flex-1 py-1.5 rounded-lg text-xs font-semibold border transition-colors',
                    alertLevel === level
                      ? alertBadge(level)
                      : 'border-slate-600 text-slate-500 hover:text-slate-300'
                  )}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Optional notes about this person..."
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
            className="flex items-center gap-2 px-5 py-2 bg-vantag-red hover:bg-red-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-60"
          >
            {isPending && <Loader2 size={14} className="animate-spin" />}
            Add Person
          </button>
        </div>
      </div>
    </div>
  );
}

export default function WatchlistPage() {
  const [showAddModal, setShowAddModal] = useState(false);
  const [search, setSearch]            = useState('');

  const { data: watchlist = [], isLoading }    = useWatchlist();
  const { data: matches = [] }                 = useWatchlistMatches();
  const { mutateAsync: deleteEntry, isPending: deleting } = useDeleteWatchlistEntry();

  const filtered = watchlist.filter((e) =>
    e.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = async (entry: WatchlistEntry) => {
    if (!confirm(`Remove "${entry.name}" from watchlist?`)) return;
    try {
      await deleteEntry(entry.id);
      toast.success(`${entry.name} removed from watchlist`);
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
            <Users size={22} className="text-vantag-red" />
            <div>
              <h1 className="text-xl font-bold text-slate-100">Watchlist</h1>
              <p className="text-xs text-slate-400">{watchlist.length} registered persons</p>
            </div>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-vantag-red hover:bg-red-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Plus size={16} /> Add Person
          </button>
        </div>
      </header>

      <div className="px-6 py-6 space-y-6">
        {/* ── Watchlist Table ────────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex-1 max-w-xs">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name…"
                className="w-full bg-vantag-card border border-slate-700/60 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-slate-400"
              />
            </div>
          </div>

          <div className="bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-12 px-4 py-3 border-b border-slate-700/60 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              <div className="col-span-1" />
              <div className="col-span-4">Name</div>
              <div className="col-span-2">Alert Level</div>
              <div className="col-span-2">Match Count</div>
              <div className="col-span-2">Added</div>
              <div className="col-span-1" />
            </div>

            {/* Rows */}
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={24} className="animate-spin text-slate-500" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="flex items-center justify-center py-12 gap-2 text-slate-500 text-sm">
                <Users size={18} />
                {search ? 'No matching entries' : 'Watchlist is empty'}
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
                          <Users size={14} className="text-slate-500" />
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

                    {/* Alert level */}
                    <div className="col-span-2">
                      <span className={alertBadge(entry.alertLevel)}>{entry.alertLevel}</span>
                    </div>

                    {/* Match count */}
                    <div className="col-span-2">
                      <span className="text-sm text-slate-300 font-medium">{entry.matchCount}</span>
                      <span className="text-xs text-slate-500 ml-1">matches</span>
                    </div>

                    {/* Added at */}
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
                        title="Remove"
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

        {/* ── Recent Matches ─────────────────────────────────────── */}
        <section>
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <AlertTriangle size={14} className="text-vantag-amber" /> Recent Matches
          </h2>
          <div className="bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden">
            {matches.length === 0 ? (
              <div className="flex items-center justify-center py-10 gap-2 text-slate-500 text-sm">
                <CheckCircle2 size={16} className="text-vantag-green" />
                No recent matches
              </div>
            ) : (
              <div className="divide-y divide-slate-700/40">
                {matches.slice(0, 20).map((match) => (
                  <div key={match.id} className="flex items-center gap-4 px-4 py-3 hover:bg-slate-700/10 transition-colors">
                    {/* Thumbnail */}
                    <div className="w-10 h-10 rounded-lg bg-slate-800 overflow-hidden shrink-0">
                      {match.thumbnailUrl ? (
                        <img src={match.thumbnailUrl} alt="Match thumbnail" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <Users size={14} className="text-slate-500" />
                        </div>
                      )}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-100">{match.entryName}</span>
                        <span
                          className={clsx(
                            'text-xs px-1.5 py-0.5 rounded font-bold',
                            match.confidence > 0.85
                              ? 'bg-vantag-red/20 text-vantag-red'
                              : match.confidence > 0.70
                              ? 'bg-vantag-amber/20 text-vantag-amber'
                              : 'bg-slate-700/50 text-slate-400'
                          )}
                        >
                          {Math.round(match.confidence * 100)}%
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5 truncate">
                        {match.cameraName} · {new Date(match.ts).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Add Person Modal */}
      {showAddModal && <AddPersonModal onClose={() => setShowAddModal(false)} />}
    </div>
  );
}
