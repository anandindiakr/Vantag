const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');
const handler = require('serve-handler');
const server = http.createServer((request, response) => handler(request, response, { public: path.resolve(__dirname, '../dist-offline') }));
let checks = 0, writes = 0, rejected = true, testBody;
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', async route => {
      const endpoint = new URL(route.request().url()).pathname.slice(5);
      let body = {};
      if (endpoint === 'bootstrap') body = { setup_required: false };
      else if (endpoint === 'login') body = { ok: true };
      else if (endpoint === 'status') body = { site: { name: 'ONVIF test', timezone: 'UTC' }, licence: { can_process: true, state: 'active' }, runtime: {} };
      else if (['cameras', 'events', 'counts'].includes(endpoint)) body = [];
      else if (endpoint === 'onvif/profiles') {
        testBody = route.request().postDataJSON();
        if (rejected) return route.fulfill({ status: 400, json: { detail: 'ONVIF account rejected. Check media permissions.' } });
        body = { profiles: [{ token: 'actual-profile', name: 'Meeting Room', source: 'source-5', width: '640', height: '360' }], media_endpoint: 'http://192.168.1.2/onvif/media', onvif_port: 80, message: 'Device-reported profiles read. Nothing saved.', clock_note: 'Device clock checked.' };
      } else if (endpoint === 'onvif/test-profile') {
        testBody = route.request().postDataJSON();
        body = { success: true, path: '/real/profile5', port: 8554, message: 'Profile decoded. Review before saving.' };
      } else { writes++; throw new Error(`Unexpected write ${endpoint}`); }
      await route.fulfill({ json: body });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/offline.html`);
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password', { exact: true }).fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    await page.getByText('Advanced connection tools', { exact: true }).click();
    await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.2');
    await page.getByLabel('NVR username').fill('viewer');
    const password = page.getByLabel('Actual NVR password', { exact: true });
    await password.fill('literal#%23');
    const toggle = page.getByRole('button', { name: 'Show password characters' });
    const style = await toggle.evaluate(element => { const css = getComputedStyle(element); return { color: css.color, height: element.getBoundingClientRect().height }; });
    assert.equal(style.color, 'rgb(248, 250, 252)'); checks++;
    assert.ok(style.height >= 44); checks++;
    await toggle.click();
    assert.equal(await password.getAttribute('type'), 'text'); checks++;
    await page.getByRole('button', { name: 'Hide password characters' }).click();
    assert.equal(await password.getAttribute('type'), 'password'); checks++;
    const detectPanel = page.getByRole('region', { name: 'Automatic stream detection' });
    await page.getByLabel('NVR / camera LAN IP').fill('');
    await page.getByRole('button', { name: 'Auto-detect / diagnose stream' }).click();
    await detectPanel.getByRole('alert').waitFor(); checks++;
    assert.match(await detectPanel.getByRole('alert').textContent(), /Enter the NVR/); checks++;
    await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.2');
    const profilesPanel = page.getByRole('region', { name: 'Device-reported stream profiles', exact: true });
    await page.getByRole('button', { name: 'Read device profiles', exact: true }).click();
    await profilesPanel.getByRole('alert').waitFor();
    assert.match(await profilesPanel.getByRole('alert').textContent(), /account rejected/); checks++;
    assert.equal(testBody.rtsp_url, 'rtsp://viewer:literal%23%2523@192.168.1.2:554/Streaming/Channels/102'); checks++;
    rejected = false;
    await page.getByRole('button', { name: 'Read device profiles', exact: true }).click();
    await page.getByLabel('Device video source / profile').selectOption('actual-profile');
    assert.equal(await page.getByLabel('ONVIF HTTP service port (0 = discover)').inputValue(), '80'); checks++;
    await page.getByRole('button', { name: 'Test selected profile', exact: true }).click();
    await profilesPanel.getByText('Profile decoded. Review before saving.', { exact: true }).waitFor();
    assert.equal(testBody.profile_token, 'actual-profile'); checks++;
    assert.equal(await page.getByLabel('RTSP path', { exact: true }).inputValue(), '/real/profile5'); checks++;
    assert.equal(await page.getByLabel('RTSP port', { exact: true }).inputValue(), '8554'); checks++;
    assert.equal(await page.getByLabel('Stream setup').inputValue(), 'custom'); checks++;
    assert.equal(writes, 0); checks++;
    assert.deepEqual(errors, []); checks++;
    console.log(JSON.stringify({ ok: true, checks, scope: 'Mocked ONVIF profile flow, inline feedback, visible password controls; not hardware acceptance' }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
