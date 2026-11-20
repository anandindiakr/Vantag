const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/pages/CamerasManage.tsx'), 'utf8');
const tree = ts.createSourceFile('CamerasManage.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const helper = tree.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === 'testCameraStream');
assert.ok(helper, 'The connection-test helper must exist');
const javascript = ts.transpileModule(helper.getText(tree), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;

async function runCase(response, polls, verify) {
  let now = 0;
  let reads = 0;
  const api = {
    post: async () => ({ data: response }),
    get: async () => ({ data: polls[Math.min(reads++, polls.length - 1)] }),
  };
  const delay = (callback) => { now += 2000; callback(); };
  const create = new Function('api', 'setTimeout', 'Date', `${javascript}; return testCameraStream;`);
  const testStream = create(api, delay, { now: () => now });
  const result = await testStream({ ip: '192.168.1.102', port: 554, rtsp_path: '/Streaming/Channels/201' });
  verify(result, reads);
}

(async () => {
  const queued = { success: false, queued: true, job_id: 'job', lan_unreachable: true };
  await runCase(queued, [
    { status: 'pending' },
    { status: 'done', success: true, rtsp_path: '/Streaming/Channels/201', thumbnail_base64: 'jpeg' },
  ], (result, reads) => {
    assert.deepEqual(result, { success: true, thumbnail_base64: 'jpeg' });
    assert.equal(reads, 2);
  });
  await runCase(queued, [{ status: 'done', success: false, error: 'Digest SHA-256 unsupported' }], (result) => {
    assert.equal(result.success, false);
    assert.equal(result.error, 'Digest SHA-256 unsupported');
  });
  await runCase(queued, [{ status: 'done', success: true, rtsp_path: '/Streaming/Channels/101', thumbnail_base64: 'jpeg' }], (result) => {
    assert.equal(result.success, false, 'A different NVR channel must not validate this camera');
  });
  await runCase(queued, [{ status: 'done', success: true, rtsp_path: '/Streaming/Channels/201' }], (result) => {
    assert.equal(result.success, false, 'LAN video confirmation requires an actual preview');
  });
  await runCase(queued, [{ status: 'expired' }], (result) => {
    assert.equal(result.success, false);
    assert.match(result.error, /expired/);
  });
  await runCase(queued, [{ status: 'pending' }], (result) => {
    assert.equal(result.success, false);
    assert.match(result.error, /95 seconds/);
  });
  await runCase({ success: true, thumbnail_base64: 'public-jpeg' }, [], (result, reads) => {
    assert.equal(result.success, true);
    assert.equal(reads, 0);
  });
  console.log('7 camera connection UI-helper checks passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
