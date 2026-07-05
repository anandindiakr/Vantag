// scripts/prerender.mjs
//
// Post-build static prerender for public SEO routes.
// Serves the freshly built dist/ via a tiny static server, then uses
// Playwright (headless Chromium) to render each public route and writes
// the fully-hydrated HTML back into dist/<route>/index.html so crawlers
// (Googlebot, Bingbot, LinkedIn/WhatsApp preview bots, AI answer engines)
// receive real content + <title>/meta/canonical/JSON-LD on first byte —
// no JS execution required on their side.
//
// This does NOT touch authenticated routes (/dashboard, /cameras, etc.)
// and does NOT change how the SPA behaves for logged-in users; the SPA
// still hydrates normally in the browser for all routes.

import { chromium } from 'playwright';
import { createServer } from 'http';
import handler from 'serve-handler';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { mkdirSync, writeFileSync, existsSync } from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distDir = join(__dirname, '..', 'dist');
const PORT = 4173;
// Production origin to bake into canonical/OG/JSON-LD URLs. The prerender
// browser only ever visits http://localhost:PORT, so any absolute URLs
// captured from window.location.origin must be rewritten to the real
// public domain before being written to disk.
const BASE_URL = (process.env.PRERENDER_BASE_URL || 'https://retailnazar.com').replace(/\/$/, '');

// Public, unauthenticated routes only — crawlers never see /dashboard etc.
const ROUTES = [
  '/',
  '/how-it-works',
  '/faq',
  '/privacy',
  '/terms',
  '/login',
  '/register',
  '/sales-demo',
];

async function main() {
  if (!existsSync(distDir)) {
    console.error('[prerender] dist/ not found — run `vite build` first.');
    process.exit(1);
  }

  const server = createServer((req, res) =>
    handler(req, res, {
      public: distDir,
      rewrites: [{ source: '**', destination: '/index.html' }],
    })
  );
  await new Promise((resolve) => server.listen(PORT, resolve));
  console.log(`[prerender] static server on http://localhost:${PORT}`);

  const browser = await chromium.launch();
  const page = await browser.newPage();

  for (const route of ROUTES) {
    const url = `http://localhost:${PORT}${route}`;
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      // Give React a brief extra tick for any deferred effects (e.g. FAQ fetch).
      await page.waitForTimeout(300);
      let html = await page.content();
      // Rewrite any localhost origin references (canonical, og:url, twitter:image,
      // JSON-LD @id/url fields set at runtime via window.location.origin) to the
      // real production domain.
      html = html.split(`http://localhost:${PORT}`).join(BASE_URL);

      const outDir = route === '/' ? distDir : join(distDir, route.replace(/^\//, ''));
      mkdirSync(outDir, { recursive: true });
      writeFileSync(join(outDir, 'index.html'), html, 'utf-8');
      console.log(`[prerender] wrote ${route} -> ${join(outDir, 'index.html')}`);
    } catch (err) {
      console.error(`[prerender] FAILED for ${route}:`, err.message);
    }
  }

  await browser.close();
  server.close();
}

main().catch((err) => {
  console.error('[prerender] fatal error:', err);
  process.exit(1);
});
