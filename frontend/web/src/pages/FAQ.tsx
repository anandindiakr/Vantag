/**
 * FAQ.tsx — public FAQ (pulled from /api/support/faq)
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

interface Faq { q: string; a: string; }

export default function FAQ() {
  const { t } = useTranslation();
  const [faqs, setFaqs] = useState<Faq[]>([]);

  useEffect(() => {
    fetch('/api/support/faq')
      .then((r) => r.json())
      .then((d) => setFaqs(d.faqs || []))
      .catch(() => setFaqs([]));
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <nav className="px-8 py-4 flex items-center justify-between border-b border-white/10">
        <Link to="/" className="text-xl font-bold">Vantag</Link>
        <div className="flex gap-6 text-sm">
          <Link to="/" className="hover:text-violet-400">{t('nav.home', 'Home')}</Link>
          <Link to="/how-it-works" className="hover:text-violet-400">{t('nav.how_it_works', 'How it works')}</Link>
          <Link to="/faq" className="text-violet-400">{t('nav.faq', 'FAQ')}</Link>
          <Link to="/login" className="hover:text-violet-400">{t('nav.login', 'Login')}</Link>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-8 py-16">
        <h1 className="text-5xl font-bold mb-4 text-center">
          {t('faq.title', 'Frequently asked questions')}
        </h1>
        <p className="text-white/60 text-center mb-12">
          {t('faq.subtitle', "Can't find what you need? Use the chat in the bottom-right or email support@retail-vantag.com")}
        </p>

        <div className="space-y-3">
          {faqs.map((f, i) => (
            <details key={i} className="bg-white/5 border border-white/10 rounded-xl p-5 group">
              <summary className="cursor-pointer font-bold text-lg flex items-center justify-between">
                {f.q}
                <span className="text-violet-400 group-open:rotate-180 transition-transform">▾</span>
              </summary>
              <p className="mt-3 text-white/70 whitespace-pre-wrap">{f.a}</p>
            </details>
          ))}
          {faqs.length === 0 && (
            <div className="text-white/50 text-center py-12">Loading FAQs…</div>
          )}
        </div>

        <div className="mt-12 text-center bg-gradient-to-r from-violet-600/20 to-purple-700/20 border border-violet-500/30 rounded-2xl p-8">
          <h3 className="text-2xl font-bold mb-2">{t('faq.more_title', 'Still need help?')}</h3>
          <p className="text-white/70 mb-4">
            {t('faq.more_body', 'Our Vantag Assistant (bottom-right) answers instantly. For complex cases, email our team.')}
          </p>
          <a href="mailto:support@retail-vantag.com"
            className="inline-block bg-violet-600 hover:bg-violet-500 px-6 py-3 rounded-xl font-bold">
            support@retail-vantag.com
          </a>
        </div>
      </div>
    </div>
  );
}
