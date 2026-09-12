'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createClient, validateConfig } = require('../client.js');
// No test may accidentally fall back to a real transport.
globalThis.fetch = () => { throw new Error('NETWORK_FORBIDDEN'); };
const userId = '11111111-1111-4111-8111-111111111111';
const taskId = '22222222-2222-4222-8222-222222222222';
const storeId = '33333333-3333-4333-8333-333333333333';
const jwt = role => ['eyJhbGciOiJIUzI1NiJ9', Buffer.from(JSON.stringify({ role })).toString('base64url'), 'fake-signature'].join('.');
const config = { mode: 'live', liveEnabled: true, supabaseUrl: 'https://supabase.invalid', publicKey: 'sb_publishable_fake_only' };
const response = (data, status = 200) => ({ status, ok: status >= 200 && status < 300, async json() { return data; } });
const memory = () => { const data = new Map(); return { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, v), removeItem: k => data.delete(k) }; };
const input = () => ({ task_id: taskId, store_id: storeId, self_asin: 'B012345678', product_stage: 'stable', input_file_path: 'private-inputs/object.xlsx', input_file_hash: 'a'.repeat(64) });
function setup(queue = [], extra = {}) {
  const calls = [];
  const storage = extra.storage || memory();
  const client = createClient({ config, storage, now: () => 100000,
    fetch: async (url, options) => {
      calls.push({ url, ...options });
      assert.ok(url.startsWith('https://supabase.invalid/'));
      assert.ok(queue.length, `Unexpected fake fetch: ${url}`);
      const item = queue.shift();
      if (item instanceof Error) throw item;
      return typeof item === 'function' ? item() : item;
    }, ...extra });
  return { client, calls, storage };
}
const loginResponses = () => [response({ access_token: jwt('authenticated'), expires_at: 200, user: { id: userId } }), response({ id: userId })];
const signIn = client => client.auth.signIn('user@example.invalid', 'fake-password');
const gatewayConfig = { ...config, gatewayUrl: config.supabaseUrl + '/functions/v1/kwcc-gateway' };
const uploadRun = '44444444-4444-4444-8444-444444444444';
const uploadInput = () => ({ ...input(), run_id: uploadRun, file: new File(['keyword,clicks\nexample,1'], 'report.csv', { type: 'text/csv' }) });
const registered = () => response({ task_id: taskId, run_id: uploadRun, status: 'pending' });

test('gateway config pins the same project endpoint and rejects mismatched anon project', () => {
  assert.equal(validateConfig(gatewayConfig).gateway, gatewayConfig.gatewayUrl);
  for (const gatewayUrl of ['https://other.invalid/functions/v1/kwcc-gateway', config.supabaseUrl + '/functions/v1/other', gatewayConfig.gatewayUrl + '?key=unexpected', gatewayConfig.gatewayUrl + '/'])
    assert.throws(() => validateConfig({ ...config, gatewayUrl }));
  const key = ['eyJhbGciOiJIUzI1NiJ9', Buffer.from(JSON.stringify({ role: 'anon', ref: 'other' })).toString('base64url'), 'unsigned'].join('.');
  assert.throws(() => validateConfig({ ...config, supabaseUrl: 'https://example.supabase.co', publicKey: key }));
});

test('upload hashes actual file bytes, posts a private object then registers task/run through the gateway', async () => {
  const { client, calls } = setup([...loginResponses(), response({ Key: 'stored' }), registered()], { config: gatewayConfig, crypto: require('node:crypto').webcrypto });
  await signIn(client);
  const result = await client.tasks.create(uploadInput());
  assert.equal(result.run_id, uploadRun);
  assert.equal(calls[0].url, gatewayConfig.gatewayUrl + '/auth/v1/token?grant_type=password');
  assert.equal(calls[2].url, gatewayConfig.gatewayUrl + `/storage/v1/object/inputs/${storeId}/${userId}/${taskId}/input.csv`);
  assert.equal(calls[2].headers['Accept-Profile'], undefined);
  assert.equal(calls[2].headers['Content-Type'], 'text/csv');
  assert.ok(calls[2].body instanceof ArrayBuffer);
  const body = JSON.parse(calls[3].body);
  assert.equal(body.p_input_file_hash, require('node:crypto').createHash('sha256').update('keyword,clicks\nexample,1').digest('hex'));
  assert.equal(body.p_run_id, uploadRun);
  assert.equal(calls[3].url, gatewayConfig.gatewayUrl + '/rest/v1/rpc/kwcc_submit_task_with_business_inputs');
  assert.deepEqual(body.p_business_inputs, { primary_core_keyword: null, competitor_asins: [],
    core_keywords: [], competitor_selection_version: null, product_facts_version: null,
    feature_review_version: null, checklist_version: null, confirmation_version: null });
  assert.ok(calls.every(c => c.credentials === 'omit' && c.redirect === 'error'));
});

test('uncertain task registration retry preserves task/run and does not re-upload or overwrite the private input', async () => {
  const { client, calls } = setup([...loginResponses(), response({}), new Error('timeout'), registered()], { config: gatewayConfig, crypto: require('node:crypto').webcrypto });
  await signIn(client);
  await assert.rejects(client.tasks.create(uploadInput()), { code: 'NETWORK_ERROR' });
  await client.tasks.create(uploadInput());
  assert.equal(calls.filter(c => c.url.includes('/storage/')).length, 1);
  assert.equal(calls[3].body, calls[4].body);
  await assert.rejects(client.tasks.create({ ...uploadInput(), self_asin: 'B087654321' }), { code: 'TASK_CONFLICT' });
  assert.equal(calls.length, 5);
});

test('invalid or failed upload never registers a task', async () => {
  const { client, calls } = setup([...loginResponses(), response({}, 413)], { config: gatewayConfig, crypto: require('node:crypto').webcrypto });
  await signIn(client);
  for (const file of [new File([], 'empty.csv'), new File(['x'], 'payload.exe'), { name: 'big.csv', size: 10485761, arrayBuffer() {} }])
    await assert.rejects(client.tasks.create({ ...uploadInput(), file }), { code: 'INPUT_INVALID' });
  assert.equal(calls.length, 2);
  await assert.rejects(client.tasks.create(uploadInput()), { code: 'REQUEST_FAILED' });
  assert.equal(calls.length, 3);
  assert.ok(!calls.some(c => c.url.includes('kwcc_submit_task')));
});

test('logout while file hashing cancels upload before any storage request', async () => {
  let resolveHash;
  const { client, calls } = setup([...loginResponses(), response(null, 204)], { config: gatewayConfig, crypto: { subtle: { digest: () => new Promise(resolve => { resolveHash = resolve; }) } } });
  await signIn(client);
  const pending = client.tasks.create(uploadInput());
  await new Promise(resolve => setImmediate(resolve));
  await client.auth.signOut();
  resolveHash(new Uint8Array(32).buffer);
  await assert.rejects(pending, { code: 'SESSION_CHANGED' });
  assert.equal(calls.length, 3);
});

test('latest run selection and rerun use scoped task and new run ids', async () => {
  const { client, calls } = setup([...loginResponses(), response([{ task_id: taskId, run_id: uploadRun, status: 'completed' }]), response({ task_id: taskId, run_id: userId, status: 'pending' })], { config: gatewayConfig });
  await signIn(client);
  assert.equal((await client.tasks.latestRun(taskId)).run_id, uploadRun);
  await assert.rejects(client.tasks.rerun(taskId, uploadRun, uploadRun), { code: 'INPUT_INVALID' });
  await client.tasks.rerun(taskId, uploadRun, userId);
  assert.deepEqual(JSON.parse(calls[3].body), { p_task_id: taskId, p_previous_run_id: uploadRun, p_run_id: userId });
});

test('demo default uses no fetch and never persists a real task', async () => {
  const client = createClient({ storage: memory(), fetch: globalThis.fetch });
  assert.equal(client.mode, 'demo');
  assert.equal((await client.auth.signIn()).demo, true);
  assert.deepEqual(await client.tasks.create({ file: {} }), { demo: true, persisted: false });
  await client.auth.signOut();
  assert.equal(await client.auth.getUser(), null);
});
test('live requires both switches and valid public config; cannot silently fall back', () => {
  for (const bad of [{ ...config, liveEnabled: false }, { ...config, liveEnabled: 'true' }, { ...config, mode: 'typo' },
    { ...config, supabaseUrl: 'http://supabase.invalid' }, { ...config, supabaseUrl: 'https://supabase.invalid/rest/v1' },
    { ...config, supabaseUrl: 'https://user:pass@supabase.invalid' }, { ...config, supabaseUrl: 'https://supabase.invalid/?x=1' },
    { ...config, supabaseUrl: 'https://supabase.invalid/#fragment' }, { ...config, publicKey: '' }])
    assert.throws(() => createClient({ config: bad }));
  assert.equal(validateConfig({ ...config, publicKey: jwt('anon') }).mode, 'live');
});
test('service keys, service JWTs and arbitrary user JWTs cannot be public keys', () => {
  for (const publicKey of ['sb_secret_fake', 'service_role', jwt('service_role'), jwt('authenticated'), 'arbitrary', 'sb_publishable_fake\r\nx:1'])
    assert.throws(() => validateConfig({ ...config, publicKey }));
});
test('demo marker does not satisfy live authentication; no transport is called', async () => {
  const storage = memory(); storage.setItem('kwcc_demo_session', '1');
  const { client, calls } = setup([], { storage });
  assert.equal(await client.auth.getUser(), null);
  await assert.rejects(client.tasks.list(), { code: 'AUTH_REQUIRED' });
  assert.equal(calls.length, 0);
});
test('missing transport fails closed', async () => {
  const client = createClient({ config });
  await assert.rejects(signIn(client), { code: 'TRANSPORT_MISSING' });
  assert.equal(client.auth.state, 'signed_out');
});
test('login validates user through Auth; session restoration revalidates', async () => {
  const storage = memory();
  const { client, calls } = setup(loginResponses(), { storage });
  assert.deepEqual(await signIn(client), { id: userId });
  assert.equal(calls[0].url, 'https://supabase.invalid/auth/v1/token?grant_type=password');
  assert.equal(calls[0].headers['Accept-Profile'], undefined);
  assert.equal(calls[1].headers.Authorization, `Bearer ${jwt('authenticated')}`);
  assert.equal(calls[1].credentials, 'omit'); assert.equal(calls[1].redirect, 'error');
  assert.ok(!storage.getItem('kwcc_live_session').includes('fake-password'));
  const restored = setup([response({ id: userId })], { storage });
  assert.deepEqual(await restored.client.auth.getUser(), { id: userId });
  assert.equal(restored.calls.length, 1);
});
test('bad credentials, malformed responses, user mismatch and network failure stay signed out', async () => {
  for (const queue of [[response({}, 400)], [response({}, 403)], [new Error('transport detail must not leak')],
    [response(null)], [response({ access_token: jwt('service_role'), expires_at: 200, user: { id: userId } })],
    [loginResponses()[0], response({ id: storeId })], [response({ access_token: jwt('authenticated'), user: { id: userId } })]]) {
    const { client, storage } = setup(queue);
    await assert.rejects(signIn(client));
    assert.notEqual(client.auth.state, 'authenticated');
    assert.equal(storage.getItem('kwcc_live_session'), null);
    await assert.rejects(client.tasks.list(), { code: 'AUTH_REQUIRED' });
  }
});
test('expired stored session is cleared without a request', async () => {
  const storage = memory();
  storage.setItem('kwcc_live_session', JSON.stringify({ access_token: 'fake', expires_at: 99, user: { id: userId } }));
  const { client, calls } = setup([], { storage });
  await assert.rejects(client.auth.getUser(), { code: 'SESSION_EXPIRED' });
  assert.equal(client.auth.state, 'expired'); assert.equal(calls.length, 0);
  assert.equal(storage.getItem('kwcc_live_session'), null);
});
test('in-memory expiry prevents another REST request', async () => {
  let clock = 100000;
  const { client, calls } = setup(loginResponses(), { now: () => clock });
  await signIn(client); clock = 200000;
  await assert.rejects(client.tasks.list(), { code: 'SESSION_EXPIRED' });
  assert.equal(calls.length, 2);
});
test('401 and 403 clear live session, propagate distinct state, never show success', async () => {
  for (const status of [401, 403]) {
    const { client, storage } = setup([...loginResponses(), response({}, status)]);
    await signIn(client);
    await assert.rejects(client.tasks.create(input()), { status });
    assert.equal(client.auth.state, status === 403 ? 'forbidden' : 'expired');
    assert.equal(storage.getItem('kwcc_live_session'), null);
    await assert.rejects(client.tasks.list(), { code: 'AUTH_REQUIRED' });
  }
});
test('REST lists and task create use explicit public profiles and authenticated ownership', async () => {
  const { client, calls } = setup([...loginResponses(), response([]), response([]), response([{ task_id: taskId, status: 'pending' }])]);
  await signIn(client); await client.tasks.list(); await client.strategies.list();
  assert.equal((await client.tasks.create({ ...input(), created_by: 'forged', status: 'completed' })).task_id, taskId);
  for (const call of calls.slice(2)) {
    assert.equal(call.headers['Accept-Profile'], 'public'); assert.equal(call.headers['Content-Profile'], 'public');
    assert.equal(call.headers.Authorization, `Bearer ${jwt('authenticated')}`);
  }
  const created = JSON.parse(calls[4].body);
  assert.equal(created.created_by, userId); assert.equal(created.status, 'pending');
  assert.equal(created.current_stage, 'ingestion'); assert.equal(calls[4].headers.Prefer, 'return=representation');
});
test('strategy writes and selected files fail closed without REST requests', async () => {
  const { client, calls } = setup(loginResponses()); await signIn(client);
  assert.equal(client.strategies.canWrite, false);
  await assert.rejects(client.strategies.save({}), { code: 'STRATEGY_WRITE_DISABLED' });
  await assert.rejects(client.tasks.create({ ...input(), file: { name: 'file.xlsx' } }), { code: 'UPLOAD_UNAVAILABLE' });
  for (const input_file_path of ['C:\\fakepath\\file.xlsx', '/tmp/file.xlsx', '../file.xlsx', 'x/../file.xlsx', 'https://private.invalid/file', 'x//file'])
    await assert.rejects(client.tasks.create({ ...input(), input_file_path }), { code: 'INPUT_INVALID' });
  assert.equal(calls.length, 2);
});
test('task and strategy response shape errors never count as success', async () => {
  const { client } = setup([...loginResponses(), response(null), response({}), response([]), response([{ task_id: storeId, status: 'pending' }])]);
  await signIn(client);
  await assert.rejects(client.tasks.list(), { code: 'RESPONSE_INVALID' });
  await assert.rejects(client.strategies.list(), { code: 'RESPONSE_INVALID' });
  await assert.rejects(client.tasks.create(input()), { code: 'RESPONSE_INVALID' });
  await assert.rejects(client.tasks.create(input()), { code: 'RESPONSE_INVALID' });
});
test('logout clears local state even if remote logout fails', async () => {
  const { client, storage, calls } = setup([...loginResponses(), new Error('offline')]); await signIn(client);
  await assert.rejects(client.auth.signOut(), { code: 'NETWORK_ERROR' });
  assert.equal(storage.getItem('kwcc_live_session'), null); assert.equal(client.auth.state, 'signed_out');
  await assert.rejects(client.tasks.list(), { code: 'AUTH_REQUIRED' });
  assert.equal(calls[2].url, 'https://supabase.invalid/auth/v1/logout');
});
test('logout during login prevents delayed response from restoring authentication', async () => {
  let release;
  const { client } = setup([() => new Promise(resolve => { release = resolve; }), response({ id: userId })]);
  const pending = signIn(client);
  await client.auth.signOut();
  release(loginResponses()[0]);
  await assert.rejects(pending, { code: 'SESSION_CHANGED' });
  assert.equal(client.auth.state, 'signed_out');
});
test('late private response cannot repopulate data after logout', async () => {
  let release;
  const { client } = setup([...loginResponses(), () => new Promise(resolve => { release = resolve; }), response(null, 204)]);
  await signIn(client); const pending = client.tasks.list(); await client.auth.signOut();
  release(response([{ task_id: taskId }]));
  await assert.rejects(pending, { code: 'SESSION_CHANGED' });
});
test('injected clients are supported but demo client cannot authenticate live', () => {
  const authClient = { mode: 'live' }, taskClient = { mode: 'live' }, strategyClient = { mode: 'live' };
  const client = createClient({ config, authClient, taskClient, strategyClient });
  assert.equal(client.auth, authClient); assert.equal(client.tasks, taskClient); assert.equal(client.strategies, strategyClient);
  assert.throws(() => createClient({ config, authClient: { mode: 'demo' } }), { code: 'MODE_MISMATCH' });
});
test('all pages wire config then client then app, production config remains empty demo', () => {
  const root = path.join(__dirname, '..');
  for (const page of ['index', 'login', 'workspace', 'tasks', 'strategy', 'report']) {
    const html = fs.readFileSync(path.join(root, `${page}.html`), 'utf8');
    const scripts = [...html.matchAll(/<script src="([^"]+)"/g)].map(match => match[1]);
    assert.deepEqual(scripts.slice(0, 3), ['public-config.js', 'client.js', 'app.js']);
  }
  const sandbox = {}; vm.runInNewContext(fs.readFileSync(path.join(root, 'public-config.js'), 'utf8'), sandbox);
  assert.equal(sandbox.KWCC_PUBLIC_CONFIG.mode, 'demo'); assert.equal(sandbox.KWCC_PUBLIC_CONFIG.liveEnabled, false);
  assert.equal(sandbox.KWCC_PUBLIC_CONFIG.supabaseUrl, ''); assert.equal(sandbox.KWCC_PUBLIC_CONFIG.publicKey, '');
});
test('task and strategy scripts await auth and do not fetch demo artifacts when live or blocked', async () => {
  for (const name of ['tasks', 'strategy']) for (const ready of [false, true]) {
    const element = () => ({ children: [], textContent: '', value: '', dataset: {},
      addEventListener() {}, setAttribute() {}, querySelectorAll() { return []; },
      replaceChildren() { this.children = []; }, append(item) { this.children.push(item); } });
    const nodes = new Map();
    const context = { fetch: globalThis.fetch, URL,
      document: { currentScript: {src: 'https://demo.invalid/report.js'}, querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, element()); return nodes.get(selector); }, createElement: element },
      KWCC: { ready: Promise.resolve(ready), mode: 'live', tasks: { list: async () => [] }, strategies: { list: async () => [], permissions: async () => [] }, showError: error => { throw error; } } };
    await vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', `${name}.js`), 'utf8'), context);
    if (context.KWCCStrategyReady) await context.KWCCStrategyReady;
    if (!ready) assert.equal(nodes.size, 0);
  }
});

const runId = '44444444-4444-4444-8444-444444444444';
const reportPath = `${taskId}/${runId}/report-${'a'.repeat(48)}.json`;
const reportContent = () => ({ schema_version: 'report-0.2', rows: [{ keyword: 'private keyword', spend: null, ui_color: 'cyan', action_group: 'hold_steady' }], currency_code: 'USD' });
const reportRun = () => ({ task_id: taskId, run_id: runId, status: 'completed', report_path: reportPath });
const reportResponses = () => [response([{ task_id: taskId }]), response([reportRun()]), response(reportContent())];

test('private reports authorize task, then exact run, then exact bound object using the same ordinary token', async () => {
  const { client, calls } = setup([...loginResponses(), ...reportResponses()]);
  await signIn(client);
  const result = await client.reports.read(taskId.toUpperCase(), runId.toUpperCase());
  assert.deepEqual(result, { task_id: taskId, run_id: runId, report_path: reportPath, content: reportContent() });
  assert.match(calls[2].url, new RegExp(`/rest/v1/tasks\\?task_id=eq.${taskId}&select=task_id&limit=2$`));
  assert.match(calls[3].url, new RegExp(`/rest/v1/task_runs\\?task_id=eq.${taskId}&run_id=eq.${runId}&`));
  assert.equal(calls[4].url, `https://supabase.invalid/storage/v1/object/authenticated/reports/${reportPath}`);
  for (const call of calls.slice(2)) {
    assert.equal(call.headers.Authorization, `Bearer ${jwt('authenticated')}`);
    assert.equal(call.headers.apikey, config.publicKey);
    assert.equal(call.credentials, 'omit'); assert.equal(call.redirect, 'error'); assert.equal(call.cache, 'no-store');
    assert.equal(call.method, 'GET');
  }
  assert.equal(calls[2].headers['Accept-Profile'], 'public');
  assert.equal(calls[3].headers['Accept-Profile'], 'public');
  assert.equal(calls[4].headers['Accept-Profile'], undefined);
});

test('private reports require session and strict UUIDs before any lookup', async () => {
  const { client, calls } = setup(loginResponses());
  await assert.rejects(client.reports.read(taskId, runId), { code: 'AUTH_REQUIRED' });
  await signIn(client);
  for (const bad of [null, '', '../run', 'https://private.invalid', `${taskId}\n`, `${taskId}&select=*`, [], {}]) {
    await assert.rejects(client.reports.read(bad, runId), { code: 'INPUT_INVALID' });
    await assert.rejects(client.reports.read(taskId, bad), { code: 'INPUT_INVALID' });
  }
  assert.equal(calls.length, 2);
});

test('empty, duplicated, malformed or cross-task/run authorization never reaches Storage', async () => {
  for (const tasks of [[], null, {}, [{ task_id: storeId }], [{ task_id: taskId }, { task_id: taskId }]]) {
    const { client, calls } = setup([...loginResponses(), response(tasks)]);
    await signIn(client);
    await assert.rejects(client.reports.read(taskId, runId), { code: 'REPORT_UNAVAILABLE' });
    assert.equal(calls.length, 3);
  }
  for (const runs of [[], {}, null, [reportRun(), reportRun()], [{ ...reportRun(), task_id: storeId }], [{ ...reportRun(), run_id: storeId }]]) {
    const { client, calls } = setup([...loginResponses(), reportResponses()[0], response(runs)]);
    await signIn(client);
    await assert.rejects(client.reports.read(taskId, runId), { code: 'REPORT_UNAVAILABLE' });
    assert.equal(calls.length, 4);
  }
});

test('reports reject URLs, encodings, traversal, siblings and all non-48hex object names', async () => {
  for (const report_path of [
    `https://supabase.invalid/storage/v1/object/authenticated/reports/${reportPath}`, `//evil.invalid/${reportPath}`,
    `/reports/${reportPath}`, reportPath.replace(runId, storeId), reportPath.replace(taskId, storeId),
    `${taskId}/${runId}/../${runId}/report-${'a'.repeat(48)}.json`, reportPath.replace('/report-', '/%72eport-'),
    reportPath.replaceAll('/', '\\'), `${reportPath}?download=1`, `${reportPath}#fragment`, `${reportPath}\n`,
    `${taskId}/${runId}/master-table.json`, `${taskId}/${runId}/report-${'a'.repeat(47)}.json`,
    `${taskId}/${runId}/report-${'a'.repeat(49)}.json`, reportPath.replace('report-a', 'report-g'), '', {},
  ]) {
    const { client, calls } = setup([...loginResponses(), reportResponses()[0], response([{ ...reportRun(), report_path }])]);
    await signIn(client);
    await assert.rejects(client.reports.read(taskId, runId), { code: 'REPORT_PATH_INVALID' });
    assert.equal(calls.length, 4);
  }
});

test('unfinished or unbound runs and all unbound modules explicitly remain not generated', async () => {
  for (const patch of [{ status: 'pending' }, { status: 'processing' }, { status: 'failed' }, { report_path: null }]) {
    const { client, calls } = setup([...loginResponses(), reportResponses()[0], response([{ ...reportRun(), ...patch }])]);
    await signIn(client);
    await assert.rejects(client.reports.read(taskId, runId), { code: 'REPORT_NOT_GENERATED' });
    assert.equal(calls.length, 4);
  }
  const { client, calls } = setup([...loginResponses(), ...Array.from({ length: 5 }, reportResponses).flat()]);
  await assert.rejects(client.reports.readModule(taskId, runId, 'rank-benchmark.json'), { code: 'AUTH_REQUIRED' });
  await signIn(client);
  for (const name of ['rank-benchmark.json', 'negative-keywords.json', 'competitors.json', 'listing-diagnostics.json', 'optimization-plan.json'])
    await assert.rejects(client.reports.readModule(taskId, runId, name), { code: 'REPORT_NOT_GENERATED' });
  await assert.rejects(client.reports.readModule(taskId, runId, '../report.json'), { code: 'INPUT_INVALID' });
  assert.equal(calls.length, 17);
  assert.ok(calls.filter(call => call.url.includes('/storage/')).every(call => call.url.endsWith(reportPath)));
});

test('bundled modules use only the authorized master object and preserve missing module semantics', async () => {
  const modules = {
    'rank-benchmark.json': { rows: [{ keyword: 'bundle rank', my_organic_rank: null }] },
    'negative-keywords.json': { exact_negative: [], phrase_negative: [], cautious: [] },
    'optimization-plan.json': { actions: [] },
    'competitors.json': { competitors: [] },
    'listing-diagnostics.json': { diagnostics: [] },
  };
  for (const name of Object.keys(modules)) {
    const content = { ...reportContent(), task_id: taskId, run_id: runId, modules };
    const { client, calls } = setup([...loginResponses(), ...reportResponses().slice(0, 2), response(content)]);
    await signIn(client);
    assert.deepEqual(await client.reports.readModule(taskId, runId, name), modules[name]);
    assert.equal(calls.length, 5);
    assert.equal(calls[4].url, `https://supabase.invalid/storage/v1/object/authenticated/reports/${reportPath}`);
    assert.ok(calls.every(call => !call.url.includes(name)));
  }
  for (const modules of [{}, { 'rank-benchmark.json': null }, null]) {
    const { client, calls } = setup([...loginResponses(), ...reportResponses().slice(0, 2), response({ ...reportContent(), modules })]);
    await signIn(client);
    await assert.rejects(client.reports.readModule(taskId, runId, 'rank-benchmark.json'), { code: 'REPORT_NOT_GENERATED' });
    assert.equal(calls.length, 5);
  }
});

test('bundled modules reject malformed entries, URL references and cross-run identities', async () => {
  for (const modules of [[], 'https://evil.invalid', { 'rank-benchmark.json': [] },
    { 'rank-benchmark.json': `https://supabase.invalid/${reportPath}` },
    { 'rank-benchmark.json': { run_id: storeId, rows: [] } }, { 'rank-benchmark.json': { task_id: storeId, rows: [] } }]) {
    const { client, calls } = setup([...loginResponses(), ...reportResponses().slice(0, 2), response({ ...reportContent(), modules })]);
    await signIn(client);
    await assert.rejects(client.reports.readModule(taskId, runId, 'rank-benchmark.json'), { code: 'RESPONSE_INVALID' });
    assert.equal(calls.length, 5);
  }
});

test('invalid object schema/rows and conflicting embedded identities reject the artifact', async () => {
  for (const content of [null, [], {}, { ...reportContent(), schema_version: 'module02-0.1' },
    { ...reportContent(), rows: [null] }, { ...reportContent(), rows: [[]] },
    { ...reportContent(), task_id: storeId }, { ...reportContent(), run_id: storeId }]) {
    const { client } = setup([...loginResponses(), ...reportResponses().slice(0, 2), response(content)]);
    await signIn(client);
    await assert.rejects(client.reports.read(taskId, runId), { code: 'RESPONSE_INVALID' });
  }
});

test('401/403 at every report stage clears authentication and never falls back to demo', async () => {
  for (const status of [401, 403]) for (const stage of [0, 1, 2]) {
    const { client, calls, storage } = setup([...loginResponses(), ...reportResponses().slice(0, stage), response({}, status)]);
    await signIn(client);
    await assert.rejects(client.reports.read(taskId, runId), { status });
    assert.equal(client.auth.state, status === 403 ? 'forbidden' : 'expired');
    assert.equal(storage.getItem('kwcc_live_session'), null);
    assert.equal(calls.length, 3 + stage);
  }
});

test('logout, expiry and new login at every report stage discard late data and stop the chain', async () => {
  for (const change of ['logout', 'expire', 'login']) for (const stage of [0, 1, 2]) {
    let release, started;
    const waiting = new Promise(resolve => { started = resolve; });
    let clock = 100000;
    const queue = [...loginResponses(), ...reportResponses().slice(0, stage), () => new Promise(resolve => { release = resolve; started(); })];
    if (change === 'logout') queue.push(response(null, 204));
    if (change === 'login') queue.push(...loginResponses());
    const { client, calls } = setup(queue, { now: () => clock });
    await signIn(client);
    const pending = client.reports.read(taskId, runId);
    await waiting;
    if (change === 'logout') await client.auth.signOut();
    if (change === 'login') await signIn(client);
    if (change === 'expire') clock = 200000;
    release(reportResponses()[stage]);
    await assert.rejects(pending, { code: change === 'expire' ? 'SESSION_EXPIRED' : 'SESSION_CHANGED' });
    assert.equal(calls.length, 3 + stage + (change === 'login' ? 2 : change === 'logout' ? 1 : 0));
    if (change === 'login') assert.equal(client.auth.state, 'authenticated');
  }
});

function reportPage(client, { ready = true, search = `?task=${taskId}&run=${runId}&url=https://evil.invalid` } = {}) {
  const nodes = new Map();
  const element = tag => ({ tag, children: [], textContent: '', disabled: false, events: {},
    append(...items) { this.children.push(...items); }, appendChild(item) { this.children.push(item); },
    replaceChildren(...items) { this.children = items; }, setAttribute() {},
    addEventListener(name, fn) { this.events[name] = fn; }, classList: { toggle() {} },
  });
  const context = {
    URL, fetch: globalThis.fetch, location: { href: `https://demo.invalid/report/index.html${search}` },
    document: { currentScript: { src: 'https://demo.invalid/report.js' }, createElement: element,
      querySelector(key) { if (!nodes.has(key)) nodes.set(key, element(key)); return nodes.get(key); },
      querySelectorAll() { return []; } },
    KWCC: { ...client, ready: Promise.resolve(ready) },
  };
  const done = vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../report.js'), 'utf8'), context);
  return { done, nodes };
}

test('master page awaits auth and renders only the private client result; logout clears export/data', async () => {
  const { client, calls } = setup([...loginResponses(), ...reportResponses(), response(null, 204)]);
  const denied = reportPage(client, { ready: false });
  await denied.done; assert.equal(denied.nodes.size, 0); assert.equal(calls.length, 0);
  await signIn(client);
  const page = reportPage(client); await page.done;
  assert.equal(calls.length, 5);
  assert.equal(page.nodes.get('#report-schema-version').textContent, 'report-0.2');
  assert.equal(page.nodes.get('#report-rows').children[0].children[0].children[0].textContent, 'private keyword');
  assert.equal(page.nodes.get('#report-rows').children[0].children[2].children[0].className, 'conclusion cyan');
  assert.equal(page.nodes.get('#export-report').disabled, false);
  await client.auth.signOut();
  assert.equal(page.nodes.get('#export-report').disabled, true);
  assert.equal(page.nodes.get('#keyword-count').textContent, '报告加载失败');
  assert.doesNotMatch(JSON.stringify(page.nodes.get('#report-rows')), /private keyword/);
  page.nodes.get('#export-report').events.click();
});

test('master page rejects missing selectors and private storage errors without loading demo', async () => {
  for (const missing of [true, false]) {
    const queue = [...loginResponses()];
    if (!missing) queue.push(...reportResponses().slice(0, 2), response({}, 404));
    const { client, calls } = setup(queue); await signIn(client);
    const page = reportPage(client, missing ? { search: `?task=${taskId}` } : {}); await page.done;
    assert.equal(page.nodes.get('#export-report').disabled, true);
    assert.equal(page.nodes.get('#keyword-count').textContent, '报告加载失败');
    assert.equal(calls.length, missing ? 2 : 5);
    if (missing) assert.match(page.nodes.get('#report-rows').children[0].children[0].textContent, /task 与 run UUID/);
  }
});

test('master page expiry before export clears private report even without timer notification', async () => {
  let clock = 100000;
  const { client } = setup([...loginResponses(), ...reportResponses()], { now: () => clock });
  await signIn(client);
  const page = reportPage(client); await page.done;
  assert.equal(page.nodes.get('#export-report').disabled, false);
  clock = 200000;
  page.nodes.get('#export-report').events.click();
  assert.equal(page.nodes.get('#export-report').disabled, true);
  assert.doesNotMatch(JSON.stringify(page.nodes.get('#report-rows')), /private keyword/);
});

function appFixture(client, { login = false, clientError = false } = {}) {
  const elements = new Map();
  const element = () => ({ hidden: false, disabled: false, textContent: '', value: '', children: [], dataset: {},
    events: {}, classList: { contains: () => !login, add() {}, remove() {}, toggle() {} },
    setAttribute() {}, append(item) { this.children.push(item); }, prepend(item) { this.children.unshift(item); },
    querySelector(selector) { return elements.get(selector) || null; },
    addEventListener(name, handler) { this.events[name] = handler; } });
  const body = element();
  elements.set('main', element());
  if (login) {
    elements.set('#login-form', element());
    elements.set('[type="submit"]', element());
    elements.set('[name="password"]', element());
  }
  let subscriber;
  client.auth.subscribe = fn => { subscriber = fn; };
  const location = { href: '', reloads: 0, replace(url) { this.href = url; }, reload() { this.reloads++; } };
  const windowEvents = {};
  const timers = new Set();
  const sandbox = {
    KWCC_PUBLIC_CONFIG: config, KWCCClient: { createClient: () => { if (clientError) throw new Error('bad config'); return client; } },
    sessionStorage: memory(), localStorage: memory(), fetch: globalThis.fetch,
    FormData: class { get(key) { return key === 'password' ? 'fake-password' : 'user@example.invalid'; } },
    setInterval: () => { timers.add(1); return 1; }, clearInterval: id => timers.delete(id), setTimeout() {},
    window: { location, addEventListener(name, handler) { windowEvents[name] = handler; } },
    document: { body, createElement: element, querySelector: selector => elements.get(selector) || null,
      querySelectorAll: selector => selector.startsWith('main,') ? [elements.get('main')] : [], addEventListener() {} },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8'), sandbox);
  return { sandbox, elements, body, location, timers, windowEvents, emit: state => subscriber(state) };
}

for (const scenario of ['signed_out', 'changed_user', 'expired']) {
  test(`bfcache ${scenario} locks old DOM and reloads a fresh session before showing data`, async () => {
    let clock = 100000;
    const storage = memory();
    const session = { access_token: jwt('authenticated'), expires_at: 200, user: { id: userId } };
    storage.setItem('kwcc_live_session', JSON.stringify(session));
    const old = setup([response({ id: userId })], { storage, now: () => clock });
    const fixture = appFixture(old.client);
    await fixture.sandbox.KWCC.ready;
    assert.equal(fixture.elements.get('main').hidden, false);
    fixture.windowEvents.pageshow({ persisted: false });
    assert.equal(fixture.location.reloads, 0);
    fixture.windowEvents.pagehide({ persisted: true });
    assert.equal(fixture.elements.get('main').hidden, true);
    assert.equal(fixture.timers.size, 0);
    if (scenario === 'signed_out') storage.removeItem('kwcc_live_session');
    if (scenario === 'changed_user') storage.setItem('kwcc_live_session', JSON.stringify({ ...session, user: { id: storeId } }));
    if (scenario === 'expired') clock = 201000;
    fixture.windowEvents.pageshow({ persisted: true });
    assert.equal(fixture.elements.get('main').hidden, true);
    assert.equal(fixture.location.reloads, 1);
    assert.equal(old.calls.length, 1, 'cached client must not issue a revalidation with its old token');
    const fresh = setup(scenario === 'changed_user' ? [response({ id: storeId })] : [], { storage, now: () => clock });
    const loaded = appFixture(fresh.client);
    assert.equal(await loaded.sandbox.KWCC.ready, scenario === 'changed_user');
    assert.equal(loaded.elements.get('main').hidden, scenario !== 'changed_user');
    if (scenario === 'changed_user') assert.equal((await fresh.client.auth.checkSession()).user.id, storeId);
  });
}

test('late initial Auth response cannot uncover a suspended page', async () => {
  let resolve;
  const fixture = appFixture({ mode: 'live', auth: { getUser: () => new Promise(done => { resolve = done; }) } });
  fixture.windowEvents.pagehide({ persisted: true });
  resolve({ id: userId });
  assert.equal(await fixture.sandbox.KWCC.ready, false);
  assert.equal(fixture.elements.get('main').hidden, true);
});
test('UI hides protected content on 403/expiry and rejects demo identity in live', async () => {
  const client = { mode: 'live', auth: { getUser: async () => ({ id: userId }) } };
  const fixture = appFixture(client);
  assert.equal(await fixture.sandbox.KWCC.ready, true);
  assert.equal(fixture.elements.get('main').hidden, false);
  fixture.emit('forbidden');
  assert.equal(fixture.elements.get('main').hidden, true);
  assert.match(fixture.body.children[0].textContent, /403/);
  assert.equal(fixture.body.children[0].children[0].href, 'login.html');
  const demo = appFixture({ mode: 'live', auth: { getUser: async () => ({ demo: true }) } });
  assert.equal(await demo.sandbox.KWCC.ready, false);
  assert.equal(demo.location.href, 'login.html');
  const expired = appFixture({ mode: 'live', auth: { getUser: async () => { throw new Error('expired'); } } });
  assert.equal(await expired.sandbox.KWCC.ready, false);
  assert.equal(expired.elements.get('main').hidden, true);
});
test('UI login failure clears password and never navigates; success navigates only after Auth', async () => {
  for (const success of [false, true]) {
    const client = { mode: 'live', auth: { signIn: async () => { if (!success) throw new Error('bad credentials'); return { id: userId }; } } };
    const fixture = appFixture(client, { login: true });
    await fixture.sandbox.KWCC.ready;
    fixture.elements.get('[name="password"]').value = 'fake-password';
    await fixture.elements.get('#login-form').events.submit({ preventDefault() {} });
    assert.equal(fixture.elements.get('[name="password"]').value, '');
    assert.equal(fixture.elements.get('[type="submit"]').disabled, false);
    assert.equal(fixture.location.href, success ? 'workspace.html' : '');
  }
});
test('invalid config blocks the UI instead of falling back to demo', async () => {
  const fixture = appFixture({ auth: {} }, { clientError: true });
  assert.equal(await fixture.sandbox.KWCC.ready, false);
  assert.equal(fixture.sandbox.KWCC.mode, 'blocked');
  assert.equal(fixture.elements.get('main').hidden, true);
});
