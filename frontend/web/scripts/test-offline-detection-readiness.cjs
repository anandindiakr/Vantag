const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const handler = require('serve-handler');
const { chromium } = require('playwright');

(async () => {
  const server = http.createServer((request, response) => handler(request, response, { public: path.resolve(__dirname, '../dist-offline') }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url()); assert.equal(url.origin, origin);
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const camera = { id: 'demo', name: 'Demo camera', enabled: true, detections: {}, inventory_zones: [], people_count_zones: [], exclusion_zones: [], detection_schedule: { enabled: false, start: '09:00', end: '18:00' } };
    let json = {};
    if (url.pathname === '/api/bootstrap') json = { setup_required: false };
    if (url.pathname === '/api/cameras') json = [camera];
    if (url.pathname === '/api/status') json = { site: { name: 'Test site', timezone: 'UTC' }, licence: { state: 'active', can_process: true, claims: { licence_type: 'internal_demo', expires_at: null, camera_limit: 8 } }, runtime: { running: true, cameras: [{ id: 'demo', name: camera.name, connected: true, fall_status: { state: 'Off for this camera' }, theft_status: { state: 'Concealment analysis unavailable: RuntimeError; proximity heuristic only' }, inventory_status: { state: 'Draw and save a shelf zone first' } }] } };
    if (url.pathname === '/api/events' || url.pathname === '/api/counts') json = [];
    if (url.pathname.startsWith('/api/frame/')) return route.fulfill({ status: 503 });
    return route.fulfill({ json });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('owner'); await page.getByLabel('Local password').fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    await page.getByRole('button', { name: 'Demo camera', exact: true }).click();
    const panel = page.getByRole('region', { name: 'Selected camera analytics' });
    await panel.getByText('Concealment analysis unavailable: RuntimeError; proximity heuristic only', { exact: false }).waitFor();
    await panel.getByText('Draw and save a shelf zone first', { exact: false }).waitFor();
    await page.getByRole('button', { name: 'Licence & health', exact: true }).click();
    await page.getByText('Internal team demo — no expiry; bound to this device only', { exact: false }).waitFor();
    assert.equal(await page.getByText(/Invalid Date|1970/).count(), 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, checks: ['inline theft failure', 'inline missing shelf zone', 'permanent device licence display', 'no fabricated expiry', 'no external requests or page errors'], real_detections_tested: false }));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
