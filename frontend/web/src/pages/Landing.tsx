import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion, useInView } from 'framer-motion';
import {
  Shield, Camera, Zap as _Zap, Lock, BarChart3, Bell,
  CheckCircle, ArrowRight, Eye, Cpu, Smartphone,
  Monitor, AlertTriangle as _AlertTriangle, Activity, Users, Package,
  MapPin, Timer, TrendingDown, ChevronRight, Play,
  Wifi, BrainCircuit, ShieldAlert, Flame,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────
   DATA
───────────────────────────────────────────────────────── */

const REGIONS = [
  { code: 'IN', name: 'India',     app: 'Retail Nazar', flag: '🇮🇳', lang: 'hi', currency: '₹' },
  { code: 'SG', name: 'Singapore', app: 'Vantag',       flag: '🇸🇬', lang: 'en', currency: 'S$' },
  { code: 'MY', name: 'Malaysia',  app: 'JagaJaga',     flag: '🇲🇾', lang: 'ms', currency: 'RM' },
];

/* ── 11 AI Feature detectors ── */
const AI_FEATURES = [
  {
    icon: ShieldAlert,
    category: 'SECURITY',
    categoryColor: '#ff3c3c',
    title: 'Shoplifting Detection',
    desc: 'Identifies concealment and product-sweep behaviour in real time. Triggers critical alerts before the shoplifter reaches the exit.',
    badge: 'CRITICAL',
  },
  {
    icon: Package,
    category: 'INVENTORY',
    categoryColor: '#f59e0b',
    title: 'Inventory Movement',
    desc: 'Monitors item counts per shelf zone. Alerts when stock drops suddenly without a staff member present — a key signal of bulk theft.',
    badge: 'HIGH',
  },
  {
    icon: MapPin,
    category: 'SECURITY',
    categoryColor: '#ff3c3c',
    title: 'Restricted Zone Entry',
    desc: 'Define custom polygon zones (back office, staff area). Instant alerts when an unauthorised person enters, with time-based schedules.',
    badge: 'CRITICAL',
  },
  {
    icon: Users,
    category: 'ANALYTICS',
    categoryColor: '#06b6d4',
    title: 'Queue Length Management',
    desc: 'Counts customers in checkout lanes and triggers alerts when queues exceed your limit. Estimates wait time for each zone.',
    badge: 'MEDIUM',
  },
  {
    icon: Activity,
    category: 'SAFETY',
    categoryColor: '#a855f7',
    title: 'Fall Detection',
    desc: 'AI-powered person-down detection using pose estimation and bounding-box analysis. Fires a CRITICAL alert instantly for medical response.',
    badge: 'CRITICAL',
  },
  {
    icon: Camera,
    category: 'SECURITY',
    categoryColor: '#ff3c3c',
    title: 'Camera Tamper Detection',
    desc: 'Detects spray painting, lens blocking, or sudden angle changes. Never be left blind during a theft attempt.',
    badge: 'HIGH',
  },
  {
    icon: Timer,
    category: 'ANALYTICS',
    categoryColor: '#06b6d4',
    title: 'Anomalous Dwell Time',
    desc: 'Flags customers loitering in high-value aisles beyond configurable time thresholds. Separates genuine shoppers from threats.',
    badge: 'MEDIUM',
  },
  {
    icon: TrendingDown,
    category: 'INVENTORY',
    categoryColor: '#f59e0b',
    title: 'Empty Shelf Alerts',
    desc: 'Detects empty shelf zones and notifies staff to restock. Reduce lost sales from out-of-stock situations around the clock.',
    badge: 'LOW',
  },
  {
    icon: Flame,
    category: 'SECURITY',
    categoryColor: '#ff3c3c',
    title: 'Product Sweep',
    desc: 'Tracks a person\'s hand sweeping across 3+ shelf items within seconds — a classic theft behaviour — and alerts immediately.',
    badge: 'CRITICAL',
  },
  {
    icon: BarChart3,
    category: 'ANALYTICS',
    categoryColor: '#06b6d4',
    title: 'Crowd Surge Detection',
    desc: 'Monitors sudden density spikes in any zone. Useful for crowd safety, festival sales, and managing peak-hour bottlenecks.',
    badge: 'HIGH',
  },
  {
    icon: Eye,
    category: 'SECURITY',
    categoryColor: '#ff3c3c',
    title: 'Watchlist Matching',
    desc: 'Match detected faces against your custom watchlist of known shoplifters. Get instant alerts when a flagged individual enters the store.',
    badge: 'CRITICAL',
  },
];

const PLATFORM_FEATURES = [
  { icon: Lock,        title: 'One-Tap Door Lock',      desc: 'Lock any door from your phone via MQTT. Works from anywhere with internet.' },
  { icon: Bell,        title: 'Multi-Channel Alerts',   desc: 'Push, SMS, WhatsApp, Slack, Teams, and webhook alerts the moment an event fires.' },
  { icon: BrainCircuit, title: 'Edge AI Processing',    desc: 'All inference runs locally on your device. No video leaves your premises.' },
  { icon: Wifi,        title: 'Works With Any Camera',  desc: 'Generic IP, Dahua, Hikvision, Reolink — no expensive proprietary hardware.' },
];

const EDGE_OPTIONS = [
  { icon: Smartphone, title: 'Android Phone / Tablet', desc: 'Install on any Android device. No extra hardware for 2–5 cameras.' },
  { icon: Monitor,    title: 'Windows / Mac PC',       desc: 'Run the Edge Agent on any computer already in your shop.' },
  { icon: Cpu,        title: 'Vantag Edge Box',        desc: 'Pre-configured plug-and-play device — connect power and ethernet, done.' },
];

const PLANS = [
  {
    id: 'starter', name: 'Starter', cameras: '2–5', highlight: false,
    priceIN: 2999, priceSG: 49, priceMY: 149,
    features: ['AI Detection Suite (11 models)', 'Real-time Dashboard', 'One-Tap Door Lock', 'Email Alerts', '7-day history', 'Mobile + Web Portal'],
  },
  {
    id: 'growth', name: 'Growth', cameras: '6–15', highlight: true,
    priceIN: 5999, priceSG: 99, priceMY: 299,
    features: ['Everything in Starter', 'Shoplifting + Fall Detection', 'Restricted Zone Polygons', 'Queue Management', 'Slack / Teams Alerts', '30-day history', 'Priority Support'],
  },
  {
    id: 'enterprise', name: 'Enterprise', cameras: '16–30', highlight: false,
    priceIN: 11999, priceSG: 199, priceMY: 599,
    features: ['Everything in Growth', 'Watchlist Matching', 'POS Integration', 'Multi-location', 'Custom Webhooks + API', 'Unlimited history', 'Dedicated Support'],
  },
];

const HOW_IT_WORKS = [
  { step: '01', title: 'Register & Configure', desc: 'Sign up and enter your store details + camera IP addresses in under 5 minutes. Works on mobile.' },
  { step: '02', title: 'AI Auto-Connects', desc: 'Vantag discovers your cameras, tests RTSP streams, and configures the AI analyzer stack automatically.' },
  { step: '03', title: 'Go Live', desc: 'All 11 AI models activate. Your dashboard is live and alerts start flowing — in under 30 minutes total.' },
];

const STATS = [
  { value: '11', label: 'AI Models' },
  { value: '< 30m', label: 'Setup time' },
  { value: '2–30', label: 'Cameras' },
  { value: '3', label: 'Countries' },
];

/* ─────────────────────────────────────────────────────────
   BADGE COMPONENT
───────────────────────────────────────────────────────── */
function SeverityBadge({ level }: { level: string }) {
  const map: Record<string, string> = {
    CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/30',
    HIGH:     'bg-orange-500/20 text-orange-400 border-orange-500/30',
    MEDIUM:   'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    LOW:      'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  };
  return (
    <span className={`text-[10px] font-mono-alt font-bold px-1.5 py-0.5 rounded border ${map[level] ?? map.LOW}`}>
      {level}
    </span>
  );
}

/* ─────────────────────────────────────────────────────────
   SECTION WRAPPER
───────────────────────────────────────────────────────── */
function Section({ children, className = '', id }: { children: React.ReactNode; className?: string; id?: string }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: '-80px' });
  return (
    <motion.section
      ref={ref}
      initial={{ opacity: 0, y: 32 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className={className}
      id={id}
    >
      {children}
    </motion.section>
  );
}

/* ─────────────────────────────────────────────────────────
   PRICING CARD
───────────────────────────────────────────────────────── */
function PricingCard({ plan, region }: { plan: typeof PLANS[0]; region: typeof REGIONS[0] }) {
  const priceMap: Record<string, number> = { IN: plan.priceIN, SG: plan.priceSG, MY: plan.priceMY };
  const price = priceMap[region.code];

  return (
    <div
      className={`relative flex flex-col rounded-2xl p-8 border transition-all duration-300 ${
        plan.highlight
          ? 'bg-gradient-to-b from-cyan-950/60 to-[#0d1117] border-cyan-500/50 shadow-[0_0_40px_rgba(6,182,212,0.12)]'
          : 'bg-[#0d1117] border-white/8 hover:border-white/20'
      }`}
    >
      {plan.highlight && (
        <div className="absolute -top-px left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400 to-transparent" />
      )}
      {plan.highlight && (
        <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-3 py-1 bg-cyan-500 rounded-full text-[11px] font-mono-alt font-bold text-black tracking-wider">
          MOST POPULAR
        </div>
      )}

      <div className="mb-6">
        <p className="text-xs font-mono-alt text-white/40 uppercase tracking-widest mb-2">{plan.name}</p>
        <div className="flex items-end gap-1">
          <span className="text-xl font-mono-alt text-white/50">{region.currency}</span>
          <span className="font-syne text-4xl font-bold text-white leading-none">{price.toLocaleString()}</span>
          <span className="text-sm text-white/30 mb-1.5">/mo</span>
        </div>
        <p className="text-xs text-white/30 mt-2 font-mono-alt">{plan.cameras} cameras · 14-day free trial</p>
      </div>

      <ul className="space-y-3 flex-1 mb-8">
        {plan.features.map(f => (
          <li key={f} className="flex items-start gap-2.5 text-sm">
            <CheckCircle className="w-4 h-4 text-cyan-400 mt-0.5 flex-shrink-0" />
            <span className="text-white/65 font-body-alt">{f}</span>
          </li>
        ))}
      </ul>

      <Link
        to={`/register?plan=${plan.id}&country=${region.code}`}
        className={`block text-center py-3.5 rounded-xl text-sm font-semibold font-body-alt transition-all ${
          plan.highlight
            ? 'bg-cyan-500 hover:bg-cyan-400 text-black'
            : 'bg-white/8 hover:bg-white/14 text-white border border-white/10'
        }`}
      >
        Start Free Trial
      </Link>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   MAIN COMPONENT
───────────────────────────────────────────────────────── */
export default function Landing() {
  const { i18n } = useTranslation();
  const [activeRegion, setActiveRegion] = useState('IN');
  const [scrolled, setScrolled] = useState(false);
  const heroRef = useRef<HTMLDivElement>(null);
  useInView(heroRef, { once: true }); // trigger hero animation

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const region = REGIONS.find(r => r.code === activeRegion) ?? REGIONS[0];

  /* group features by category for display */
  const securityFeatures  = AI_FEATURES.filter(f => f.category === 'SECURITY');
  const inventoryFeatures = AI_FEATURES.filter(f => f.category === 'INVENTORY');
  const analyticsFeatures = AI_FEATURES.filter(f => f.category === 'ANALYTICS');
  const safetyFeatures    = AI_FEATURES.filter(f => f.category === 'SAFETY');

  return (
    <div
      className="min-h-screen text-white overflow-x-hidden font-body-alt"
      style={{ background: '#080c10' }}
    >
      {/* ── Ambient background glows ── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div
          className="absolute w-[700px] h-[700px] rounded-full animate-drift-glow"
          style={{ background: 'radial-gradient(circle, rgba(6,182,212,0.07) 0%, transparent 70%)', top: '-10%', left: '-10%' }}
        />
        <div
          className="absolute w-[500px] h-[500px] rounded-full animate-drift-glow"
          style={{ background: 'radial-gradient(circle, rgba(168,85,247,0.06) 0%, transparent 70%)', bottom: '10%', right: '-5%', animationDelay: '-5s' }}
        />
        {/* Fine dot grid */}
        <div
          className="absolute inset-0"
          style={{ backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)', backgroundSize: '32px 32px' }}
        />
      </div>

      {/* ── Navbar ── */}
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
          scrolled ? 'bg-[#080c10]/90 backdrop-blur-xl border-b border-white/6 shadow-lg' : ''
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="relative w-9 h-9">
              <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-cyan-400 to-violet-600 opacity-80" />
              <div className="relative w-full h-full rounded-lg flex items-center justify-center">
                <Shield className="w-4.5 h-4.5 text-white" />
              </div>
            </div>
            <span className="font-syne text-lg font-bold tracking-tight">
              Vantag
              {activeRegion === 'IN' && <span className="ml-2 text-sm font-body-alt font-medium text-cyan-400">Retail Nazar</span>}
              {activeRegion === 'MY' && <span className="ml-2 text-sm font-body-alt font-medium text-emerald-400">JagaJaga</span>}
            </span>
          </div>

          {/* Region pill */}
          <div className="hidden md:flex items-center gap-1 bg-white/5 border border-white/8 rounded-full p-1">
            {REGIONS.map(r => (
              <button
                key={r.code}
                onClick={() => { setActiveRegion(r.code); i18n.changeLanguage(r.lang); }}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold font-mono-alt tracking-wide transition-all ${
                  activeRegion === r.code
                    ? 'bg-cyan-500 text-black'
                    : 'text-white/50 hover:text-white'
                }`}
              >
                {r.flag} {r.name}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-4">
            <Link to="/login" className="text-sm text-white/50 hover:text-white transition-colors font-medium">
              Sign In
            </Link>
            <Link
              to="/register"
              className="flex items-center gap-1.5 px-4 py-2 bg-cyan-500 hover:bg-cyan-400 rounded-full text-sm font-bold text-black transition-all"
            >
              Get Started <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════════════
          HERO
      ═══════════════════════════════════════════════════ */}
      <section ref={heroRef} className="relative min-h-screen flex flex-col justify-center pt-24 pb-16">
        {/* Scan line animation */}
        <div
          className="absolute inset-x-0 h-px animate-scan-line pointer-events-none"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(6,182,212,0.5), transparent)', top: 0 }}
        />

        <div className="relative max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-10 items-center">
          {/* Left — copy */}
          <motion.div
            initial={{ opacity: 0, x: -24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
            className="min-w-0"
          >
            {/* Live badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-red-500/10 border border-red-500/25 rounded-full text-red-400 text-xs font-mono-alt font-bold tracking-widest mb-5">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-blink-live flex-shrink-0" />
              LIVE · {region.flag} {region.app}
            </div>

            <h1 className="font-black text-3xl sm:text-4xl lg:text-[2.6rem] xl:text-5xl leading-tight tracking-tight mb-6">
              <span className="text-white">11 AI Models.</span>
              <br />
              <span
                style={{
                  background: 'linear-gradient(130deg, #06b6d4 0%, #818cf8 55%, #a855f7 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                1 Platform.
              </span>
              <br />
              <span className="text-white">Zero Blind Spots.</span>
            </h1>

            <p className="text-[1.1rem] text-white/50 leading-relaxed mb-10 max-w-lg font-body-alt">
              Shoplifting, fall detection, restricted zone entry, inventory drops, queue overflows — your store,
              protected around the clock by AI that runs on your own hardware.
            </p>

            <div className="flex flex-wrap gap-4 items-center mb-14">
              <Link
                to="/register"
                className="group flex items-center gap-2 px-6 py-4 rounded-2xl text-base font-bold text-black transition-all hover:scale-[1.03]"
                style={{ background: 'linear-gradient(135deg, #06b6d4, #6366f1)' }}
              >
                Start Free Trial
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link
                to="/login"
                className="flex items-center gap-2 px-6 py-4 rounded-2xl text-sm font-semibold border border-white/10 text-white/70 hover:text-white hover:border-white/25 transition-all"
              >
                <Play className="w-4 h-4" /> Live Demo
              </Link>
            </div>

            {/* Stats row */}
            <div className="flex flex-wrap gap-8 pt-8 border-t border-white/6">
              {STATS.map(({ value, label }) => (
                <div key={label}>
                  <div className="font-syne text-2xl font-black text-white">{value}</div>
                  <div className="text-xs font-mono-alt text-white/35 tracking-wide mt-0.5">{label}</div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Right — CCTV command panel */}
          <motion.div
            initial={{ opacity: 0, x: 24, scale: 0.96 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            transition={{ duration: 1, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="hidden lg:block min-w-0"
          >
            <div
              className="relative rounded-2xl border border-white/10 overflow-hidden"
              style={{ background: 'linear-gradient(145deg, #0d1117 0%, #111827 100%)' }}
            >
              {/* Panel header */}
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/8">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-blink-live" />
                  <span className="font-mono-alt text-[11px] text-white/40 tracking-widest">VANTAG COMMAND · LIVE</span>
                </div>
                <span className="font-mono-alt text-[11px] text-cyan-400">3 CAMERAS ACTIVE</span>
              </div>

              {/* Camera grid */}
              <div className="grid grid-cols-2 gap-1 p-1">
                {[
                  { id: 'CAM-01', zone: 'Zone A — Entrance',  status: 'CLEAR', color: '#10b981' },
                  { id: 'CAM-03', zone: 'Zone C — Shelves',   status: 'ALERT', color: '#ef4444', alert: 'Shoplifting' },
                  { id: 'CAM-04', zone: 'Zone D — Checkout',  status: 'QUEUE', color: '#f59e0b', alert: 'Queue: 7/5' },
                  { id: 'OVERVIEW', zone: 'Heatmap',          status: 'LIVE',  color: '#06b6d4' },
                ].map((cam) => (
                  <div
                    key={cam.id}
                    className="relative aspect-video rounded-lg overflow-hidden"
                    style={{ background: '#0a0f14' }}
                  >
                    {/* Simulated "noise" overlay */}
                    <div className="absolute inset-0 opacity-[0.03]"
                      style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.9\' numOctaves=\'4\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\' opacity=\'1\'/%3E%3C/svg%3E")', backgroundSize: 'cover' }} />

                    {/* Grid lines */}
                    <div className="absolute inset-0 opacity-10"
                      style={{ backgroundImage: 'linear-gradient(rgba(6,182,212,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.4) 1px, transparent 1px)', backgroundSize: '20px 20px' }} />

                    {/* Camera icon in center */}
                    <div className="absolute inset-0 flex items-center justify-center">
                      {cam.id === 'OVERVIEW' ? (
                        <div className="w-full h-full p-3 flex flex-col justify-end"
                          style={{ background: 'linear-gradient(145deg, rgba(6,182,212,0.05), rgba(168,85,247,0.05))' }}>
                          {/* Mini heatmap dots */}
                          <div className="grid grid-cols-8 gap-0.5 opacity-60">
                            {Array.from({ length: 32 }).map((_, i) => {
                              const heat = Math.random();
                              return (
                                <div key={i} className="aspect-square rounded-sm"
                                  style={{ background: heat > 0.7 ? '#ef4444' : heat > 0.4 ? '#f59e0b' : '#1d4ed8', opacity: 0.3 + heat * 0.7 }} />
                              );
                            })}
                          </div>
                        </div>
                      ) : (
                        <Camera className="w-8 h-8 text-white/8" />
                      )}
                    </div>

                    {/* Alert overlay for ALERT cams */}
                    {cam.status === 'ALERT' && (
                      <div className="absolute inset-0 border-2 border-red-500/70 rounded-lg animate-pulse" />
                    )}

                    {/* Camera label */}
                    <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
                      <span className="font-mono-alt text-[9px] text-white/50">{cam.id}</span>
                      <div className="flex items-center gap-1">
                        {cam.alert && (
                          <span className="font-mono-alt text-[9px] px-1.5 py-0.5 rounded"
                            style={{ background: cam.status === 'ALERT' ? 'rgba(239,68,68,0.25)' : 'rgba(245,158,11,0.25)', color: cam.color }}>
                            {cam.alert}
                          </span>
                        )}
                        <span className="font-mono-alt text-[9px] font-bold" style={{ color: cam.color }}>{cam.status}</span>
                      </div>
                    </div>

                    {/* Top-left zone name */}
                    <div className="absolute top-2 left-2">
                      <span className="font-mono-alt text-[8px] text-white/30">{cam.zone}</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Alert feed at bottom */}
              <div className="border-t border-white/6 px-4 py-3 space-y-2">
                {[
                  { time: '14:32:07', type: 'SHOPLIFTING', msg: 'Concealment detected · Track #12 · CAM-03', color: '#ef4444' },
                  { time: '14:31:55', type: 'QUEUE',       msg: 'Lane overflow 7/5 · Est. wait 4.2 min · CAM-04', color: '#f59e0b' },
                  { time: '14:30:12', type: 'INVENTORY',   msg: 'Shelf C2 drop −3 items · no staff present', color: '#f59e0b' },
                ].map((alert) => (
                  <div key={alert.time} className="flex items-center gap-3">
                    <span className="font-mono-alt text-[9px] text-white/25 flex-shrink-0">{alert.time}</span>
                    <span className="font-mono-alt text-[9px] font-bold px-1.5 py-0.5 rounded flex-shrink-0"
                      style={{ background: `${alert.color}22`, color: alert.color }}>
                      {alert.type}
                    </span>
                    <span className="font-mono-alt text-[9px] text-white/40 truncate">{alert.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════
          AI FEATURES — 11 DETECTORS
      ═══════════════════════════════════════════════════ */}
      <Section className="py-20 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <span className="inline-block font-mono-alt text-[11px] tracking-[0.2em] text-cyan-400 uppercase mb-4">AI Detection Suite</span>
            <h2 className="font-syne text-3xl sm:text-4xl font-black text-white mb-4">11 Models. One Store.</h2>
            <p className="text-white/45 text-lg max-w-2xl mx-auto font-body-alt">
              Every detector runs simultaneously on your edge device — no cloud latency, no per-event billing.
            </p>
          </div>

          {/* Category tabs legend */}
          <div className="flex flex-wrap justify-center gap-4 mt-8 mb-14">
            {[
              { cat: 'SECURITY',  color: '#ff3c3c', count: securityFeatures.length },
              { cat: 'INVENTORY', color: '#f59e0b', count: inventoryFeatures.length },
              { cat: 'ANALYTICS', color: '#06b6d4', count: analyticsFeatures.length },
              { cat: 'SAFETY',    color: '#a855f7', count: safetyFeatures.length },
            ].map(({ cat, color, count }) => (
              <div key={cat} className="flex items-center gap-2 px-4 py-2 rounded-full border border-white/8 bg-white/3">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
                <span className="font-mono-alt text-[11px] text-white/60 tracking-widest">{cat}</span>
                <span className="font-mono-alt text-[11px] font-bold" style={{ color }}>{count}</span>
              </div>
            ))}
          </div>

          {/* Feature cards grid */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {AI_FEATURES.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.5, delay: (i % 4) * 0.07 }}
                className="group relative flex flex-col p-5 rounded-xl border border-white/7 bg-[#0d1117] hover:border-white/16 transition-all duration-300 hover:shadow-[0_0_24px_rgba(0,0,0,0.4)]"
              >
                {/* Category stripe */}
                <div
                  className="absolute top-0 left-0 right-0 h-[2px] rounded-t-xl opacity-60 group-hover:opacity-100 transition-opacity"
                  style={{ background: f.categoryColor }}
                />

                <div className="flex items-start justify-between mb-4">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: `${f.categoryColor}15`, border: `1px solid ${f.categoryColor}30` }}
                  >
                    <f.icon className="w-5 h-5" style={{ color: f.categoryColor }} />
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span
                      className="font-mono-alt text-[9px] font-bold tracking-widest"
                      style={{ color: f.categoryColor }}
                    >
                      {f.category}
                    </span>
                    <SeverityBadge level={f.badge} />
                  </div>
                </div>

                <h3 className="font-syne text-[15px] font-bold text-white mb-2 leading-tight">{f.title}</h3>
                <p className="text-[13px] text-white/40 leading-relaxed flex-1 font-body-alt">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════
          PLATFORM FEATURES
      ═══════════════════════════════════════════════════ */}
      <Section className="py-20 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div>
              <span className="inline-block font-mono-alt text-[11px] tracking-[0.2em] text-violet-400 uppercase mb-4">Platform</span>
              <h2 className="font-syne text-3xl sm:text-4xl font-black text-white mb-6">Built for the Real World</h2>
              <p className="text-white/45 text-lg leading-relaxed font-body-alt mb-10">
                Works with cameras you already own. Runs on hardware you already have. Sends alerts the way your team already works.
              </p>
              <div className="space-y-5">
                {PLATFORM_FEATURES.map((f, i) => (
                  <motion.div
                    key={f.title}
                    initial={{ opacity: 0, x: -16 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1 }}
                    className="flex gap-4"
                  >
                    <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center flex-shrink-0">
                      <f.icon className="w-5 h-5 text-violet-400" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-white text-[15px] mb-1">{f.title}</h4>
                      <p className="text-sm text-white/40 font-body-alt">{f.desc}</p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* Edge options */}
            <div className="space-y-4">
              <p className="font-mono-alt text-[11px] tracking-widest text-white/30 uppercase mb-6">Works On</p>
              {EDGE_OPTIONS.map((opt, i) => (
                <motion.div
                  key={opt.title}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="flex items-center gap-5 p-5 rounded-xl bg-[#0d1117] border border-white/7 hover:border-cyan-500/25 hover:bg-[#0d1117] transition-all group"
                >
                  <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center flex-shrink-0 group-hover:bg-cyan-500/15 transition-colors">
                    <opt.icon className="w-6 h-6 text-cyan-400" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-white text-[15px] mb-0.5">{opt.title}</h4>
                    <p className="text-sm text-white/40 font-body-alt">{opt.desc}</p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-white/20 ml-auto group-hover:text-cyan-400 group-hover:translate-x-0.5 transition-all" />
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════
          HOW IT WORKS
      ═══════════════════════════════════════════════════ */}
      <Section className="py-20 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <span className="inline-block font-mono-alt text-[11px] tracking-[0.2em] text-emerald-400 uppercase mb-4">Setup</span>
            <h2 className="font-syne text-3xl sm:text-4xl font-black text-white mb-4">Live in 30 Minutes</h2>
            <p className="text-white/45 text-lg font-body-alt">No technician. No IT team. Just your phone and your cameras.</p>
          </div>

          <div className="grid md:grid-cols-3 gap-6 relative">
            {/* Connector line */}
            <div className="hidden md:block absolute top-12 left-[16.7%] right-[16.7%] h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />

            {HOW_IT_WORKS.map((step, i) => (
              <motion.div
                key={step.step}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.15 }}
                className="relative p-8 rounded-2xl bg-[#0d1117] border border-white/7 hover:border-white/15 transition-all"
              >
                <div className="font-syne text-5xl font-black text-white/5 mb-4">{step.step}</div>
                <div className="w-8 h-1 rounded-full bg-emerald-400 mb-4" />
                <h3 className="font-syne text-xl font-bold text-white mb-3">{step.title}</h3>
                <p className="text-sm text-white/45 leading-relaxed font-body-alt">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════
          PRICING
      ═══════════════════════════════════════════════════ */}
      <Section className="py-20 border-t border-white/5" id="pricing">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <span className="inline-block font-mono-alt text-[11px] tracking-[0.2em] text-yellow-400 uppercase mb-4">Pricing</span>
            <h2 className="font-syne text-3xl sm:text-4xl font-black text-white mb-4">Simple. Local. Fair.</h2>
            <p className="text-white/45 text-lg font-body-alt mb-8">Priced in your currency. No hidden fees.</p>

            {/* Region selector */}
            <div className="inline-flex items-center gap-1 bg-white/5 border border-white/8 rounded-full p-1.5">
              {REGIONS.map(r => (
                <button
                  key={r.code}
                  onClick={() => setActiveRegion(r.code)}
                  className={`px-5 py-2 rounded-full text-sm font-mono-alt font-bold tracking-wide transition-all ${
                    activeRegion === r.code ? 'bg-cyan-500 text-black' : 'text-white/45 hover:text-white'
                  }`}
                >
                  {r.flag} {r.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-6 items-start">
            {PLANS.map(plan => (
              <PricingCard key={plan.id} plan={plan} region={region} />
            ))}
          </div>

          <p className="text-center text-xs font-mono-alt text-white/25 mt-8 tracking-wide">
            14-day free trial on all plans · Cancel anytime · Razorpay / Stripe accepted
          </p>
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════
          CTA BANNER
      ═══════════════════════════════════════════════════ */}
      <Section className="py-20 border-t border-white/5">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <div className="relative rounded-3xl overflow-hidden p-16"
            style={{ background: 'linear-gradient(145deg, rgba(6,182,212,0.08), rgba(99,102,241,0.12), rgba(168,85,247,0.08))' }}>
            <div className="absolute inset-0 border border-white/8 rounded-3xl" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-red-500/10 border border-red-500/25 rounded-full text-red-400 text-xs font-mono-alt font-bold tracking-widest mb-6">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-blink-live" />
                EVERY SECOND WITHOUT PROTECTION COSTS YOU
              </div>
              <h2 className="font-syne text-3xl sm:text-4xl font-black text-white mb-4">Ready to Protect Your Store?</h2>
              <p className="text-white/45 text-lg font-body-alt mb-8 max-w-xl mx-auto">
                Join retailers across India, Singapore and Malaysia using Vantag to stop theft before it happens.
              </p>
              <div className="flex flex-wrap justify-center gap-4">
                <Link
                  to="/register"
                  className="group flex items-center gap-2 px-8 py-4 rounded-2xl text-base font-bold text-black transition-all hover:scale-[1.03]"
                  style={{ background: 'linear-gradient(135deg, #06b6d4, #6366f1)' }}
                >
                  Start Free Trial — No Card Needed
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════
          FOOTER
      ═══════════════════════════════════════════════════ */}
      <footer className="border-t border-white/5 py-10">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-wrap justify-between gap-12">            {/* Brand */}
            <div className="max-w-xs">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-violet-600 flex items-center justify-center">
                  <Shield className="w-4 h-4 text-white" />
                </div>
                <span className="font-syne text-lg font-bold">Vantag</span>
              </div>
              <p className="text-sm text-white/35 font-body-alt leading-relaxed mb-4">
                AI-powered retail security platform for shops across India, Singapore and Malaysia.
              </p>
              <div className="flex gap-2">
                {REGIONS.map(r => (
                  <span key={r.code} className="text-[11px] font-mono-alt px-2 py-1 rounded border border-white/8 text-white/30">{r.flag} {r.app}</span>
                ))}
              </div>
            </div>

            {/* Links */}
            <div className="flex gap-16 text-sm">
              <div className="space-y-3">
                <div className="font-mono-alt text-[10px] tracking-widest text-white/25 uppercase mb-4">Product</div>
                {['Features', 'Pricing', 'Download App', 'API Docs'].map(l => (
                  <div key={l} className="text-white/40 hover:text-white/80 cursor-pointer transition-colors font-body-alt">{l}</div>
                ))}
              </div>
              <div className="space-y-3">
                <div className="font-mono-alt text-[10px] tracking-widest text-white/25 uppercase mb-4">AI Models</div>
                {['Shoplifting', 'Fall Detection', 'Queue Mgmt', 'Inventory', 'Restricted Zones'].map(l => (
                  <div key={l} className="text-white/40 hover:text-white/80 cursor-pointer transition-colors font-body-alt">{l}</div>
                ))}
              </div>
              <div className="space-y-3">
                <div className="font-mono-alt text-[10px] tracking-widest text-white/25 uppercase mb-4">Company</div>
                {['About', 'Privacy', 'Terms', 'Contact'].map(l => (
                  <div key={l} className="text-white/40 hover:text-white/80 cursor-pointer transition-colors font-body-alt">{l}</div>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between mt-12 pt-8 border-t border-white/5">
            <span className="font-mono-alt text-[11px] text-white/20">© 2026 Vantag Technologies · IN · SG · MY</span>
            <span className="font-mono-alt text-[11px] text-white/20">11 AI Models · Edge-First · Hardware-Agnostic</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
