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
  page.on('pageerror', error => errors.push(error.message));
  let runtime = { running: true, detector: { architecture: 'yolo26', is_preferred: true, provider: 'CPUExecutionProvider', inference_count: 15, last_inference_ms: 91.4, model_path: 'C:\\Users\\PrivateOwner\\models\\secret.onnx' }, calibration: { inference_ms: 85, fallback_reason: 'cuda: RuntimeError' }, cameras: [{ id: 'one', connected: true, fps: 4, frame_age_sec: 0.8 }], advanced_features: { assistant: 'unavailable: no qualified local assistant bundled' } };
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    const responses = {
      '/api/bootstrap': { setup_required: false }, '/api/login': {}, '/api/cameras': [], '/api/events': [], '/api/counts': [],
      '/api/status': { site: { name: 'Demo site', timezone: 'UTC' }, licence: { state: 'active', can_process: true, claims: { licence_type: 'internal_demo', expires_at: null, camera_limit: 8 } }, runtime },
    };
    return route.fulfill({ json: responses[pathname] || {} });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password', { exact: true }).fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Licence & health', exact: true }).click();
    const health = page.getByRole('region', { name: 'Runtime health summary' });
    await health.getByText('CPU (ONNX Runtime)', { exact: true }).waitFor();
    await health.getByText('YOLO26 architecture verified', { exact: true }).waitFor();
    assert.equal(await page.locator('pre:visible').count(), 0);
    assert.equal(await page.locator('details:has-text("Technical details (for support)")').getAttribute('open'), null);
    await page.getByText('Technical details (for support)', { exact: true }).click();
    assert.ok(!(await page.locator('main').textContent()).includes('PrivateOwner'));
    assert.ok(!(await page.locator('main').textContent()).includes('secret.onnx'));
    assert.ok((await health.innerText()).includes('CPU fallback'));
    await page.screenshot({ path: path.resolve(__dirname, '../../../windows_agent/build/health-summary-verified.png'), fullPage: true });
    runtime = { running: false, error: 'Failed at C:\\Users\\PrivateOwner\\data', detector: {}, cameras: [] };
    await health.getByText('Needs attention', { exact: true }).waitFor();
    assert.ok(!(await health.textContent()).includes('PrivateOwner'));
    await health.getByText('Not verified', { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, checks: ['friendly health', 'verified architecture label', 'collapsed support details', 'allowlisted diagnostics without paths', 'visible CPU fallback', 'error and stopped states', 'mobile width'], actual_inference_tested: false }));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
