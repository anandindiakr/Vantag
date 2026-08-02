/**
 * HelpCenter.tsx — logged-in help page
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen, Download, MessageCircle, Mail, ShieldCheck,
  Rocket, Wifi, HardDrive, Bell, AlertTriangle, Brain, CreditCard, HelpCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useRegion } from '../hooks/useRegion';

interface FaqItem { q: string; a: string; }
interface FaqCategory { id: string; title: string; icon: string; diagram?: string; items: FaqItem[]; }

const ICONS: Record<string, typeof HelpCircle> = {
  Rocket, Wifi, HardDrive, Bell, AlertTriangle, Brain, CreditCard, Shield: ShieldCheck,
};

function CategoryIcon({ name, className }: { name: string; className?: string }) {
  const Cmp = ICONS[name] || HelpCircle;
  return <Cmp className={className} />;
}

export default function HelpCenter() {
  const { t } = useTranslation();
  const region = useRegion();
  const supportEmail = region.region === 'IN' ? 'support@retailnazar.com' : region.region === 'PH' ? 'support@retailbantay.com' : region.region === 'ID' ? 'support@retailpantau.com' : 'support@retail-vantag.com';
  const [categories, setCategories] = useState<FaqCategory[]>([]);

  useEffect(() => {
    fetch('/api/support/faq')
      .then((r) => r.json())
      .then((d) => setCategories(d.categories || []))
      .catch(() => setCategories([]));
  }, []);

  const quicklinks = [
    { icon: <Download size={20} />, title: t('help.ql.install', 'Install Edge Agent'), to: '/download' },
    { icon: <BookOpen size={20} />, title: t('help.ql.how', 'How Vantag works'), to: '/help/how-it-works' },
    { icon: <ShieldCheck size={20} />, title: t('help.ql.security', 'Security & Privacy'), to: '/help/faq' },
    { icon: <MessageCircle size={20} />, title: t('help.ql.chat', 'Chat with AI Assistant'), action: 'chat' },
  ];

  const handleManualDownload = async () => {
    try {
      const token = localStorage.getItem('vantag_token') || '';
      const res = await fetch('/api/support/manual', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('download failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'Vantag_User_Manual.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      window.open('/api/support/manual', '_blank');
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white p-8 max-w-5xl mx-auto">
      <h1 className="text-4xl font-bold mb-2">{t('help.title', 'Help Center')}</h1>
      <p className="text-white/60 mb-8">
        {t('help.subtitle', 'Get instant answers from Vantag Assistant or browse our guides.')}
      </p>

      {/* Quick actions */}
      <div className="grid md:grid-cols-5 gap-3 mb-10">
        {quicklinks.map((q, i) =>
          q.to ? (
            <Link key={i} to={q.to}
              className="bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl p-5 transition-all">
              <div className="text-violet-400 mb-2">{q.icon}</div>
              <div className="font-bold">{q.title}</div>
            </Link>
          ) : (
            <div key={i}
              className="bg-gradient-to-br from-violet-600 to-purple-700 rounded-xl p-5 cursor-pointer"
              onClick={() => {
                // Trigger opening the SupportChat (floating button is always visible)
                const btn = document.querySelector('[aria-label="Open support chat"]') as HTMLButtonElement;
                btn?.click();
              }}>
              <div className="text-white mb-2">{q.icon}</div>
              <div className="font-bold text-white">{q.title}</div>
              <div className="text-xs text-white/80 mt-1">{t('help.ql.chat_sub', 'Instant answers, 24/7')}</div>
            </div>
          )
        )}
        <button
          onClick={handleManualDownload}
          className="bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl p-5 transition-all text-left">
          <div className="text-violet-400 mb-2"><BookOpen size={20} /></div>
          <div className="font-bold">{t('help.ql.manual', 'Download User Manual')}</div>
        </button>
      </div>

      {/* FAQ */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">{t('help.faq_title', 'Frequently asked questions')}</h2>
        <Link to="/help/faq" className="text-sm text-violet-400 hover:text-violet-300">
          {t('help.faq_view_all', 'View full FAQ →')}
        </Link>
      </div>
      <div className="space-y-8 mb-10">
        {categories.length === 0 && (
          <div className="text-white/50 text-center py-8">Loading FAQs…</div>
        )}
        {categories.map((cat) => (
          <div key={cat.id}>
            <div className="flex items-center gap-2 mb-3">
              <CategoryIcon name={cat.icon} className="w-5 h-5 text-violet-400" />
              <h3 className="font-bold text-lg">{cat.title}</h3>
            </div>
            {cat.diagram && (
              <div className="mb-4 rounded-xl overflow-hidden border border-white/10 bg-white/5">
                <img src={cat.diagram} alt={`${cat.title} diagram`} className="w-full h-auto" loading="lazy" />
              </div>
            )}
            <div className="space-y-3">
              {cat.items.map((f, i) => (
                <details key={i} className="bg-white/5 border border-white/10 rounded-xl p-5 group">
                  <summary className="cursor-pointer font-bold flex items-center justify-between gap-4">
                    <span>{f.q}</span>
                    <span className="text-violet-400 group-open:rotate-180 transition-transform shrink-0">▾</span>
                  </summary>
                  <p className="mt-3 text-white/70 whitespace-pre-wrap">{f.a}</p>
                </details>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Contact */}
      <div className="bg-gradient-to-r from-violet-600/20 to-purple-700/20 border border-violet-500/30 rounded-2xl p-6 flex items-center justify-between flex-wrap gap-4">
        <div>
          <h3 className="text-xl font-bold mb-1">{t('help.contact_title', 'Need a human?')}</h3>
          <p className="text-white/70 text-sm">{t('help.contact_body', "Email us and we'll reply within 24 hours.")}</p>
        </div>
        <a href={`mailto:${supportEmail}`}
          className="bg-violet-600 hover:bg-violet-500 px-5 py-3 rounded-xl font-bold flex items-center gap-2">
          <Mail size={16} /> {supportEmail}
        </a>
      </div>
    </div>
  );
}
