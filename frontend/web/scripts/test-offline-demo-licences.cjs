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
  const errors = [], issued = [];
  let reject = false;
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { localStorage.setItem('vantag_token', 'test-token'); localStorage.setItem('vantag_is_super_admin', 'true'); });
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/admin/demo-entitlement')) {
      issued.push(route.request().postDataJSON());
      return route.fulfill({ status: reject ? 403 : 200, json: reject ? { detail: 'Superadmin access required' } : { payload: 'test-only-envelope', signature: 'test-only-signature' } });
    }
    if (url.pathname.endsWith('/admin/stats')) return route.fulfill({ json: null });
    if (url.pathname.endsWith('/admin/tenants')) return route.fulfill({ json: { tenants: [{ id: 'tenant-demo', name: 'Internal team' }], total: 1 } });
    return route.fulfill({ json: {} });
  });
  try {
    await page.goto(`${origin}/admin`);
    await page.getByRole('button', { name: 'Offline demos', exact: true }).click();
    await page.getByRole('heading', { name: 'Offline demo licences' }).waitFor();
    await page.getByLabel('Import device renewal request (JSON)').setInputFiles({ name: 'request.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ version: 1, purpose: 'offline_entitlement_renewal', device_id: 'a'.repeat(64), tenant_id: 'tenant-demo' })) });
    await page.waitForFunction(() => document.querySelector('input[pattern]')?.value === 'a'.repeat(64));
    assert.equal(await page.getByLabel('Account / tenant ID').inputValue(), 'tenant-demo');
    await page.getByLabel('Evaluation days').fill('14');
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Issue and download device licence' }).click();
    assert.equal((await download).suggestedFilename(), 'vantag-demo-entitlement.json');
    await page.getByRole('status').waitFor();
    assert.equal(issued[0].licence_type, 'evaluation'); assert.equal(issued[0].days, 14);
    await page.getByLabel('Usage policy').selectOption('internal_demo');
    assert.equal(await page.getByLabel('Evaluation days').count(), 0);
    const permanent = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Issue and download device licence' }).click();
    await permanent;
    assert.equal(issued[1].licence_type, 'internal_demo'); assert.equal(issued[1].days, null);
    reject = true;
    await page.getByRole('button', { name: 'Issue and download device licence' }).click();
    await page.getByRole('alert').filter({ hasText: 'Superadmin access required' }).waitFor();
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, checks: ['superadmin navigation', 'device request import', 'account selection', '14-day evaluation download', 'permanent demo without expiry field', 'inline authorization error', 'no page errors'], actual_server_signing_tested: false }));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
