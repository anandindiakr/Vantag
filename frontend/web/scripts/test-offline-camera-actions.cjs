const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const handler = require('serve-handler');
const { chromium } = require('playwright');

(async () => {
  const server = http.createServer((request, response) => handler(request, response, { public: process.env.OFFLINE_UI_DIRECTORY || path.resolve(__dirname, '../dist-offline') }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const checks = [];
  try {
    for (const state of ['missing', 'expired', 'invalid', 'active', 'grace']) {
      const page = await browser.newPage({ viewport: { width: 1600, height: 810 } });
      const errors = [], probes = [], saves = [];
      let saved = [], rejectSave = false, rejectProbe = false, stallProbe = false;
      const canProcess = ['active', 'grace'].includes(state);
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/api/**', async route => {
        const request = route.request();
        const url = new URL(request.url());
        let result = {};
        if (url.pathname === '/api/bootstrap') result = { setup_required: false };
        else if (url.pathname === '/api/status') result = { licence: { state, can_process: canProcess, reason: canProcess ? '' : 'Import a valid signed entitlement for this device.' }, site: { name: 'Camera action regression', timezone: 'Asia/Kolkata' }, runtime: { cameras: [] } };
        else if (url.pathname === '/api/counts') result = [];
        else if (url.pathname === '/api/cameras') {
          if (request.method() === 'POST') {
            saves.push(request.postDataJSON());
            if (rejectSave) return route.fulfill({ status: 403, json: { detail: 'A valid signed offline entitlement is required' } });
            const { rtsp_url, ...camera } = request.postDataJSON();
            saved = [...saved, { ...camera, id: String(saved.length + 1) }];
            result = { id: String(saved.length), applied: false, application_error: false, message: 'Saved. Monitoring is stopped.' };
          } else result = saved;
        } else if (url.pathname === '/api/probe') {
          probes.push(request.postDataJSON());
          if (stallProbe) return;
          result = { success: !rejectProbe, message: rejectProbe ? 'RTSP authentication rejected by device' : 'Video frame decoded' };
        }
        await route.fulfill({ json: result });
      });
      await page.goto(`${origin}/offline.html`);
      await page.getByLabel('Local username').fill('test-owner');
      await page.getByLabel('Local password', { exact: true }).fill('test-password-only');
      await page.getByRole('button', { name: 'Sign in locally' }).click();
      await page.getByRole('button', { name: 'Cameras', exact: true }).click();
      await page.getByText(`Licence: ${state}`, { exact: true }).waitFor();
      const test = page.getByRole('button', { name: 'Test decoded video', exact: true });
      const save = page.getByRole('button', { name: 'Save camera', exact: true });
      assert.equal(await test.isEnabled(), true, `${state}: camera test must explain why it cannot proceed instead of silently disabling`);
      assert.equal(await save.isEnabled(), true, `${state}: save must explain why it cannot proceed instead of silently disabling`);
      if (!canProcess) {
        await page.getByRole('region', { name: 'Camera activation required' }).waitFor();
        await test.click();
        await page.getByRole('alert').filter({ hasText: /signed.*entitlement/i }).last().waitFor();
        assert.equal(probes.length, 0);
        await page.getByLabel('Camera name', { exact: true }).fill('Unlicensed test');
        await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.120');
        await save.click();
        assert.equal(saves.length, 0);
        await page.getByRole('button', { name: 'Open device activation', exact: true }).click();
        await page.getByRole('heading', { name: 'Offline entitlement', exact: true }).waitFor();
        await page.getByRole('button', { name: 'Cameras', exact: true }).click();
        assert.equal(await page.getByLabel('Camera name', { exact: true }).inputValue(), 'Unlicensed test');
        assert.equal(await page.getByLabel('NVR / camera LAN IP').inputValue(), '192.168.1.120');
        checks.push(`${state}: visible licence reason, actionable buttons and activation navigation without bypass`);
      } else {
        await save.click();
        await page.getByRole('alert').filter({ hasText: /Camera name/ }).waitFor();
        assert.equal(saves.length, 0);
        await page.getByLabel('Camera name', { exact: true }).fill('First channel');
        await page.getByLabel('NVR / camera LAN IP').fill('192.168.1.120');
        await page.getByLabel('NVR username').fill('admin');
        await page.getByLabel('Actual NVR password').fill('Demo#@%:test');
        await page.getByLabel('Stream setup').selectOption('dahua');
        await page.getByLabel('Video stream').selectOption('01');
        await test.click();
        await page.getByText(/This confirms video decoding, not AI accuracy/).waitFor();
        assert.equal(probes[0].rtsp_url, 'rtsp://admin:Demo%23%40%25%3Atest@192.168.1.120:554/cam/realmonitor?channel=1&subtype=0');
        rejectProbe = true;
        await test.click();
        await page.getByRole('alert').filter({ hasText: 'RTSP authentication rejected' }).waitFor();
        await save.click();
        await page.getByRole('status').filter({ hasText: 'First channel added as a separate camera' }).waitFor();
        assert.equal(saves.length, 1);
        assert.equal(saves[0].rtsp_url, probes[0].rtsp_url);
        await page.getByRole('button', { name: 'New camera', exact: true }).click();
        const ip = page.getByLabel('NVR / camera LAN IP');
        await page.waitForFunction(() => document.activeElement?.getAttribute('name') === 'ip');
        assert.equal(await ip.inputValue(), '');
        assert.equal(await page.getByLabel('Actual NVR password').inputValue(), '');
        const box = await ip.boundingBox();
        assert.ok(box.y >= 0 && box.y + box.height < 810, 'New camera brings editable IP field into view');
        await ip.fill('192.168.1.121');
        assert.equal(await ip.inputValue(), '192.168.1.121');
        await page.getByLabel('Camera name', { exact: true }).fill('Second channel');
        await page.getByLabel('NVR username').fill('admin');
        await page.getByLabel('Actual NVR password').fill('Second#password');
        rejectSave = true;
        await save.click();
        await page.getByRole('alert').filter({ hasText: 'A valid signed offline entitlement is required' }).waitFor();
        assert.equal(await ip.inputValue(), '192.168.1.121');
        assert.equal(await save.isEnabled(), true);
        rejectSave = false;
        await save.click();
        await page.getByRole('status').filter({ hasText: 'Second channel added as a separate camera' }).waitFor();
        assert.equal(saves.at(-1).id, undefined);
        assert.equal(saved.length, 2);
        await ip.fill('192.168.1.122');
        await page.getByLabel('NVR username').fill('admin');
        await page.getByLabel('Actual NVR password').fill('Pending#request');
        await page.evaluate(() => {
          const original = window.setTimeout.bind(window);
          window.setTimeout = (callback, delay, ...args) => original(callback, delay === 60000 ? 50 : delay, ...args);
        });
        stallProbe = true;
        await test.click();
        await page.getByRole('alert').filter({ hasText: 'request timed out' }).waitFor();
        assert.equal(await ip.inputValue(), '192.168.1.122');
        assert.equal(await test.isEnabled(), true);
        assert.equal(await save.isEnabled(), true);
        await page.getByRole('button', { name: 'New camera', exact: true }).click();
        await page.waitForFunction(() => document.activeElement?.getAttribute('name') === 'ip');
        assert.deepEqual(await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) })), { local: [], session: [] });
        checks.push(`${state}: save validation, decoded test, Dahua path, # encoding, failure recovery, new-camera IP focus/editing, second save and hung-request timeout recovery`);
      }
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log(JSON.stringify({ ok: true, checks, real_camera_tested: false }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
