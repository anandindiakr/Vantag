const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const handler = require('serve-handler');
const { chromium } = require('playwright');

(async () => {
  const server = http.createServer((request, response) => handler(request, response, { public: path.resolve(__dirname, '../dist'), rewrites: [{ source: '**', destination: '/index.html' }] }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem('vantag_token', 'test-token');
    localStorage.setItem('vantag_is_super_admin', 'true');
    localStorage.setItem('vantag_tenant', JSON.stringify({ id: 'tenant-demo', name: 'Demo site', status: 'active' }));
  });
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith('/offline/availability')) return route.fulfill({ json: { available: false } });
    if (pathname.endsWith('/agent/version')) return route.fulfill({ json: { version: '1.11.5' } });
    if (pathname.endsWith('/support/faq')) return route.fulfill({ json: { categories: [] } });
    if (pathname.endsWith('/admin/stats')) return route.fulfill({ json: null });
    if (pathname.endsWith('/admin/tenants')) return route.fulfill({ json: { tenants: [] } });
    return route.fulfill({ json: {} });
  });
  try {
    await page.goto(origin);
    await page.locator('#offline-site-guide').waitFor();
    await page.getByRole('link', { name: 'Read setup, licensing and troubleshooting steps' }).click();
    await page.getByRole('heading', { name: 'From online download to offline monitoring' }).waitFor();
    assert.equal(new URL(page.url()).hash, '#offline-site-guide');
    await page.waitForFunction(() => Math.abs(document.querySelector('#offline-site-guide').getBoundingClientRect().top) < 100);
    const guide = page.locator('#offline-site-guide');
    for (const text of ['public website', 'same PC', 'seven days of grace', 'no expiry', 'do not automatically sync', 'RTSP 401', 'under validation']) {
      assert.ok((await guide.textContent()).toLowerCase().includes(text.toLowerCase()), text);
    }
    await guide.getByText('Superadmin: customers, evaluations and internal demo PCs', { exact: true }).click();
    assert.ok((await guide.innerText()).includes('Evaluation days (1–365)'));
    assert.ok((await guide.innerText()).includes('does not create employee accounts') || (await guide.innerText()).includes('do not create employee accounts'));

    await page.goto(`${origin}/download`);
    await page.getByRole('heading', { name: 'Online packages · internet required for the website' }).waitFor();
    const offlineDownload = page.getByRole('button', { name: 'Under validation — not available for installation' });
    assert.equal(await offlineDownload.isDisabled(), true);
    await page.getByRole('heading', { name: 'Online agent installation' }).waitFor();

    await page.goto(`${origin}/help`);
    await page.locator('#offline-site-guide').waitFor();
    assert.ok((await page.locator('#offline-site-guide').innerText()).includes('local owner login'));
    await page.getByText('The downloadable PDF may describe the earlier online workflow.', { exact: false }).waitFor();

    await page.goto(`${origin}/admin`);
    await page.getByRole('button', { name: 'Offline demos', exact: true }).click();
    await page.getByRole('link', { name: 'Read offline setup, customer renewal and team demo instructions' }).click();
    await page.locator('#offline-site-guide').waitFor();
    assert.equal(new URL(page.url()).pathname, '/help');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${origin}/how-it-works#offline-site-guide`);
    await page.locator('#offline-site-guide').waitFor();
    const widths = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth }));
    assert.ok(widths.page <= widths.viewport, JSON.stringify(widths));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, checks: ['homepage guide navigation and anchor', 'mode and release-limit copy', 'licence and admin steps', 'disabled unqualified download', 'logged-in help', 'admin-to-help navigation', 'mobile layout', 'no page errors'], actual_offline_inference_tested: false }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
