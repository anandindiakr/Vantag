/**
 * HelpCenter.tsx — logged-in help page
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Download, MessageCircle, Mail, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Faq { q: string; a: string; }

export default function HelpCenter() {
  const { t } = useTranslation();
  const [faqs, setFaqs] = useState<Faq[]>([]);

  useEffect(() => {
    fetch('/api/support/faq')
      .then((r) => r.json())
      .then((d) => setFaqs(d.faqs || []))
      .catch(() => setFaqs([]));
  }, []);

  const quicklinks = [
    { icon: <Download size={20} />, title: t('help.ql.install', 'Install Edge Agent'), to: '/download' },
    { icon: <BookOpen size={20} />, title: t('help.ql.how', 'How Vantag works'), to: '/how-it-works' },
    { icon: <ShieldCheck size={20} />, title: t('help.ql.security', 'Security & Privacy'), to: '/faq' },
    { icon: <MessageCircle size={20} />, title: t('help.ql.chat', 'Chat with AI Assistant'), action: 'chat' },
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white p-8 max-w-5xl mx-auto">
      <h1 className="text-4xl font-bold mb-2">{t('help.title', 'Help Center')}</h1>
      <p className="text-white/60 mb-8">
        {t('help.subtitle', 'Get instant answers from Vantag Assistant or browse our guides.')}
      </p>

      {/* Quick actions */}
      <div className="grid md:grid-cols-4 gap-3 mb-10">
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
      </div>

      {/* FAQ */}
      <h2 className="text-2xl font-bold mb-4">{t('help.faq_title', 'Frequently asked questions')}</h2>
      <div className="space-y-3 mb-10">
        {faqs.map((f, i) => (
          <details key={i} className="bg-white/5 border border-white/10 rounded-xl p-5 group">
            <summary className="cursor-pointer font-bold flex items-center justify-between">
              {f.q}
              <span className="text-violet-400 group-open:rotate-180 transition-transform">▾</span>
            </summary>
            <p className="mt-3 text-white/70 whitespace-pre-wrap">{f.a}</p>
          </details>
        ))}
      </div>

      {/* Contact */}
      <div className="bg-gradient-to-r from-violet-600/20 to-purple-700/20 border border-violet-500/30 rounded-2xl p-6 flex items-center justify-between flex-wrap gap-4">
        <div>
          <h3 className="text-xl font-bold mb-1">{t('help.contact_title', 'Need a human?')}</h3>
          <p className="text-white/70 text-sm">{t('help.contact_body', "Email us and we'll reply within 24 hours.")}</p>
        </div>
        <a href="mailto:support@retail-vantag.com"
          className="bg-violet-600 hover:bg-violet-500 px-5 py-3 rounded-xl font-bold flex items-center gap-2">
          <Mail size={16} /> support@retail-vantag.com
        </a>
      </div>
    </div>
  );
}
