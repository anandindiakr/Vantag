// Generates robots.txt and sitemap.xml at build time, using the same
// PRERENDER_BASE_URL env var as scripts/prerender.mjs so every per-domain
// build (build:in / build:sg / build:my) gets correct absolute URLs.
import { writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distDir = join(__dirname, '..', 'dist');
const BASE_URL = (process.env.PRERENDER_BASE_URL || 'https://retailnazar.com').replace(/\/$/, '');

// Public marketing/content pages worth indexing. Keep in sync with the
// ROUTES list in scripts/prerender.mjs (auth pages like /login, /register
// are crawlable but intentionally omitted from the sitemap — they carry
// no unique SEO value and shouldn't compete with marketing pages).
const SITEMAP_ROUTES = [
  { path: '/', priority: '1.0', changefreq: 'weekly' },
  { path: '/how-it-works', priority: '0.8', changefreq: 'monthly' },
  { path: '/faq', priority: '0.8', changefreq: 'monthly' },
  { path: '/sales-demo', priority: '0.7', changefreq: 'monthly' },
  { path: '/privacy', priority: '0.3', changefreq: 'yearly' },
  { path: '/terms', priority: '0.3', changefreq: 'yearly' },
];

// Authenticated / private app routes that must never be indexed.
const DISALLOWED_PREFIXES = [
  '/dashboard', '/admin', '/account', '/cameras', '/onboarding',
  '/watchlist', '/incidents', '/setup', '/zone-editor', '/agent-status',
  '/health-check', '/pair', '/download', '/verify-email',
  '/reset-password', '/forgot-password', '/store',
];

const today = new Date().toISOString().slice(0, 10);

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${SITEMAP_ROUTES.map(r => `  <url>
    <loc>${BASE_URL}${r.path}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>${r.changefreq}</changefreq>
    <priority>${r.priority}</priority>
  </url>`).join('\n')}
</urlset>
`;

const robots = `User-agent: *
Allow: /
${DISALLOWED_PREFIXES.map(p => `Disallow: ${p}`).join('\n')}

Sitemap: ${BASE_URL}/sitemap.xml
`;

writeFileSync(join(distDir, 'sitemap.xml'), sitemap, 'utf-8');
writeFileSync(join(distDir, 'robots.txt'), robots, 'utf-8');
console.log(`[seo-files] wrote sitemap.xml + robots.txt for ${BASE_URL}`);
