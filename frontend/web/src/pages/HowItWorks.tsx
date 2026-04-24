/**
 * HowItWorks.tsx — public setup guide
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const Step = ({ num, title, body, icon }: { num: number; title: string; body: string; icon: string }) => (
  <div className="bg-white/5 border border-white/10 rounded-xl p-6">
    <div className="flex items-center gap-3 mb-3">
      <span className="w-10 h-10 rounded-full bg-violet-600 text-white flex items-center justify-center font-bold">
        {num}
      </span>
      <span className="text-3xl">{icon}</span>
    </div>
    <h3 className="text-xl font-bold mb-2">{title}</h3>
    <p className="text-white/70 text-sm">{body}</p>
  </div>
);

export default function HowItWorks() {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <nav className="px-8 py-4 flex items-center justify-between border-b border-white/10">
        <Link to="/" className="text-xl font-bold">Vantag</Link>
        <div className="flex gap-6 text-sm">
          <Link to="/" className="hover:text-violet-400">{t('nav.home', 'Home')}</Link>
          <Link to="/how-it-works" className="text-violet-400">{t('nav.how_it_works', 'How it works')}</Link>
          <Link to="/faq" className="hover:text-violet-400">{t('nav.faq', 'FAQ')}</Link>
          <Link to="/login" className="hover:text-violet-400">{t('nav.login', 'Login')}</Link>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-8 py-16">
        <h1 className="text-5xl font-bold mb-4 text-center">
          {t('how.title', 'How Vantag works')}
        </h1>
        <p className="text-xl text-white/70 text-center mb-16 max-w-3xl mx-auto">
          {t('how.subtitle', 'Plug-and-play retail AI. Up and running in under 30 minutes.')}
        </p>

        {/* 6 steps */}
        <div className="grid md:grid-cols-3 gap-5 mb-20">
          <Step num={1} icon="📝"
            title={t('how.s1.title', 'Register your store')}
            body={t('how.s1.body', 'Sign up with your email, store name, country and pick a plan that fits your camera count (2–30).')}
          />
          <Step num={2} icon="💳"
            title={t('how.s2.title', 'Pay in your currency')}
            body={t('how.s2.body', 'Razorpay supports INR, SGD and MYR. Monthly or annual. Cancel anytime.')}
          />
          <Step num={3} icon="⬇️"
            title={t('how.s3.title', 'Download the Edge Agent')}
            body={t('how.s3.body', 'A small Python app for Windows/Linux/Mac/Raspberry Pi. Runs locally on your PC or tablet.')}
          />
          <Step num={4} icon="🔍"
            title={t('how.s4.title', 'Auto-discover cameras')}
            body={t('how.s4.body', 'The agent scans your LAN for IP cameras (RTSP port 554) and lists them in your dashboard.')}
          />
          <Step num={5} icon="🎯"
            title={t('how.s5.title', 'Draw zones')}
            body={t('how.s5.body', 'For each camera snapshot, drag a box over shelves, aisles, or entry points. Label them.')}
          />
          <Step num={6} icon="🚨"
            title={t('how.s6.title', 'Live alerts start')}
            body={t('how.s6.body', 'Theft, loitering, falls, empty shelves — real-time alerts + evidence snapshots on your phone.')}
          />
        </div>

        {/* Architecture diagram */}
        <div className="bg-white/5 border border-white/10 rounded-2xl p-8 mb-20">
          <h2 className="text-3xl font-bold mb-6 text-center">
            {t('how.arch_title', 'Architecture at a glance')}
          </h2>
          <pre className="text-center text-violet-300 font-mono text-xs md:text-sm overflow-x-auto">
{`  ┌─ Retailer's LAN ──────────────┐       ┌─── Vantag Cloud (VPS) ───┐
  │                               │       │                          │
  │  [IP Camera] ─┐               │       │   Dashboard / Web / App  │
  │  [IP Camera] ─┤               │       │           ▲              │
  │  [IP Camera] ─┼─▶ Edge Agent ─┼──TLS──┼──▶ FastAPI + PostgreSQL  │
  │  [IP Camera] ─┘   (YOLOv8)    │       │           │              │
  │                               │       │      Mosquitto MQTT      │
  │  Video stays LOCAL            │       │                          │
  │  Only events + snapshots      │       │  Razorpay · Let's Encrypt│
  │  leave the LAN (low BW)       │       │                          │
  └───────────────────────────────┘       └──────────────────────────┘`}
          </pre>
        </div>

        <div className="text-center">
          <Link to="/register"
            className="inline-block bg-gradient-to-r from-violet-600 to-purple-700 hover:from-violet-500 hover:to-purple-600 px-8 py-4 rounded-xl font-bold text-lg transition-all">
            {t('how.cta', 'Start free trial')}
          </Link>
        </div>
      </div>
    </div>
  );
}
