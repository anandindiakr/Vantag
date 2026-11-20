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
  page.setDefaultTimeout(10000);
  const posts = [];
  const errors = [];
  const camera = (id, name, host, channel, streamPath) => ({ id, name, enabled: true, detections: {}, detection_schedule: { enabled: false, start: '09:00', end: '18:00' }, people_count_zones: [], inventory_zones: [], exclusion_zones: [], stream_info: { host, port: 554, channel, path: streamPath, stream_type: 'Substream' } });
  const cameras = [camera('one', 'Meeting Room', '192.168.50.79', 4, '/Streaming/Channels/402'), camera('two', 'Office', '192.168.50.84', 1, '/cam/realmonitor?channel=1&subtype=1')];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    assert.equal(url.origin, origin);
    if (!url.pathname.startsWith('/api/')) return route.continue();
    let result = {};
    if (url.pathname === '/api/bootstrap') result = { setup_required: false };
    if (url.pathname === '/api/status') result = { licence: { state: 'active', can_process: true }, site: { name: 'Channel tests', timezone: 'UTC' }, runtime: {} };
    if (url.pathname === '/api/counts' || url.pathname === '/api/events') result = [];
    if (url.pathname === '/api/cameras') {
      if (route.request().method() === 'POST') {
        const saved = route.request().postDataJSON();
        posts.push(saved);
        result = { id: saved.id, applied: false, application_error: false, message: 'Saved for next start' };
      } else result = cameras;
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password').fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    await page.getByText('192.168.50.79:554 · Channel 4 · Substream · /Streaming/Channels/402', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Meeting Room', exact: true }).click();
    assert.equal(await page.getByRole('combobox', { name: /^NVR channel/ }).inputValue(), '4');
    assert.equal(await page.getByRole('textbox', { name: 'RTSP path', exact: true }).inputValue(), '/Streaming/Channels/402');
    await page.getByRole('button', { name: 'Save camera', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Saved for next start' }).waitFor();
    assert.equal(posts.length, 1);
    assert.equal(posts[0].rtsp_url, '');
    assert.equal(posts[0].stream_info, undefined);
    await page.getByRole('combobox', { name: /^NVR channel/ }).selectOption('5');
    await page.getByRole('button', { name: 'Save camera', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'To change the saved channel/path' }).waitFor();
    assert.equal(posts.length, 1);
    await page.getByRole('button', { name: 'Office', exact: true }).click();
    assert.equal(await page.getByLabel('Stream setup').inputValue(), 'dahua');
    assert.equal(await page.getByRole('combobox', { name: /^NVR channel/ }).inputValue(), '1');
    assert.equal(await page.getByRole('textbox', { name: 'RTSP path', exact: true }).inputValue(), '/cam/realmonitor?channel=1&subtype=1');
    await page.getByRole('combobox', { name: /^NVR channel/ }).selectOption('5');
    assert.equal(await page.getByRole('textbox', { name: 'RTSP path', exact: true }).inputValue(), '/cam/realmonitor?channel=5&subtype=1');
    await page.getByLabel('Video stream').selectOption('01');
    assert.equal(await page.getByRole('textbox', { name: 'RTSP path', exact: true }).inputValue(), '/cam/realmonitor?channel=5&subtype=0');
    await page.getByLabel('NVR / camera LAN IP').fill('192.168.50.84');
    await page.getByLabel('NVR username').fill('viewer');
    await page.getByLabel('Actual NVR password').fill('test#password');
    await page.getByRole('button', { name: 'Save camera', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Saved for next start' }).waitFor();
    assert.equal(posts[1].rtsp_url, 'rtsp://viewer:test%23password@192.168.50.84:554/cam/realmonitor?channel=5&subtype=0');
    await page.getByRole('button', { name: 'Licence & health', exact: true }).click();
    await page.getByText('Incomplete: legacy stationary-person dwell heuristic', { exact: false }).waitFor();
    await page.getByText('Candidate heuristics only:', { exact: false }).waitFor();
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, checks: 15, real_camera_accuracy_tested: false }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
