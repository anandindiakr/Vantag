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
  const searches = [];
  let reviewed = false;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    let json = {};
    if (url.pathname === '/api/bootstrap') json = { setup_required: false };
    if (url.pathname === '/api/status') json = { site: { name: 'Report office', timezone: 'Asia/Singapore' }, licence: { state: 'expired', can_process: false }, runtime: {} };
    if (url.pathname === '/api/cameras') json = [{ id: 'office', name: 'Office', detections: {} }];
    if (url.pathname === '/api/events' || url.pathname === '/api/counts') json = [];
    if (url.pathname === '/api/incidents') {
      searches.push(Object.fromEntries(url.searchParams));
      json = { items: [{ event_id: 'incident-old-001', camera_id: 'office', event_type: 'fall_detected', recorded_at: 1795222800, confidence: 0.82, people_visible: null, verification_state: 'not_verified_offline', review: { state: reviewed ? 'confirmed' : 'candidate', note: reviewed ? 'Checked camera evidence' : '' }, evidence: {} }], total: 215, page: Number(url.searchParams.get('page') || 1), page_size: Number(url.searchParams.get('page_size') || 50), timezone: 'Asia/Singapore', generated_at: 1795222800 };
    }
    if (url.pathname === '/api/incidents/incident-old-001/review') {
      assert.equal(route.request().postDataJSON().state, 'confirmed');
      reviewed = true;
      json = { ok: true };
    }
    await route.fulfill({ json });
  });
  try {
    await page.goto(`${origin}/offline.html`);
    await page.getByLabel('Local username').fill('owner');
    await page.getByLabel('Local password', { exact: true }).fill('test-only-password');
    await page.getByRole('button', { name: 'Sign in locally' }).click();
    await page.getByRole('button', { name: 'Incidents', exact: true }).click();
    await page.getByRole('heading', { name: 'Incident report', exact: true }).waitFor();
    await page.getByText('incident-old-001', { exact: true }).waitFor();
    await page.getByLabel('Incident type').selectOption('fall_detected');
    await page.getByLabel('Minimum people visible').fill('5');
    await page.getByLabel('Search saved records').fill('old');
    await page.getByRole('button', { name: 'Search archive', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('[data-report-total]')?.textContent.includes('215'));
    await page.getByText('Review this record', { exact: true }).click();
    await page.getByLabel('Review state for incident-old-001').selectOption('confirmed');
    await page.getByLabel('Review note for incident-old-001').fill('Checked camera evidence');
    await page.getByRole('button', { name: 'Save review', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Review saved' }).waitFor();
    await page.getByRole('button', { name: 'Prepare print / PDF', exact: true }).click();
    await page.getByRole('button', { name: 'Print / Save PDF', exact: true }).waitFor();
    assert.ok(searches.some(query => query.q === 'old' && query.min_people === '5' && query.event_type === 'fall_detected'));
    assert.ok(searches.some(query => query.page_size === '1000'));
    await page.emulateMedia({ media: 'print' });
    assert.equal(await page.locator('.console-shell > aside').isVisible(), false);
    assert.ok((await page.locator('.incident-report').innerText()).includes('Not measured'));
    assert.ok((await page.locator('.incident-report').innerText()).includes('Operator confirmed'));
    await page.emulateMedia({ media: 'screen' });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, searchable_archive: true, review_and_print: true, works_after_expiry: true }));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
