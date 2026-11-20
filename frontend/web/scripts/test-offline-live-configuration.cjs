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
  let applicationError = false;
  let camera = { id: 'one', name: 'Entrance', enabled: true, detections: { people_count: true }, detection_schedule: { enabled: false, start: '09:00', end: '18:00' }, inventory_zones: [], people_count_zones: [], exclusion_zones: [] };
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=', 'base64');
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    assert.equal(url.origin, origin);
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (url.pathname.startsWith('/api/frame/')) return route.fulfill({ status: 200, contentType: 'image/png', body: image });
    let result = {};
    if (url.pathname === '/api/bootstrap') result = { setup_required: false };
    if (url.pathname === '/api/status') result = { licence: { state: 'active', can_process: true }, site: { name: 'Live configuration test', timezone: 'UTC' }, runtime: { running: true, cameras: [{ id: 'one', connected: true }] } };
    if (url.pathname === '/api/events' || url.pathname === '/api/counts') result = [];
    if (url.pathname === '/api/cameras') {
      if (route.request().method() === 'POST') {
        const { rtsp_url, ...saved } = route.request().postDataJSON();
        camera = saved;
        result = { id: 'one', applied: !applicationError, application_error: applicationError, message: applicationError ? 'Configuration saved, but could not be applied. Retry Start / apply configuration.' : 'Saved and applied to monitoring.' };
      } else result = [camera];
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('test-owner');
    await page.getByLabel('Local password').fill('not-a-real-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Zones', exact: true }).click();
    await page.locator('.panel select').first().selectOption('one');
    const surface = page.locator('canvas');
    await surface.waitFor();
    const rect = await surface.boundingBox();
    await page.mouse.move(rect.x + rect.width * 0.2, rect.y + rect.height * 0.2);
    await page.mouse.down();
    await page.mouse.move(rect.x + rect.width * 0.6, rect.y + rect.height * 0.7);
    await page.mouse.up();
    await page.getByText('Unsaved zone changes', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Save zones', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Saved and applied to monitoring.' }).waitFor();
    assert.equal(await page.getByText('Unsaved zone changes', { exact: true }).count(), 0);
    assert.equal(camera.inventory_zones.length, 1);
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    await page.locator('svg[aria-label="Camera zone outlines"] rect').waitFor();
    assert.equal(await page.locator('svg[aria-label="Camera zone outlines"] rect').count(), 1);
    await page.getByRole('button', { name: 'New camera', exact: true }).click();
    await page.getByRole('button', { name: 'Entrance', exact: true }).click();
    assert.equal(await page.locator('svg[aria-label="Camera zone outlines"] rect').count(), 1);
    applicationError = true;
    await page.getByRole('button', { name: 'Zones', exact: true }).click();
    await page.getByRole('button', { name: 'Save zones', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'could not be applied' }).waitFor();
    assert.equal(await page.getByRole('status').count(), 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, checks: ['draw marks unsaved', 'save reports applied without restart instruction', 'outlines remain in camera view', 'outlines survive camera reselection', 'application failure is not displayed as success', 'no external requests or page errors'], actual_nvr_tested: false }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
