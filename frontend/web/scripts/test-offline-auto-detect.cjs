const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');
const handler = require('serve-handler');
const server = http.createServer((request, response) => handler(request, response, { public: path.resolve(__dirname, '../dist-offline') }));
let checks = 0, writes = 0, detectionBody, release;
const stages = { network: 'reachable', protocol: 'RTSP response received', credentials: 'failed', path: 'not tested', decode: 'not tested' };
let result = { success: false, failed_stage: 'credentials', path: null, message: 'Authenticated RTSP 401. Check password, RTSP permissions or lockout. No alternate paths tried.', stages, attempts: [{ candidate: 1, status: 401, authenticated_request: true }] };
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage(), errors = [], external = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (!request.url().startsWith(`http://127.0.0.1:${server.address().port}`)) external.push(request.url()); });
    await page.route('**/api/**', async route => {
      const endpoint = new URL(route.request().url()).pathname.slice(5);
      let body = {};
      if (endpoint === 'bootstrap') body = { setup_required: false };
      else if (endpoint === 'login') body = { ok: true };
      else if (endpoint === 'status') body = { site: { name: 'Detection test', timezone: 'UTC' }, licence: { can_process: true, state: 'active' }, runtime: {} };
      else if (['cameras', 'events', 'counts'].includes(endpoint) && route.request().method() === 'GET') body = [];
      else if (endpoint === 'auto-detect') { detectionBody = route.request().postDataJSON(); await new Promise(resolve => { release = resolve; }); body = result; }
      else { writes++; throw new Error(`Unexpected write ${endpoint}`); }
      await route.fulfill({ json: body });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/offline.html`);
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password').fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    await page.getByText('Advanced connection tools', { exact: true }).click();
    await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.2');
    await page.getByLabel('NVR username').fill('viewer');
    await page.getByLabel('Actual NVR password').fill('literal#%23');
    await page.getByLabel('NVR channel / video source').selectOption('3');
    const input = page.getByRole('textbox', { name: 'RTSP path', exact: true });
    const detect = page.getByRole('button', { name: 'Auto-detect / diagnose stream', exact: true });
    const run = async () => {
      release = null;
      await detect.click();
      await page.getByText(/Checking RTSP response, account access/).waitFor();
      assert.equal(await input.isDisabled(), true); checks++;
      while (!release) await new Promise(resolve => setTimeout(resolve, 10));
      const waiting = page.waitForResponse(response => response.url().endsWith('/api/auto-detect'));
      release(); await waiting;
      await page.getByRole('heading', { name: result.success ? 'Video verified — review before saving' : `Stopped at: ${result.failed_stage}`, exact: true }).waitFor();
    };
    await run();
    assert.equal(detectionBody.rtsp_url, 'rtsp://viewer:literal%23%2523@192.168.1.2:554/Streaming/Channels/302'); checks++;
    assert.equal(detectionBody.channel, 3); checks++;
    assert.equal(await input.inputValue(), '/Streaming/Channels/302'); checks++;
    assert.equal(await page.getByText(/Unknown — device did not identify/).count(), 1); checks++;
    await page.getByLabel('Actual NVR password').fill('updated#password');
    assert.equal(await page.getByRole('heading', { name: 'Stopped at: credentials', exact: true }).count(), 0); checks++;
    result = { ...result, success: true, failed_stage: null, path: '/cam/realmonitor?channel=3&subtype=1', message: 'Decoded video verified. Not saved. Confirm intended camera.', stages: { ...stages, credentials: 'accepted for stream', path: 'RTSP description found', decode: 'frame decoded' }, brand_hint: 'dahua' };
    await run();
    assert.equal(await input.inputValue(), result.path); checks++;
    assert.equal(await page.getByLabel('Stream setup').inputValue(), 'custom'); checks++;
    assert.equal(await input.evaluate(element => element.readOnly), false); checks++;
    assert.equal(writes, 0); checks++;
    await input.fill('/different');
    assert.equal(await page.getByRole('heading', { name: 'Video verified — review before saving', exact: true }).count(), 0); checks++;
    assert.deepEqual(errors, []); checks++;
    assert.deepEqual(external, []); checks++;
    console.log(JSON.stringify({ ok: true, checks, scope: 'Mocked browser auto-detection, literal password encoding, failure stages, safe path application; not hardware interoperability' }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
