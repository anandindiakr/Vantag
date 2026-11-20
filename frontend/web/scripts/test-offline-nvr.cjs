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
  const external = [];
  const probes = [];
  const saves = [];
  let saved = [];
  let decoded = false;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) { external.push(url.origin); return route.abort(); }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    let result = {};
    switch (url.pathname) {
      case '/api/bootstrap': result = { setup_required: false }; break;
      case '/api/status': result = { licence: { state: 'active', can_process: true }, site: { name: 'Isolated NVR UI test', timezone: 'UTC' }, runtime: { cameras: [] } }; break;
      case '/api/cameras':
        if (request.method() === 'POST') {
          const body = request.postDataJSON();
          saves.push(body);
          const { rtsp_url, ...camera } = body;
          saved = [{ ...camera, id: 'test-camera' }];
          result = { id: 'test-camera', applied: false, application_error: false, message: 'Saved. Monitoring is stopped; start it on Overview when ready.' };
        } else result = saved;
        break;
      case '/api/events': case '/api/counts': result = []; break;
      case '/api/probe':
        probes.push(request.postDataJSON());
        result = { success: decoded, message: decoded ? 'Video frame decoded' : 'No video frame received. Check NVR authentication, permissions, channel and codec.' };
        break;
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('isolated-test');
    await page.getByLabel('Local password').fill('not-a-real-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    const test = () => page.getByRole('button', { name: 'Test decoded video', exact: true }).click();
    await test();
    await page.getByRole('alert').filter({ hasText: 'Enter the NVR LAN IP' }).waitFor();
    assert.equal(probes.length, 0);
    await page.getByLabel('NVR / camera LAN IP').fill('999.1.1.1');
    await test();
    await page.getByRole('alert').filter({ hasText: 'valid NVR IPv4' }).waitFor();
    assert.equal(probes.length, 0);
    await page.getByLabel('Camera name', { exact: true }).fill('Test NVR');
    await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.102');
    await page.getByLabel('NVR username').fill('admin');
    await page.getByLabel('Actual NVR password').fill('Test#@%:secret');
    await page.getByLabel(/^NVR channel/).selectOption('2');
    assert.equal(await page.locator('input[name=path]').inputValue(), '/Streaming/Channels/202');
    await page.getByLabel('Video stream').selectOption('01');
    await test();
    await page.getByRole('alert').filter({ hasText: 'No video frame received' }).waitFor();
    assert.equal(probes[0].rtsp_url, 'rtsp://admin:Test%23%40%25%3Asecret@192.168.1.102:554/Streaming/Channels/201');
    assert.equal(await page.locator('.success').count(), 0);
    await page.getByRole('button', { name: 'Save camera', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Test NVR added as a separate camera. Saved. Monitoring is stopped' }).waitFor();
    assert.equal(saves[0].rtsp_url, probes[0].rtsp_url);
    assert.equal(await page.getByLabel('NVR / camera LAN IP').inputValue(), '192.168.1.102');
    assert.equal(await page.getByLabel('NVR username').inputValue(), 'admin');
    assert.equal(await page.getByLabel('Actual NVR password').inputValue(), 'Test#@%:secret');
    assert.equal(await page.locator('input[name=path]').inputValue(), '/Streaming/Channels/301');
    decoded = true;
    await test();
    await page.getByRole('status').filter({ hasText: 'This confirms video decoding, not AI accuracy' }).waitFor();
    await page.getByRole('button', { name: 'New camera', exact: true }).click();
    assert.equal(await page.getByLabel('Actual NVR password').inputValue(), '');
    await page.getByRole('button', { name: 'Test NVR', exact: true }).click();
    assert.equal(await page.getByLabel('Actual NVR password').inputValue(), '');
    await page.getByRole('button', { name: 'Save camera', exact: true }).click();
    await page.getByText('Saved. Monitoring is stopped; start it on Overview when ready.', { exact: true }).waitFor();
    assert.equal(saves[1].rtsp_url, '');
    await page.getByLabel('Actual NVR password').fill('memory-only');
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await page.getByRole('button', { name: 'Sign in locally' }).waitFor();
    await page.getByLabel('Local username').fill('isolated-test');
    await page.getByLabel('Local password').fill('not-a-real-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Cameras', exact: true }).waitFor();
    assert.equal(await page.getByLabel('Actual NVR password').inputValue(), '');
    assert.deepEqual(await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) })), { local: [], session: [] });
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ ok: true, checks: ['blank and invalid IP blocked before API', 'Hikvision channel/stream path', 'special characters encoded once', 'failed decode is not success', 'save preserves entered details', 'decoded response instructions', 'saved credentials never exposed', 'edit without connection preserves encrypted stream', 'logout clears password', 'no browser storage or external requests'], actual_nvr_tested: false }, null, 2));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
