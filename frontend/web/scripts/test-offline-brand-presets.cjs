const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '../dist-offline');
const cases = [
  ['hikvision', '/Streaming/Channels/102', '/Streaming/Channels/401', true],
  ['dahua', '/cam/realmonitor?channel=1&subtype=1', '/cam/realmonitor?channel=4&subtype=0', true],
  ['axis', '/axis-media/media.amp?camera=1&videocodec=h264', '/axis-media/media.amp?camera=4&videocodec=h264', false],
  ['hanwha-camera', '/profile2/media.smp', '/profile7/media.smp', false],
  ['hanwha-nvr', '/LiveChannel/0/media.smp', '/LiveChannel/3/media.smp', false],
  ['bosch', '/?line=1&inst=2', '/?line=4&inst=1', true],
  ['ipro', '/Src/MediaInput/stream_2', '/Src/MediaInput/stream_1', true],
  ['ipro-multi', '/Src/MediaInput/stream_2/ch_1', '/Src/MediaInput/stream_1/ch_4', true],
  ['vivotek', '/live2.sdp', '/live.sdp', true],
  ['vivotek-profile', '/media2/stream.sdp?profile=', '/media2/stream.sdp?profile=Profile200', false],
  ['avigilon', '/defaultSecondary?streamType=u', '/defaultPrimary?streamType=u', true],
];
let checks = 0, probeUrl = '', cameras = [], writes = 0;
const probeUrls = [];
const status = { site: { name: 'Preset tests', timezone: 'Asia/Kolkata' }, licence: { state: 'active', can_process: true, claims: { camera_limit: 100 } }, runtime: { running: false, cameras: [], advanced_features: {} } };
const handler = require('serve-handler');
const server = http.createServer((request, response) => handler(request, response, { public: root }));
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [], external = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname.slice(5);
      let body = {};
      if (endpoint === 'bootstrap') body = { setup_required: false };
      else if (endpoint === 'login') body = { csrf_token: 'test' };
      else if (endpoint === 'status') body = status;
      else if (endpoint === 'cameras' && request.method() === 'GET') body = cameras;
      else if (endpoint === 'counts' || endpoint === 'events') body = [];
      else if (endpoint === 'probe') { probeUrl = request.postDataJSON().rtsp_url; probeUrls.push(probeUrl); body = { success: false, message: 'Simulated authenticated RTSP 401' }; }
      else if (endpoint.startsWith('cameras') && request.method() !== 'GET') { writes++; body = { ...request.postDataJSON(), id: 'saved' }; }
      else if (endpoint.startsWith('frame/') || endpoint.includes('/snapshot')) return route.fulfill({ status: 404, body: '' });
      else throw new Error(`Unexpected API: ${endpoint}`);
      await route.fulfill({ json: body });
    });
    page.on('request', request => { if (!request.url().startsWith(`http://127.0.0.1:${server.address().port}`)) external.push(request.url()); });
    const signIn = async () => {
      await page.getByLabel('Local username').fill('owner');
      await page.getByLabel('Local password').fill('test-only-password');
      await page.getByRole('button', { name: 'Sign in locally' }).click();
      await page.getByRole('button', { name: 'Cameras', exact: true }).click();
    };
    await page.goto(`http://127.0.0.1:${server.address().port}/offline.html`);
    await signIn();
    const mode = page.getByLabel('Stream setup'), input = page.getByRole('textbox', { name: 'RTSP path', exact: true });
    await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.2');
    await page.getByLabel('NVR username').fill('viewer');
    await page.getByLabel('Actual NVR password').fill('literal#%23');
    for (const [id, initial, changed, streams] of cases) {
      await mode.selectOption(id);
      assert.equal(await input.inputValue(), initial); checks++;
      assert.equal(await input.evaluate(element => element.readOnly), true); checks++;
      assert.equal(await page.getByText(/Manufacturer-documented template/).count(), 1); checks++;
      assert.match(await page.getByRole('link', { name: 'Manufacturer reference (internet required)' }).getAttribute('href'), /^https:\/\//); checks++;
      const channel = page.getByRole('combobox', { name: /^NVR channel/ });
      if (await channel.count()) await channel.selectOption('4');
      if (streams) await page.getByLabel('Video stream').selectOption('01');
      else assert.equal(await page.getByLabel('Video stream').count(), 0);
      if (id === 'hanwha-camera') await page.getByLabel('Configured profile number').fill('7');
      if (id === 'vivotek-profile') await page.getByLabel('Actual media-profile token').fill('Profile200');
      assert.equal(await input.inputValue(), changed); checks++;
      const waiting = page.waitForResponse(response => response.url().endsWith('/api/probe'));
      await page.getByRole('button', { name: 'Test decoded video', exact: true }).click();
      await waiting;
      assert.equal(probeUrl, `rtsp://viewer:literal%23%2523@192.168.1.2:554${changed}`); checks++;
      assert.equal(await page.getByText(/Simulated authenticated RTSP 401/).count(), 1); checks++;
      if (await channel.count()) await channel.selectOption('1');
      if (streams) await page.getByLabel('Video stream').selectOption('02');
    }
    await mode.selectOption('onvif');
    assert.equal(await input.inputValue(), ''); checks++;
    assert.equal(await input.evaluate(element => element.readOnly), false); checks++;
    assert.equal(await page.getByText(/ONVIF is a discovery\/control protocol/).count(), 1); checks++;
    await input.fill('/vendor/provided?video=3');
    await mode.selectOption('custom');
    assert.equal(await input.inputValue(), '/vendor/provided?video=3'); checks++;
    cameras = cases.filter(row => row[0] !== 'vivotek-profile').map(([id, initial], index) => ({ id, name: `Saved ${id}`, enabled: true, detections: {}, people_count_zones: [], inventory_zones: [], exclusion_zones: [], detection_schedule: { enabled: false, start: '09:00', end: '18:00' }, stream_info: { host: '192.168.1.2', port: 554, path: initial, channel: 1, stream_type: 'Substream' } }));
    await page.reload();
    await signIn();
    for (const camera of cameras) {
      await page.getByRole('button', { name: camera.name, exact: true }).click();
      assert.equal(await mode.inputValue(), camera.id); checks++;
      assert.equal(await input.inputValue(), camera.stream_info.path); checks++;
    }
    await page.getByRole('button', { name: 'Saved dahua', exact: true }).click();
    await page.getByRole('combobox', { name: /^NVR channel/ }).selectOption('4');
    await page.getByRole('button', { name: 'Save camera', exact: true }).click();
    await page.getByText(/To change the saved channel\/path/).waitFor();
    assert.equal(writes, 0); checks++;
    assert.deepEqual(errors, []); checks++;
    assert.deepEqual(external, []); checks++;
    assert.equal(probeUrls.length, cases.length); checks++;
    console.log(JSON.stringify({ ok: true, checks, templates: cases.length, qualifications: 'Mocked browser URL/credentials/hydration checks, not hardware interoperability or AI accuracy' }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
