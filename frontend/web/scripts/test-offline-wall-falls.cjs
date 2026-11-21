const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const handler = require('serve-handler');
const { chromium } = require('playwright');

(async () => {
  const server = http.createServer((request, response) => {
    response.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'");
    return handler(request, response, { public: path.resolve(__dirname, '../dist-offline') });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  const posts = [];
  const frames = new Set();
  let failedFrame = false;
  const cameras = [];
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=', 'base64');
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    assert.equal(url.origin, origin);
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (url.pathname.startsWith('/api/frame/')) {
      frames.add(url.pathname);
      return route.fulfill({ status: failedFrame ? 503 : 200, contentType: 'image/png', body: image });
    }
    let result = {};
    if (url.pathname === '/api/bootstrap') result = { setup_required: false };
    if (url.pathname === '/api/status') result = { licence: { state: 'active', can_process: true, claims: { camera_limit: 8 } }, site: { name: 'Wall test', timezone: 'UTC' }, runtime: { running: true, cameras: cameras.map(camera => ({ id: camera.id, connected: true, fps: 2, frame_age_sec: 1, fall_status: { state: 'Outside configured schedule or camera disabled' } })) } };
    if (url.pathname === '/api/events' || url.pathname === '/api/counts') result = [];
    if (url.pathname === '/api/cameras') {
      if (route.request().method() === 'POST') {
        const { rtsp_url, ...saved } = route.request().postDataJSON();
        posts.push({ ...saved, rtsp_url });
        const id = saved.id || `camera-${cameras.length + 1}`;
        const existing = cameras.findIndex(camera => camera.id === id);
        if (existing >= 0) cameras[existing] = { ...saved, id };
        else cameras.push({ ...saved, id });
        result = { id, applied: true, application_error: false, message: 'Saved and applied to monitoring.' };
      } else result = cameras;
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password').fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.102');
    await page.getByLabel('NVR username').fill('viewer');
    await page.getByLabel('Actual NVR password').fill('test#password');
    for (let channel = 1; channel <= 5; channel++) {
      await page.getByLabel('Camera name', { exact: true }).fill(`Channel ${channel}`);
      await page.getByRole('button', { name: 'Save camera', exact: true }).click();
      await page.getByRole('status').filter({ hasText: `Channel ${channel} added as a separate camera` }).waitFor();
      assert.equal(await page.getByLabel('Camera name', { exact: true }).inputValue(), '');
      assert.equal(await page.getByRole('combobox', { name: /^NVR channel/ }).inputValue(), String(channel + 1));
    }
    assert.equal(cameras.length, 5);
    assert.ok(posts.every(post => !post.id));
    assert.ok(posts[3].rtsp_url.endsWith('/402'));
    assert.ok(posts[3].rtsp_url.includes('test%23password@'));
    await page.getByRole('button', { name: 'Channel 1', exact: true }).click();
    await page.getByRole('heading', { name: 'Editing: Channel 1' }).waitFor();
    await page.getByLabel('Camera name', { exact: true }).fill('Entrance renamed');
    await page.getByRole('button', { name: 'Save camera', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Saved and applied to monitoring.' }).waitFor();
    assert.equal(cameras.length, 5);
    assert.equal(posts.at(-1).id, 'camera-1');
    await page.getByRole('button', { name: 'Video wall', exact: true }).click();
    await page.locator('.wall-tile img').nth(4).waitFor();
    assert.equal(await page.locator('.wall-tile').count(), 5);
    assert.equal(frames.size, 5);
    assert.equal(await page.getByText('AI switches · Fall off · Theft off · Shelf off', { exact: true }).count(), 5);
    await page.locator('.wall-analytics > summary').first().click();
    await page.getByText('Fall detection: Outside configured schedule or camera disabled', { exact: true }).first().waitFor();
    assert.equal(await page.getByText('Theft detection: Off for this camera', { exact: true }).count(), 5);
    assert.equal(await page.getByText('Shelf detection: Off for this camera', { exact: true }).count(), 5);
    failedFrame = true;
    await page.locator('.wall-tile .preview-warning').first().waitFor();
    failedFrame = false;
    await page.waitForFunction(() => document.querySelectorAll('.wall-tile .preview-warning').length === 0);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, checks: ['five separate adds', 'automatic next channel', 'name reset', 'hash password encoded once', 'edit preserves camera count', 'five simultaneous wall frames', 'fall schedule visible', 'frame failure visible and recovers', 'mobile no horizontal overflow', 'no external requests or page errors'], real_cameras_tested: false }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
