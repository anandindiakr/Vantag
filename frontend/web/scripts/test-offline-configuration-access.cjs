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
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  page.setDefaultTimeout(3000);
  const errors = [];
  const posts = [];
  let running = false;
  let previewFails = false;
  let camera = { id: 'pantry', name: 'Pantry', enabled: true, detections: {}, detection_schedule: { enabled: false, start: '09:00', end: '18:00' }, inventory_zones: [], people_count_zones: [], restricted_zones: [], exclusion_zones: [], stream_info: { host: '192.168.1.10', port: 554, path: '/Streaming/Channels/102', channel: 1, stream_type: 'Substream' } };
  const second = { ...camera, id: 'office', name: 'Office' };
  const image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=';
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.protocol === 'data:' || url.protocol === 'blob:') return route.continue();
    assert.equal(url.origin, origin);
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (url.pathname.startsWith('/api/frame/')) return route.fulfill({ status: 404, json: { detail: 'No recent video frame' } });
    let json = {};
    if (route.request().method() === 'POST') posts.push({ path: url.pathname, body: route.request().postDataJSON() });
    if (url.pathname === '/api/bootstrap') json = { setup_required: false };
    if (url.pathname === '/api/status') json = { site: { name: 'Configuration test', timezone: 'UTC' }, licence: { state: 'active', can_process: true }, runtime: { running, cameras: [] } };
    if (url.pathname === '/api/cameras') {
      if (route.request().method() === 'POST') {
        camera = { ...camera, ...route.request().postDataJSON() };
        json = { id: camera.id, applied: running, application_error: false, message: running ? 'Saved and applied to monitoring.' : 'Saved. Monitoring is stopped; start it when ready.' };
      } else json = [camera, second];
    }
    if (url.pathname === '/api/cameras/pantry/test') json = previewFails ? { success: false, message: 'RTSP access rejected. Check media permissions.' } : { success: true, thumbnail: image, message: 'Video frame decoded' };
    if (url.pathname === '/api/events' || url.pathname === '/api/counts') json = [];
    return route.fulfill({ json });
  });
  try {
    await page.goto(`${origin}/offline.html`, { timeout: 30000 });
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password', { exact: true }).fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    const check = process.env.CHECK || 'all';
    if (check === 'all' || check === 'help') {
      await page.getByRole('button', { name: 'Help with this screen', exact: true }).click();
      const close = page.getByRole('button', { name: 'Close help', exact: true });
      await close.click();
      assert.equal(await close.count(), 0);
      await page.getByRole('button', { name: 'Help with this screen', exact: true }).click();
      await page.keyboard.press('Escape');
      assert.equal(await close.count(), 0);
      assert.equal(await page.getByRole('button', { name: 'Help with this screen', exact: true }).getAttribute('aria-expanded'), 'false');
    }
    if (check === 'all' || check === 'zones') {
      await page.getByRole('button', { name: 'Zones', exact: true }).click();
      await page.locator('.panel select').first().selectOption('pantry');
      const preview = page.locator('.preview').first();
      assert.ok((await preview.boundingBox()).height >= 180, 'Missing video must not collapse the editor');
      assert.equal(await page.locator('canvas').count(), 0, 'Do not draw over missing video');
      await page.getByRole('button', { name: 'Load camera image', exact: true }).click();
      await page.getByText('Setup snapshot', { exact: false }).waitFor();
      const canvas = page.getByLabel('Drag to draw a rectangular zone over the camera image');
      await canvas.waitFor();
      const rect = await canvas.boundingBox();
      await page.mouse.move(rect.x + rect.width * 0.2, rect.y + rect.height * 0.2);
      await page.mouse.down();
      await page.mouse.move(rect.x + rect.width * 0.7, rect.y + rect.height * 0.7);
      await page.mouse.up();
      await page.getByRole('button', { name: 'Save zones', exact: true }).click();
      await page.getByRole('status').filter({ hasText: 'Monitoring is stopped' }).waitFor();
      assert.equal(camera.inventory_zones.length, 1);
      assert.equal(posts.filter(post => post.path.startsWith('/api/monitoring/')).length, 0);
      previewFails = true;
      await page.getByRole('button', { name: 'Load camera image', exact: true }).click();
      await page.getByRole('alert').filter({ hasText: 'RTSP access rejected' }).waitFor();
      await page.getByLabel('Camera', { exact: true }).selectOption('office');
      assert.equal(await page.locator('canvas').count(), 0, 'Do not reuse a different camera snapshot');
    }
    if (check === 'all' || check === 'ai') {
      running = true;
      await page.getByRole('button', { name: 'AI functions', exact: true }).click();
      await page.getByLabel('Camera', { exact: true }).selectOption('pantry');
      await page.getByLabel('Fall detection', { exact: true }).check();
      await page.getByLabel('Theft / shoplifting candidates', { exact: true }).check();
      await page.getByRole('button', { name: 'Save AI functions', exact: true }).click();
      await page.getByRole('status').filter({ hasText: 'Saved and applied' }).waitFor();
      assert.equal(camera.detections.fall_detected, true);
      assert.equal(camera.detections.shoplifting, true);
      const save = posts.filter(post => post.path === '/api/cameras').at(-1);
      assert.equal(save.body.rtsp_url, '', 'AI edits preserve protected credentials');
      assert.equal(posts.filter(post => post.path === '/api/monitoring/stop').length, 0);
      await page.getByLabel('Camera', { exact: true }).selectOption('office');
      await page.getByLabel('Camera', { exact: true }).selectOption('pantry');
      assert.equal(await page.getByLabel('Fall detection', { exact: true }).isChecked(), true);
      await page.getByRole('button', { name: 'Video wall', exact: true }).click();
      const button = page.getByRole('button', { name: 'Edit AI Pantry', exact: true });
      await button.scrollIntoViewIfNeeded();
      assert.ok(await button.evaluate(element => getComputedStyle(element).opacity === '1'));
      await button.click();
      await page.getByRole('heading', { name: 'AI functions for Pantry', exact: true }).waitFor();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, check, real_ai_accuracy_tested: false }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
