import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  AlertTriangle,
  Users,
  Camera,
  LogOut,
  ShieldCheck,
  Wifi,
  WifiOff,
  Radio,
  Zap,
  PenTool,
  Download,
  HelpCircle,
  Settings2,
  HeartPulse,
  ShieldAlert,
} from 'lucide-react';
import clsx from 'clsx';
import { useVantagStore } from '../store/useVantagStore';
import { useRegion } from '../hooks/useRegion';
import { LanguageSelector } from './LanguageSelector';
import { useEffect } from 'react';

interface NavItem {
  label: string;
  to: string;
  icon: React.ReactNode;
  dividerBefore?: boolean;
}

const navItems: NavItem[] = [
  { label: 'Dashboard',    to: '/dashboard',    icon: <LayoutDashboard size={20} /> },
  { label: 'Cameras',      to: '/cameras',      icon: <Camera size={20} /> },
  { label: 'Manage Cameras', to: '/cameras/manage', icon: <Settings2 size={20} /> },
  { label: 'Incidents',    to: '/incidents',    icon: <AlertTriangle size={20} /> },
  { label: 'Watchlist',    to: '/watchlist',    icon: <Users size={20} /> },
  { label: 'Zone Editor',  to: '/zone-editor',  icon: <PenTool size={20} />, dividerBefore: true },
  { label: 'Demo Center',  to: '/demo',         icon: <Zap size={20} /> },
  { label: 'Health Check', to: '/health-check', icon: <HeartPulse size={20} />, dividerBefore: true },
  { label: 'Install Edge Agent', to: '/download', icon: <Download size={20} />, dividerBefore: true },
  { label: 'Help & Support', to: '/help', icon: <HelpCircle size={20} /> },
];

export default function Sidebar() {
  const navigate      = useNavigate();
  const region        = useRegion();
  const wsConnected   = useVantagStore((s) => s.wsConnected);
  const mqttConnected = useVantagStore((s) => s.mqttConnected);
  const stores        = useVantagStore((s) => s.stores);
  const isSuperAdmin  = useVantagStore((s) => s.isSuperAdmin);
  const setIsSuperAdmin = useVantagStore((s) => s.setIsSuperAdmin);
  const activeCount   = stores.filter((s) => s.active).length;

  // Restore super-admin from localStorage on mount (page refresh)
  useEffect(() => {
    if (localStorage.getItem('vantag_is_super_admin') === 'true') {
      setIsSuperAdmin(true);
    }
  }, [setIsSuperAdmin]);

  const handleLogout = () => {
    localStorage.removeItem('vantag_token');
    localStorage.removeItem('vantag_tenant');
    localStorage.removeItem('vantag_is_super_admin');
    navigate('/');
  };

  return (
    <aside className="flex flex-col w-64 min-h-screen bg-vantag-card border-r border-slate-700/60 flex-shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-700/60">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-vantag-red/20 ring-1 ring-vantag-red/50">
          <ShieldCheck size={20} className="text-vantag-red" />
        </div>
        <div className="flex-1 min-w-0">
          <span className="text-base font-bold tracking-tight text-slate-100 truncate block">{region.brandShort}</span>
          <p className="text-xs text-slate-400 leading-none">Retail Intelligence</p>
        </div>
        <LanguageSelector variant="dark" />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <div key={item.to}>
            {item.dividerBefore && (
              <div className="my-2 border-t border-slate-700/60" />
            )}
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150',
                  isActive
                    ? 'bg-vantag-red/15 text-vantag-red ring-1 ring-vantag-red/30'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-700/50'
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          </div>
        ))}

        {/* Admin Panel link — only for super-admins */}
        {isSuperAdmin && (
          <>
            <div className="my-2 border-t border-slate-700/60" />
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150',
                  isActive
                    ? 'bg-red-900/30 text-red-400 ring-1 ring-red-500/40'
                    : 'text-red-400/70 hover:text-red-400 hover:bg-red-900/20'
                )
              }
            >
              <ShieldAlert size={20} />
              Admin Panel
            </NavLink>
          </>
        )}
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

      {/* Logout + Footer */}
      <div className="px-4 pb-4 space-y-2">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-100 hover:bg-slate-700/50 transition-colors"
        >
          <LogOut size={16} />
          Sign Out
        </button>
        <p className="text-xs text-slate-600 text-center">v2.0.0 · Vantag Platform</p>
      </div>
    </aside>
  );
}
