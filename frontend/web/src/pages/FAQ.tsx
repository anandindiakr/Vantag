/**
 * FAQ.tsx — public FAQ (pulled from /api/support/faq)
 * Renders a categorized FAQ with icons, optional step-by-step diagrams,
 * and collapsible Q&A accordions per category.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Rocket, Wifi, HardDrive, Bell, AlertTriangle, Brain, CreditCard, Shield, HelpCircle,
} from 'lucide-react';
import { useRegion } from '../hooks/useRegion';
import Seo from '../components/Seo';

interface FaqItem { q: string; a: string; }
interface FaqCategory { id: string; title: string; icon: string; diagram?: string; items: FaqItem[]; }

const ICONS: Record<string, typeof HelpCircle> = {
  Rocket, Wifi, HardDrive, Bell, AlertTriangle, Brain, CreditCard, Shield,
};

function CategoryIcon({ name, className }: { name: string; className?: string }) {
  const Cmp = ICONS[name] || HelpCircle;
  return <Cmp className={className} />;
}

export default function FAQ({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation();
  const region = useRegion();
  const supportEmail = region.region === 'IN' ? 'support@retailnazar.com' : region.region === 'PH' ? 'support@retailbantay.com' : region.region === 'ID' ? 'support@retailpantau.com' : 'support@retail-vantag.com';
  const [categories, setCategories] = useState<FaqCategory[]>([]);
  const [activeId, setActiveId] = useState<string>('');

  useEffect(() => {
    fetch('/api/support/faq')
      .then((r) => r.json())
      .then((d) => {
        const cats: FaqCategory[] = d.categories || [];
        setCategories(cats);
        if (cats.length) setActiveId(cats[0].id);
      })
      .catch(() => setCategories([]));
  }, []);

  const allItems = categories.flatMap((c) => c.items);

  const scrollTo = (id: string) => {
    setActiveId(id);
    document.getElementById(`faq-cat-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className={embedded ? 'text-white' : 'min-h-screen bg-[#0a0a0f] text-white'}>
      {!embedded && (
        <Seo
          title="Frequently Asked Questions — Retail Nazar"
          description="Answers to common questions about Retail Nazar CCTV AI setup, NVR compatibility, alert configuration, installation mistakes to avoid, pricing, and data privacy."
          path="/faq"
          jsonLd={allItems.length ? {
            '@context': 'https://schema.org',
            '@type': 'FAQPage',
            mainEntity: allItems.map((f) => ({
              '@type': 'Question',
              name: f.q,
              acceptedAnswer: { '@type': 'Answer', text: f.a },
            })),
          } : undefined}
        />
      )}
      {!embedded && (
      <nav className="px-8 py-4 flex items-center justify-between border-b border-white/10">
        <Link to="/" className="text-xl font-bold">Vantag</Link>
        <div className="flex gap-6 text-sm">
          <Link to="/" className="hover:text-violet-400">{t('nav.home', 'Home')}</Link>
          <Link to="/how-it-works" className="hover:text-violet-400">{t('nav.how_it_works', 'How it works')}</Link>
          <Link to="/faq" className="text-violet-400">{t('nav.faq', 'FAQ')}</Link>
          <Link to="/login" className="hover:text-violet-400">{t('nav.login', 'Login')}</Link>
        </div>
      </nav>
      )}

      <div className={embedded ? 'max-w-4xl mx-auto px-8 py-8' : 'max-w-4xl mx-auto px-8 py-16'}>
        {embedded && (
          <Link to="/help" className="inline-block mb-6 text-sm text-violet-400 hover:text-violet-300">
            ← {t('help.back', 'Back to Help Center')}
          </Link>
        )}
        <h1 className="text-5xl font-bold mb-4 text-center">
          {t('faq.title', 'Frequently asked questions')}
        </h1>
        <p className="text-white/60 text-center mb-8">
          {t('faq.subtitle', "Can't find what you need? Use the chat in the bottom-right or email ") + supportEmail}
        </p>

        {categories.length === 0 && (
          <div className="text-white/50 text-center py-12">Loading FAQs…</div>
        )}

        {/* Category quick-nav */}
        {categories.length > 0 && (
          <div className="flex flex-wrap gap-2 justify-center mb-10 sticky top-0 z-10 bg-[#0a0a0f]/90 backdrop-blur py-3">
            {categories.map((c) => (
              <button
                key={c.id}
                onClick={() => scrollTo(c.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                  activeId === c.id
                    ? 'bg-violet-600 border-violet-500 text-white'
                    : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10'
                }`}
              >
                <CategoryIcon name={c.icon} className="w-4 h-4" />
                {c.title}
              </button>
            ))}
          </div>
        )}

        <div className="space-y-10">
          {categories.map((cat) => (
            <section key={cat.id} id={`faq-cat-${cat.id}`} className="scroll-mt-24">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400">
                  <CategoryIcon name={cat.icon} className="w-5 h-5" />
                </div>
                <h2 className="text-2xl font-bold">{cat.title}</h2>
              </div>

              {cat.diagram && (
                <div className="mb-5 rounded-xl overflow-hidden border border-white/10 bg-white/5">
                  <img src={cat.diagram} alt={`${cat.title} diagram`} className="w-full h-auto" loading="lazy" />
                </div>
              )}

              <div className="space-y-3">
                {cat.items.map((f, i) => (
                  <details key={i} className="bg-white/5 border border-white/10 rounded-xl p-5 group">
                    <summary className="cursor-pointer font-bold text-lg flex items-center justify-between gap-4">
                      <span>{f.q}</span>
                      <span className="text-violet-400 group-open:rotate-180 transition-transform shrink-0">▾</span>
                    </summary>
                    <p className="mt-3 text-white/70 whitespace-pre-wrap">{f.a}</p>
                  </details>
                ))}
              </div>
            </section>
          ))}
        </div>

        <div className="mt-12 text-center bg-gradient-to-r from-violet-600/20 to-purple-700/20 border border-violet-500/30 rounded-2xl p-8">
          <h3 className="text-2xl font-bold mb-2">{t('faq.more_title', 'Still need help?')}</h3>
          <p className="text-white/70 mb-4">
            {t('faq.more_body', 'Our Vantag Assistant (bottom-right) answers instantly. For complex cases, email our team.')}
          </p>
          <a href={`mailto:${supportEmail}`}
            className="inline-block bg-violet-600 hover:bg-violet-500 px-6 py-3 rounded-xl font-bold">
            {supportEmail}
          </a>
        </div>
      </div>
    </div>
  );
}
