const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const handler = require('serve-handler');
const { chromium } = require('playwright');

(async () => {
  const server = http.createServer((req, res) => handler(req, res, { public: path.resolve(__dirname, '../dist-offline') }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const failures = [];
  const external = [];
  let camera = { id: 'office', name: 'Office', enabled: true, detections: { restricted_zone: true }, detection_schedule: { enabled: false, start: '09:00', end: '18:00' }, inventory_zones: [], people_count_zones: [], exclusion_zones: [] };
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=', 'base64');
  page.on('pageerror', error => failures.push(error.message));
  page.on('request', req => { if (!req.url().startsWith(origin) && !req.url().startsWith('data:')) external.push(req.url()); });
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.startsWith('/api/frame/')) return route.fulfill({ contentType: 'image/png', body: image });
    if (pathname === '/api/cameras' && route.request().method() === 'POST') { camera = route.request().postDataJSON(); return route.fulfill({ json: { id: 'office', applied: true, message: 'Saved and applied to monitoring.' } }); }
    const data = {
      '/api/bootstrap': { setup_required: false }, '/api/login': {}, '/api/cameras': [camera], '/api/events': [], '/api/counts': [],
      '/api/status': { site: { name: 'Demo', timezone: 'UTC' }, licence: { state: 'active', can_process: true, claims: { camera_limit: 8, expires_at: null } }, runtime: { running: true, cameras: [{ id: 'office', connected: false, connection_error: 'RTSP authentication is required (401)', fps: 0 }], camera_capacity: { configured: 4, enabled: 4, monitored: 4, connected: 3, entitlement_limit: 8 } } },
    };
    return route.fulfill({ json: data[pathname] || {} });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByRole('button', { name: 'Help with this screen', exact: true }).click({ timeout: 5000 });
    await page.getByText('Local login is separate', { exact: false }).waitFor();
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password', { exact: true }).fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    const help = page.getByRole('region', { name: 'Offline contextual help' });
    await page.getByRole('button', { name: 'Help with this screen', exact: true }).click();
    await help.getByText('3 of 4', { exact: false }).waitFor();
    await help.getByText('401', { exact: false }).waitFor();
    await help.getByLabel('What do you need help with?').fill('password has #');
    await help.getByRole('button', { name: 'Show guidance' }).click();
    await help.getByText('not %23', { exact: false }).waitFor();
    await page.getByRole('button', { name: 'Zones', exact: true }).click();
    await help.getByText('Current screen: Zones', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Help with this screen', exact: true }).click();
    await page.locator('.panel select').first().selectOption('office');
    await page.getByLabel('Zone type', { exact: true }).selectOption('restricted_zones');
    const canvas = page.getByLabel('Drag to draw a rectangular zone over the camera image');
    const rect = await canvas.boundingBox();
    await page.mouse.move(rect.x + rect.width * 0.2, rect.y + rect.height * 0.2);
    await page.mouse.down();
    await page.mouse.move(rect.x + rect.width * 0.7, rect.y + rect.height * 0.7);
    await page.mouse.up();
    await page.getByRole('button', { name: 'Save zones', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Saved and applied' }).waitFor();
    assert.equal(camera.restricted_zones.length, 1);
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    await page.locator('svg[aria-label="Camera zone outlines"] rect').waitFor();
    await page.getByRole('button', { name: 'Zones', exact: true }).click();
    await page.getByRole('button', { name: 'Help with this screen', exact: true }).click();
    await help.getByLabel('What do you need help with?').fill('fall detection');
    await help.getByRole('button', { name: 'Show guidance' }).click();
    await help.getByText('Do not stage a real fall', { exact: false }).waitFor();
    await help.getByLabel('What do you need help with?').fill('speak Klingon');
    await help.getByRole('button', { name: 'Show guidance' }).click();
    await help.getByText('No matching offline guide', { exact: false }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(external, []);
    assert.deepEqual(failures, []);
    console.log(JSON.stringify({ ok: true, contextual_help: true, offline_network_only: true, real_ai_accuracy_tested: false }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
