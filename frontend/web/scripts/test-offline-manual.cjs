const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const handler = require('serve-handler');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const directory of ['dist', 'dist-offline']) {
      const server = http.createServer((request, response) => handler(request, response, { public: path.resolve(__dirname, '..', directory), rewrites: [{ source: '/help', destination: '/index.html' }, { source: '/download', destination: '/index.html' }] }));
      await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
      const origin = `http://127.0.0.1:${server.address().port}`;
      const page = await browser.newPage();
      try {
        if (directory === 'dist') {
          await page.addInitScript(() => { localStorage.setItem('vantag_token', 'test-token'); localStorage.setItem('vantag_tenant', JSON.stringify({ id: 'test', name: 'Test site', status: 'active' })); });
          await page.route('**/api/**', route => route.fulfill({ json: { available: false, categories: [] } }));
          for (const pathname of ['/help', '/download']) {
            await page.goto(origin + pathname);
            const link = page.getByRole('link', { name: 'Download offline demo-team manual (PDF)', exact: true });
            await link.waitFor();
            assert.equal(await link.getAttribute('href'), '/handouts/vantag-offline-demo-team-manual.pdf');
          }
        }
        const prefix = directory === 'dist' ? '/handouts/' : '/assets/';
        const pdf = await page.request.get(`${origin}${prefix}vantag-offline-demo-team-manual.pdf`);
        assert.equal(pdf.status(), 200);
        assert.equal((await pdf.body()).subarray(0, 5).toString(), '%PDF-');
        assert.ok(pdf.headers()['content-type'].includes('application/pdf'));
        const externalRequests = [];
        page.on('request', request => { if (new URL(request.url()).origin !== origin) externalRequests.push(request.url()); });
        await page.goto(`${origin}${prefix}vantag-offline-demo-team-manual.html`);
        assert.equal(await page.locator('main > section').count(), 8);
        await page.getByRole('link', { name: '4. Add cameras and get a real decoded frame', exact: true }).click();
        assert.equal(new URL(page.url()).hash, '#chapter-4');
        assert.deepEqual(externalRequests, []);
        await page.setViewportSize({ width: 390, height: 844 });
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        results.push({ directory, pdf_verified: true, eight_html_chapters: true, offline_self_contained: true, mobile_layout: true });
      } finally { await page.close(); await new Promise(resolve => server.close(resolve)); }
    }
    console.log(JSON.stringify({ ok: true, results }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
