import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  AlertTriangle,
  Users,
  Settings,
  ShieldCheck,
  Wifi,
  WifiOff,
  Radio,
} from 'lucide-react';
import clsx from 'clsx';
import { useVantagStore } from '../store/useVantagStore';

interface NavItem {
  label: string;
  to: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { label: 'Dashboard',  to: '/',          icon: <LayoutDashboard size={20} /> },
  { label: 'Incidents',  to: '/incidents',  icon: <AlertTriangle size={20} /> },
  { label: 'Watchlist',  to: '/watchlist',  icon: <Users size={20} /> },
  { label: 'Settings',   to: '/settings',   icon: <Settings size={20} /> },
];

export default function Sidebar() {
  const location      = useLocation();
  const wsConnected   = useVantagStore((s) => s.wsConnected);
  const mqttConnected = useVantagStore((s) => s.mqttConnected);
  const stores        = useVantagStore((s) => s.stores);
  const activeCount   = stores.filter((s) => s.active).length;

  return (
    <aside className="flex flex-col w-64 min-h-screen bg-vantag-card border-r border-slate-700/60 flex-shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-700/60">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-vantag-red/20 ring-1 ring-vantag-red/50">
          <ShieldCheck size={20} className="text-vantag-red" />
        </div>
        <div>
          <span className="text-lg font-bold tracking-tight text-slate-100">Vantag</span>
          <p className="text-xs text-slate-400 leading-none">Retail Intelligence</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const isActive =
            item.to === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.to);

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150',
                isActive
                  ? 'bg-vantag-red/15 text-vantag-red ring-1 ring-vantag-red/30'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-700/50'
              )}
            >
              {item.icon}
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {/* Connection Status */}
      <div className="px-4 py-4 border-t border-slate-700/60 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
          Connections
        </p>

        {/* WebSocket */}
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/60">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {wsConnected ? (
              <Wifi size={14} className="text-vantag-green" />
            ) : (
              <WifiOff size={14} className="text-slate-500" />
            )}
            <span>WebSocket</span>
          </div>
          <span
            className={clsx(
              'text-xs font-medium px-1.5 py-0.5 rounded',
              wsConnected
                ? 'text-vantag-green bg-vantag-green/10'
                : 'text-slate-500 bg-slate-700/50'
            )}
          >
            {wsConnected ? 'LIVE' : 'OFF'}
          </span>
        </div>

        {/* MQTT */}
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/60">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Radio size={14} className={mqttConnected ? 'text-vantag-green' : 'text-slate-500'} />
            <span>MQTT</span>
          </div>
          <span
            className={clsx(
              'text-xs font-medium px-1.5 py-0.5 rounded',
              mqttConnected
                ? 'text-vantag-green bg-vantag-green/10'
                : 'text-slate-500 bg-slate-700/50'
            )}
          >
            {mqttConnected ? 'LIVE' : 'OFF'}
          </span>
        </div>

        {/* Active stores indicator */}
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/60">
          <span className="text-xs text-slate-400">Active Stores</span>
          <span className="text-xs font-bold text-slate-100">
            {activeCount} / {stores.length}
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 py-3 border-t border-slate-700/60">
        <p className="text-xs text-slate-600">v2.0.0 · Vantag Platform</p>
      </div>
    </aside>
  );
}
