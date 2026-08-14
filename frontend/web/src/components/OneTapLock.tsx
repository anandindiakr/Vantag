import { useState, useCallback } from 'react';
import { Lock, Unlock, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { api } from '../hooks/useApi';
import { useVantagStore, DoorState } from '../store/useVantagStore';

interface OneTapLockProps {
  storeId: string;
  doorId: string;
  doorLabel?: string;
}

export default function OneTapLock({ storeId, doorId, doorLabel }: OneTapLockProps) {
  const [loading, setLoading] = useState(false);

  // Combined key used in the store. Real state arrives via the authenticated
  // WebSocket (door_state messages); we set it optimistically on success.
  const storeKey = `${storeId}:${doorId}`;
  const doorState = useVantagStore((s) => s.doorStates[storeKey] ?? 'unknown') as DoorState;

  const isLocked = doorState === 'locked';
  const isUnlocked = doorState === 'unlocked';
  const isUnknown = doorState === 'unknown';

  const handleToggle = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    try {
      const action = isLocked ? 'unlock' : 'lock';
      // Commands go through the backend REST API (single authority) which
      // publishes the canonical MQTT door command; the physical relay is
      // actuated by the on-site edge agent.
      await api.post(`/doors/${encodeURIComponent(storeId)}/${encodeURIComponent(doorId)}/${action}`, {
        action,
      });
      useVantagStore.getState().setDoorState(storeKey, action === 'lock' ? 'locked' : 'unlocked');
      toast.success(`Door ${doorId} ${action} command sent`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to send door command',
      );
    } finally {
      setLoading(false);
    }
  }, [loading, isLocked, storeId, doorId, storeKey]);

  return (
    <div className="flex flex-col items-center gap-3 bg-vantag-card border border-slate-700/60 rounded-xl p-4 w-36">
      {/* Door label */}
      <p className="text-xs font-medium text-slate-400 text-center truncate w-full">
        {doorLabel ?? doorId}
      </p>

      {/* State badge */}
      <span
        className={clsx(
          'text-xs font-semibold px-2 py-0.5 rounded border',
          isLocked
            ? 'text-vantag-red bg-vantag-red/10 border-vantag-red/30'
            : isUnlocked
            ? 'text-vantag-green bg-vantag-green/10 border-vantag-green/30'
            : 'text-slate-500 bg-slate-700/30 border-slate-600/30'
        )}
      >
        {isUnknown ? 'UNKNOWN' : isLocked ? 'LOCKED' : 'UNLOCKED'}
      </span>

      {/* Toggle button */}
      <button
        onClick={handleToggle}
        disabled={loading || isUnknown}
        className={clsx(
          'relative flex items-center justify-center w-14 h-14 rounded-full border-2 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-vantag-card',
          loading
            ? 'opacity-60 cursor-wait border-slate-600'
            : isLocked
            ? 'border-vantag-red bg-vantag-red/15 hover:bg-vantag-red/25 focus:ring-vantag-red'
            : isUnlocked
            ? 'border-vantag-green bg-vantag-green/15 hover:bg-vantag-green/25 focus:ring-vantag-green'
            : 'border-slate-600 bg-slate-700/30 cursor-not-allowed'
        )}
        aria-label={isLocked ? 'Unlock door' : 'Lock door'}
      >
        {loading ? (
          <Loader2 size={24} className="animate-spin text-slate-400" />
        ) : isLocked ? (
          <Lock size={24} className="text-vantag-red" />
        ) : isUnlocked ? (
          <Unlock size={24} className="text-vantag-green" />
        ) : (
          <Lock size={24} className="text-slate-500" />
        )}
      </button>

      <p className="text-xs text-slate-600 text-center leading-tight">
        {loading ? 'Sending…' : 'Tap to toggle'}
      </p>
    </div>
  );
}
