const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { transformSync } = require('esbuild');

(async () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../src/offlineApi.ts'), 'utf8');
  const code = transformSync(source, { loader: 'ts', format: 'cjs' }).code;
  const exports = {};
  let fetchImplementation, scheduledTimeout, expired = 0, calls = 0;
  const context = {
    module: { exports }, exports, AbortController, Event, Error, TypeError,
    window: { dispatchEvent: () => { expired++; }, setTimeout, clearTimeout },
    setTimeout: (callback, duration) => { scheduledTimeout = duration; return setTimeout(callback, 20); },
    clearTimeout,
    fetch: (...args) => { calls++; return fetchImplementation(...args); },
  };
  vm.runInNewContext(code, context);
  const api = context.module.exports.localApi;
  fetchImplementation = (_url, options) => new Promise((resolve, reject) => {
    options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  });
  await assert.rejects(Promise.race([api('probe', {}), new Promise((_, reject) => setTimeout(() => reject(new Error('Request remained stuck without timeout')), 200))]), /timed out/i);
  assert.ok(scheduledTimeout >= 30000 && scheduledTimeout <= 120000);
  assert.equal(calls, 1, 'No automatic retries against NVR');
  fetchImplementation = async () => ({ ok: false, status: 422, json: async () => ({ detail: [{ loc: ['body', 'name'], msg: 'String should have at least 1 character', input: 'never-display-password' }] }) });
  await assert.rejects(api('cameras', {}), error => /name.*at least 1 character/.test(error.message) && !error.message.includes('never-display-password'));
  fetchImplementation = async () => { throw new TypeError('Failed to fetch'); };
  await assert.rejects(api('probe', {}), /local agent|local service/i);
  fetchImplementation = async () => ({ ok: false, status: 401, json: async () => ({}) });
  await assert.rejects(api('status'), /session.*expired|sign in locally/i);
  assert.equal(expired, 1);
  fetchImplementation = async () => ({ ok: true, status: 200, json: async () => ({ success: true }) });
  assert.equal((await api('probe', {})).success, true);
  const controller = new AbortController();
  controller.abort();
  fetchImplementation = async (_url, options) => {
    if (options.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    return { ok: true, json: async () => ({}) };
  };
  await assert.rejects(api('incidents', undefined, 'GET', controller.signal), error => error.name === 'AbortError');
  console.log(JSON.stringify({ ok: true, checks: ['bounded requests release busy state', 'no automatic retry', 'safe structured validation detail', 'local service failure guidance', 'expired session guidance', 'success preserved', 'caller cancellation preserved'] }));
})().catch(error => { console.error(error); process.exitCode = 1; });
