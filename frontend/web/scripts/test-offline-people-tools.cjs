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
  const mutations = [];
  let settings = { capture_enabled: false, recognition_enabled: false, retention_days: 7 };
  const seed = { id: 'seed', camera_id: 'entrance', first_seen: 1795222800, last_seen: 1795222810 };
  const target = { id: 'target', camera_id: 'office', first_seen: 1795222820, last_seen: 1795222830, appearance_score: .9 };
  let linked = false;
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith(origin) && !request.url().startsWith('data:')) external.push(request.url()); });
  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (!['GET', 'HEAD'].includes(request.method())) mutations.push({ path: url.pathname, body: request.postDataJSON() });
    let json = {};
    if (url.pathname === '/api/bootstrap') json = { setup_required: false };
    if (url.pathname === '/api/status') json = { site: { name: 'People test', timezone: 'Asia/Singapore' }, licence: { state: 'active', can_process: true }, runtime: {} };
    if (url.pathname === '/api/cameras') json = [{ id: 'entrance', name: 'Entrance' }, { id: 'office', name: 'Office' }];
    if (url.pathname === '/api/counts') json = [];
    if (url.pathname === '/api/people/settings') {
      if (request.method() === 'POST') settings = request.postDataJSON();
      json = { settings, status: { error: '' }, faces: { available: false, error: 'Models not yet checked' } };
    }
    if (url.pathname === '/api/people/staff') json = [];
    if (url.pathname === '/api/people/observations') json = { items: [seed, target], total: 2, page: 1, page_size: 30 };
    if (url.pathname.endsWith('/candidates')) json = { items: [{ ...target, review_state: linked ? 'confirmed' : 'unreviewed' }], searched: 1, truncated: false };
    if (url.pathname.endsWith('/links')) { linked = request.postDataJSON().state === 'confirmed'; json = { items: linked ? [seed, target] : [seed] }; }
    if (url.pathname.endsWith('/timeline')) json = { items: linked ? [seed, target] : [seed] };
    if (url.pathname.endsWith('/thumbnail')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="180"><rect width="120" height="180" fill="gray"/></svg>' });
    await route.fulfill({ json });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password', { exact: true }).fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'People tools', exact: true }).click();
    await page.getByRole('heading', { name: 'People tools · local and opt-in' }).waitFor();
    assert.equal(await page.getByLabel('Save local person observations').isChecked(), false);
    await page.getByLabel('Save local person observations').check();
    await page.getByLabel('I am authorised').check();
    await page.getByRole('button', { name: 'Save people-tool settings' }).click();
    await page.getByRole('status').filter({ hasText: 'Completed locally' }).waitFor();
    assert.ok(mutations.some(item => item.path === '/api/people/settings' && item.body.capture_enabled && item.body.authorised));
    await page.getByRole('button', { name: 'Find across cameras' }).first().click();
    const review = page.getByRole('region', { name: 'Cross-camera tracking review' });
    await review.getByText('Appearance score: 0.900 · unreviewed').waitFor();
    assert.equal(linked, false);
    await review.getByRole('button', { name: 'Confirm link', exact: true }).click();
    await review.getByText('Appearance score: 0.900 · confirmed').waitFor();
    assert.equal(linked, true);
    await review.getByRole('button', { name: 'Reject link', exact: true }).click();
    await review.getByText('Appearance score: 0.900 · unreviewed').waitFor();
    assert.equal(linked, false);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ ok: true, opt_in_settings: true, anonymous_search: true, explicit_links_and_rejection: true, mobile: true, external_requests: 0 }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
