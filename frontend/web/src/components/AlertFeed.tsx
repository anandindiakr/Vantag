import { useEffect, useRef } from 'react';
import {
  Shield,
  Clock,
  Package,
  User,
  AlertCircle,
  DoorOpen,
  Users,
  Crosshair,
  ShoppingCart,
  Cpu,
} from 'lucide-react';
import clsx from 'clsx';
import { useVantagStore, VantagEvent, EventType, Severity } from '../store/useVantagStore';

function eventIcon(type: EventType) {
  const cls = 'shrink-0';
  switch (type) {
    case 'sweep':           return <Shield size={14} className={cls} />;
    case 'dwell':           return <Clock size={14} className={cls} />;
    case 'empty_shelf':     return <Package size={14} className={cls} />;
    case 'watchlist_match': return <User size={14} className={cls} />;
    case 'queue_alert':     return <ShoppingCart size={14} className={cls} />;
    case 'door_event':      return <DoorOpen size={14} className={cls} />;
    case 'loitering':       return <Users size={14} className={cls} />;
    case 'crowd':           return <Users size={14} className={cls} />;
    case 'theft_attempt':   return <Crosshair size={14} className={cls} />;
    default:                return <Cpu size={14} className={cls} />;
  }
}

function eventIconColor(type: EventType): string {
  switch (type) {
    case 'sweep':
    case 'theft_attempt':   return 'text-vantag-red';
    case 'dwell':
    case 'loitering':
    case 'crowd':           return 'text-vantag-amber';
    case 'empty_shelf':     return 'text-slate-400';
    case 'watchlist_match': return 'text-vantag-red';
    case 'queue_alert':     return 'text-vantag-amber';
    case 'door_event':      return 'text-blue-400';
    default:                return 'text-slate-500';
  }
}

function severityBadge(s: Severity) {
  switch (s) {
    case 'CRITICAL':
    case 'HIGH':   return 'bg-vantag-red/20 text-vantag-red';
    case 'MEDIUM': return 'bg-vantag-amber/20 text-vantag-amber';
    default:       return 'bg-slate-700/50 text-slate-400';
  }
}

function relativeTime(iso: string): string {
  const diffMs  = Date.now() - new Date(iso).getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60)  return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  return `${Math.floor(diffSec / 3600)}h ago`;
}

interface AlertFeedProps {
  /** Filter to a specific store. If omitted, shows all stores. */
  storeId?: string;
  maxItems?: number;
  className?: string;
}

export default function AlertFeed({ storeId, maxItems = 50, className }: AlertFeedProps) {
  const allEvents  = useVantagStore((s) => s.recentEvents);
  const listRef    = useRef<HTMLDivElement>(null);

  const events: VantagEvent[] = (
    storeId ? allEvents.filter((e) => e.storeId === storeId) : allEvents
  ).slice(0, maxItems);

  // Auto-scroll to top when new event arrives
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [events[0]?.id]);

  return (
    <div
      className={clsx(
        'flex flex-col bg-vantag-card border border-slate-700/60 rounded-xl overflow-hidden',
        className
      )}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
        <div className="flex items-center gap-2">
          <AlertCircle size={15} className="text-vantag-red" />
          <span className="text-sm font-semibold text-slate-100">Live Event Feed</span>
        </div>
        <span className="text-xs text-slate-500">{events.length} events</span>
      </div>

      <div
        ref={listRef}
        className="flex-1 overflow-y-auto scrollbar-thin divide-y divide-slate-700/40"
        style={{ maxHeight: '480px' }}
      >
        {events.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-sm text-slate-500">
            No events yet
          </div>
        ) : (
          events.map((event, idx) => (
            <div
              key={event.id}
              className={clsx(
                'flex items-start gap-3 px-4 py-3 transition-colors hover:bg-slate-700/20 animate-fade-in',
                idx === 0 && 'bg-slate-700/10'
              )}
            >
              {/* Icon */}
              <div
                className={clsx(
                  'mt-0.5 w-6 h-6 flex items-center justify-center rounded-full bg-slate-800 shrink-0',
                  eventIconColor(event.type)
                )}
              >
                {eventIcon(event.type)}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-medium text-slate-200 truncate">
                    {event.description}
                  </span>
                  <span
                    className={clsx(
                      'shrink-0 text-xs font-semibold px-1.5 py-0.5 rounded',
                      severityBadge(event.severity)
                    )}
                  >
                    {event.severity}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
                  <span className="truncate">{event.cameraName}</span>
                  <span>·</span>
                  <span className="shrink-0">{relativeTime(event.ts)}</span>
                  {event.confidence > 0 && (
                    <>
                      <span>·</span>
                      <span className="shrink-0">{Math.round(event.confidence * 100)}% conf.</span>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
