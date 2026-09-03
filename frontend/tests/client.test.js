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
test('page scripts await auth and do not fetch demo artifacts when live or blocked', async () => {
  for (const name of ['tasks', 'strategy', 'report']) for (const ready of [false, true]) {
    const element = () => ({ children: [], textContent: '', replaceChildren() { this.children = []; }, append(item) { this.children.push(item); } });
    const nodes = new Map();
    const context = { fetch: globalThis.fetch,
      document: { querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, element()); return nodes.get(selector); }, createElement: element },
      KWCC: { ready: Promise.resolve(ready), mode: 'live', tasks: { list: async () => [] }, strategies: { list: async () => [] }, showError: error => { throw error; } } };
    await vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', `${name}.js`), 'utf8'), context);
    if (!ready) assert.equal(nodes.size, 0);
    if (ready && name === 'report') assert.match(nodes.get('main').children[0].textContent, /私有报告读取尚未接入/);
  }
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
