/**
 * HowItWorks.tsx — public setup guide
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Gem, Hand, RefreshCw, DoorOpen } from 'lucide-react';
import Seo from '../components/Seo';

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

export default function HowItWorks({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className={embedded ? 'text-white' : 'min-h-screen bg-[#0a0a0f] text-white'}>
      {!embedded && (
        <Seo
          title="How Retail Nazar Works — AI CCTV Setup Guide | Retail Nazar"
          description="See how Retail Nazar turns your existing CCTV cameras into an AI security and analytics system in minutes — no new hardware required."
          path="/how-it-works"
        />
      )}
      {!embedded && (
      <nav className="px-8 py-4 flex items-center justify-between border-b border-white/10">
        <Link to="/" className="text-xl font-bold">Vantag</Link>
        <div className="flex gap-6 text-sm">
          <Link to="/" className="hover:text-violet-400">{t('nav.home', 'Home')}</Link>
          <Link to="/how-it-works" className="text-violet-400">{t('nav.how_it_works', 'How it works')}</Link>
          <Link to="/faq" className="hover:text-violet-400">{t('nav.faq', 'FAQ')}</Link>
          <Link to="/login" className="hover:text-violet-400">{t('nav.login', 'Login')}</Link>
        </div>
      </nav>
      )}

      <div className={embedded ? 'max-w-6xl mx-auto px-8 py-8' : 'max-w-6xl mx-auto px-8 py-16'}>
        {embedded && (
          <Link to="/help" className="inline-block mb-6 text-sm text-violet-400 hover:text-violet-300">
            ← {t('help.back', 'Back to Help Center')}
          </Link>
        )}
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
            body={t('how.s2.body', 'Secure payments in INR, SGD, MYR and PHP. Monthly or annual. Cancel anytime.')}
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

        {/* High-Value Counter highlight — jewellers & luxury goods */}
        <div className="mb-16 rounded-2xl border border-amber-400/25 bg-gradient-to-br from-amber-400/10 to-transparent p-8">
          <div className="flex items-center gap-2 mb-4">
            <Gem className="w-5 h-5 text-amber-400" />
            <h2 className="text-2xl font-bold">Built for jewellers &amp; high-value counters</h2>
          </div>
          <p className="text-white/70 mb-6 max-w-3xl">
            Jewellery, watches, luxury bags and high-value electronics are handed across a counter — not stocked on shelves. On top of every standard detector, the same camera runs three purpose-built high-value detections:
          </p>
          <div className="grid md:grid-cols-3 gap-4 mb-6">
            <div className="bg-white/5 border border-white/10 rounded-xl p-5">
              <Hand className="w-6 h-6 text-amber-400 mb-2" />
              <h3 className="font-bold mb-1">Case Hand Reach</h3>
              <p className="text-white/60 text-sm">Flags a hand that reaches into the display tray and withdraws — the exact palm-and-pull motion.</p>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-xl p-5">
              <RefreshCw className="w-6 h-6 text-amber-400 mb-2" />
              <h3 className="font-bold mb-1">Tray Change</h3>
              <p className="text-white/60 text-sm">Watches the tray's contents — a sudden change while a person is at the counter fires instantly.</p>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-xl p-5">
              <DoorOpen className="w-6 h-6 text-amber-400 mb-2" />
              <h3 className="font-bold mb-1">Grab &amp; Run</h3>
              <p className="text-white/60 text-sm">Detects a person moving from the display case to the exit unusually fast.</p>
            </div>
          </div>
          <Link to="/#high-value" className="inline-flex items-center gap-2 text-amber-300 hover:text-amber-200 font-semibold">
            See the High-Value Counter in detail →
          </Link>
        </div>

        {!embedded && (
        <div className="text-center">
          <Link to="/register"
            className="inline-block bg-gradient-to-r from-violet-600 to-purple-700 hover:from-violet-500 hover:to-purple-600 px-8 py-4 rounded-xl font-bold text-lg transition-all">
            {t('how.cta', 'Start free trial')}
          </Link>
        </div>
        )}
      </div>
    </div>
  );
}
