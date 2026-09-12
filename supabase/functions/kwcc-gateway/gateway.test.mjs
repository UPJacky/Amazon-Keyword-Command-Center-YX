import test from 'node:test';
import assert from 'node:assert/strict';
import { createGateway } from './gateway.mjs';
import clientApi from '../../../frontend/client.js';

const project = 'exampleproject';
const origin = 'https://upjacky.github.io';
const base = `https://${project}.supabase.co/functions/v1/kwcc-gateway`;
const jwt = data => ['eyJhbGciOiJIUzI1NiJ9', Buffer.from(JSON.stringify(data)).toString('base64url'), 'unsigned_test_only'].join('.');
const key = jwt({ role: 'anon', ref: project });
const user = '11111111-1111-4111-8111-111111111111';
const token = jwt({ role: 'authenticated', sub: user, iss: `https://${project}.supabase.co/auth/v1` });
function setup(response = () => Response.json([{ task_id: user }])) {
  const calls = [];
  const handler = createGateway({ supabaseUrl: `https://${project}.supabase.co`, allowedOrigin: origin,
    fetchImpl: async (url, options) => { calls.push({ url, options }); return response(); } });
  return { calls, handler };
}
function request(path, options = {}) {
  return new Request(base + path, { ...options, headers: { Origin: origin, apikey: key,
    Authorization: `Bearer ${token}`, ...options.headers } });
}
function edgeRequest(path, options = {}) {
  return new Request(`https://${project}.supabase.co/kwcc-gateway${path}`, { ...options, headers: { Origin: origin, apikey: key,
    Authorization: `Bearer ${token}`, ...options.headers } });
}

test('exact Origin preflight succeeds with zero upstream calls; missing/null/lookalike origins fail', async () => {
  const { handler, calls } = setup();
  const response = await handler(request('/rest/v1/tasks?select=*', { method: 'OPTIONS', headers: {
    'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization, apikey, accept-profile',
  } }));
  assert.equal(response.status, 204);
  assert.equal(response.headers.get('access-control-allow-origin'), origin);
  assert.equal(response.headers.get('access-control-allow-credentials'), null);
  assert.equal(response.headers.get('vary'), 'Origin');
  for (const wrong of ['', 'null', origin + '.evil.test', origin + '/Amazon-Keyword-Command-Center-YX/']) {
    const denied = await handler(request('/rest/v1/tasks', { headers: { Origin: wrong } }));
    assert.equal(denied.status, 403);
    assert.equal(denied.headers.get('access-control-allow-origin'), null);
  }
  assert.equal(calls.length, 0);
});

test('preflight rejects unexpected headers and methods; actual routes remain allowlisted', async () => {
  const { handler, calls } = setup();
  for (const [path, method, headers] of [
    ['/rest/v1/tasks', 'DELETE', 'authorization'], ['/rest/v1/tasks', 'PATCH', 'apikey'],
    ['/rest/v1/tasks', 'GET', 'x-forwarded-host'], ['/rest/v1/tasks', '', 'authorization'],
  ]) assert.ok((await handler(request(path, { method: 'OPTIONS', headers: {
    'Access-Control-Request-Method': method, 'Access-Control-Request-Headers': headers,
  } }))).status >= 400);
  for (const path of ['/auth/v1/admin/users', '/rest/v1/rpc/has_store_access', '/storage/v1/object/public/reports/example.json']) {
    assert.equal((await handler(request(path, { method: 'OPTIONS', headers: {
      'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization',
    } }))).status, 204);
    assert.equal((await handler(request(path))).status, 404);
  }
  assert.equal(calls.length, 0);
});

test('bearer and public key forwarded without cookies; schema forced to public; response is not cacheable', async () => {
  const { handler, calls } = setup();
  const result = await handler(request('/rest/v1/tasks?select=*&order=created_at.desc', { headers: {
    Cookie: 'never=forward', 'Accept-Profile': 'private', 'X-Forwarded-Host': 'evil.test',
  } }));
  assert.equal(result.status, 200);
  assert.equal(result.headers.get('cache-control'), 'no-store');
  assert.equal(result.headers.get('access-control-allow-origin'), origin);
  assert.equal(calls[0].url, `https://${project}.supabase.co/rest/v1/tasks?select=*&order=created_at.desc`);
  assert.equal(calls[0].options.headers.get('Authorization'), `Bearer ${token}`);
  assert.equal(calls[0].options.headers.get('Accept-Profile'), 'public');
  assert.equal(calls[0].options.headers.get('Cookie'), null);
  assert.equal(calls[0].options.headers.get('X-Forwarded-Host'), null);
  assert.equal(calls[0].options.redirect, 'error');
  assert.equal(calls[0].options.credentials, 'omit');
});

test('anonymous, malformed, foreign-project and elevated tokens never reach upstream', async () => {
  const { handler, calls } = setup();
  for (const headers of [
    { Authorization: '' }, { Authorization: 'Bearer invalid' }, { Authorization: `Bearer ${key}` },
    { Authorization: `Bearer ${jwt({ role: 'service_role', ref: project })}` },
    { apikey: jwt({ role: 'service_role', ref: project }) }, { apikey: 'sb_secret_not_allowed' },
    { apikey: jwt({ role: 'anon', ref: 'other' }) },
    { Authorization: `Bearer ${jwt({ role: 'authenticated', iss: 'https://other.supabase.co/auth/v1' })}` },
  ]) assert.equal((await handler(request('/rest/v1/tasks', { headers }))).status, 401);
  assert.equal(calls.length, 0);
});

test('login forwards only password grant and public key; no privileged session or signup routes', async () => {
  const { handler, calls } = setup(() => Response.json({ access_token: 'response-test-only' }));
  const response = await handler(request('/auth/v1/token?grant_type=password', { method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: '' }, body: JSON.stringify({ email: 'user@example.test', password: 'fixture-only' }) }));
  assert.equal(response.status, 200);
  assert.equal(calls[0].options.headers.get('Authorization'), null);
  assert.equal((await handler(request('/auth/v1/signup', { method: 'POST' }))).status, 404);
  assert.equal((await handler(request('/auth/v1/token?grant_type=refresh_token', { method: 'POST' }))).status, 404);
});

test('edge runtime prefix variant still reaches the strict login route', async () => {
  const { handler, calls } = setup(() => Response.json({ access_token: 'response-test-only' }));
  const response = await handler(edgeRequest('/auth/v1/token?grant_type=password', { method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: '' }, body: JSON.stringify({ email: 'user@example.test', password: 'fixture-only' }) }));
  assert.equal(response.status, 200);
  assert.equal(calls[0].url, `https://${project}.supabase.co/auth/v1/token?grant_type=password`);
});

test('private report path must use authenticated bucket and random task/run filename', async () => {
  const { handler, calls } = setup();
  const path = `/storage/v1/object/authenticated/reports/${user}/${user}/report-${'a'.repeat(48)}.json`;
  assert.equal((await handler(request(path))).status, 200);
  for (const invalid of [path.replace('authenticated', 'public'), path.replace('report-', ''), path + '?download=1', path.replace('/reports/', '/another/'), '/storage/v1/object/authenticated/reports/%252e%252e/private.json']) {
    assert.equal((await handler(request(invalid))).status, 404);
  }
  assert.equal(calls.length, 1);
});

test('task creation cannot forge creator, completed state, privileged fields or object traversal', async () => {
  const { handler, calls } = setup();
  const task = { task_id: user, store_id: user, created_by: user, self_asin: 'B012345678', product_stage: 'new',
    input_file_path: 'private/input.xlsx', input_file_hash: 'a'.repeat(64), status: 'pending', current_stage: 'ingestion' };
  const submit = body => handler(request('/rest/v1/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));
  assert.equal((await submit(task)).status, 200);
  for (const change of [{ status: 'completed' }, { created_by: 'someone-else' }, { report_path: 'stolen' }, { input_file_path: '../private.xlsx' }])
    assert.equal((await submit({ ...task, ...change })).status, 400);
  assert.equal(calls.length, 1);
});

test('upstream rejection, redirects, non-JSON and network failure are sanitized with exact CORS', async () => {
  for (const respond of [
    () => new Response('sensitive diagnostic', { status: 401, headers: { 'Set-Cookie': 'session=hidden' } }),
    () => new Response('<html>wrong response</html>', { status: 200 }),
    () => new Response(null, { status: 302, headers: { Location: 'https://evil.test' } }),
    () => { throw new Error('sensitive network diagnostic'); },
  ]) {
    const { handler } = setup(respond);
    const result = await handler(request('/rest/v1/tasks'));
    assert.ok(result.status >= 400);
    assert.equal(result.headers.get('access-control-allow-origin'), origin);
    assert.equal(result.headers.get('set-cookie'), null);
    assert.equal(result.headers.get('location'), null);
    assert.doesNotMatch(await result.text(), /sensitive|hidden|evil/);
  }
});

test('configuration rejects wildcard, origin path, arbitrary upstream and credentials', () => {
  for (const config of [
    { allowedOrigin: '*' }, { allowedOrigin: origin + '/repo/' },
    { supabaseUrl: 'https://evil.test' }, { supabaseUrl: `https://user@${project}.supabase.co` },
  ]) assert.throws(() => createGateway({ supabaseUrl: `https://${project}.supabase.co`, allowedOrigin: origin, ...config }));
});

test('private uploads enforce owner, extension, size and non-overwrite before forwarding', async () => {
  const { handler, calls } = setup(() => Response.json({ Key: 'inputs/object' }));
  const path = `/storage/v1/object/inputs/${user}/${user}/${user}/input.csv`;
  assert.equal((await handler(request(path, { method: 'POST', body: 'keyword,clicks\nexample,1' }))).status, 200);
  assert.equal(calls[0].options.headers.get('x-upsert'), 'false');
  assert.equal(calls[0].options.headers.get('Content-Type'), 'text/csv');
  for (const [url, body, expected] of [
    [path.replace(`/${user}/${user}/`, `/${user}/22222222-2222-4222-8222-222222222222/`), 'a,b', 403],
    [path, '', 400], [path, 'a\0b', 400], [path.replace('.csv', '.exe'), 'a,b', 404],
    [path.replace('.csv', '.xlsx'), 'not a workbook', 400], [path, new Uint8Array(10 * 1024 * 1024 + 1), 413],
  ]) assert.equal((await handler(request(url, { method: 'POST', body }))).status, expected);
  assert.equal(calls.length, 1);
});

test('only named user task RPCs are exposed; worker lifecycle RPC remains inaccessible', async () => {
  const { handler, calls } = setup();
  for (const rpc of ['kwcc_submit_task', 'kwcc_submit_task_with_business_inputs', 'kwcc_rerun_task']) {
    assert.equal((await handler(request(`/rest/v1/rpc/${rpc}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }))).status, 200);
  }
  assert.equal((await handler(request('/rest/v1/rpc/kwcc_claim_run', { method: 'POST' }))).status, 404);
  assert.equal(calls.length, 3);
});

test('browser client and gateway integrate login, private upload/register, bound report and logout without direct upstream access', async () => {
  const events = [];
  const taskId = '22222222-2222-4222-8222-222222222222';
  const runId = '33333333-3333-4333-8333-333333333333';
  const reportPath = `${taskId}/${runId}/report-${'a'.repeat(48)}.json`;
  const handler = createGateway({ supabaseUrl: `https://${project}.supabase.co`, allowedOrigin: origin,
    fetchImpl: async (url, options) => {
      const endpoint = new URL(url).pathname;
      events.push(endpoint);
      if (endpoint === '/auth/v1/token') return Response.json({ access_token: token, user: { id: user }, expires_at: 9999999999 });
      assert.equal(options.headers.get('Authorization'), `Bearer ${token}`);
      if (endpoint === '/auth/v1/user') return Response.json({ id: user });
      if (endpoint.startsWith('/storage/v1/object/inputs/')) return Response.json({ Key: 'stored' });
      if (endpoint === '/rest/v1/rpc/kwcc_submit_task_with_business_inputs') {
        const data = JSON.parse(options.body);
        assert.equal(data.p_task_id, taskId); assert.equal(data.p_run_id, runId);
        assert.match(data.p_input_file_hash, /^[0-9a-f]{64}$/);
        assert.deepEqual(data.p_business_inputs, { primary_core_keyword: null, competitor_asins: [],
          core_keywords: [], competitor_selection_version: null, product_facts_version: null,
          feature_review_version: null, checklist_version: null, confirmation_version: null });
        return Response.json({ task_id: taskId, run_id: runId, status: 'pending' });
      }
      if (endpoint === '/rest/v1/tasks') return Response.json([{ task_id: taskId }]);
      if (endpoint === '/rest/v1/task_runs') return Response.json([{ task_id: taskId, run_id: runId, status: 'completed', report_path: reportPath }]);
      if (endpoint === `/storage/v1/object/authenticated/reports/${reportPath}`) return Response.json({
        schema_version: 'report-0.2', task_id: taskId, run_id: runId, rows: [],
        modules: { 'negative-keywords.json': { rows: [], write_back: false } },
      });
      if (endpoint === '/auth/v1/logout') return new Response(null, { status: 204 });
      throw new Error('Unexpected endpoint');
    } });
  const client = clientApi.createClient({ config: { mode: 'live', liveEnabled: true,
    supabaseUrl: `https://${project}.supabase.co`, publicKey: key, gatewayUrl: base },
    fetch: (url, options) => {
      assert.ok(url.startsWith(base + '/'));
      return handler(new Request(url, { ...options, headers: { ...options.headers, Origin: origin } }));
    } });
  await client.auth.signIn('test@example.test', 'fixture-only');
  await client.tasks.create({ task_id: taskId, run_id: runId, store_id: user, self_asin: 'B012345678', product_stage: 'stable',
    file: new File(['keyword,clicks\nexample,1'], 'report.csv') });
  const report = await client.reports.read(taskId, runId);
  assert.equal(report.content.run_id, runId);
  assert.equal(report.content.modules['negative-keywords.json'].write_back, false);
  await client.auth.signOut();
  await assert.rejects(client.reports.read(taskId, runId), { code: 'AUTH_REQUIRED' });
  assert.deepEqual(events, [
    '/auth/v1/token', '/auth/v1/user', `/storage/v1/object/inputs/${user}/${user}/${taskId}/input.csv`,
    '/rest/v1/rpc/kwcc_submit_task_with_business_inputs', '/rest/v1/tasks', '/rest/v1/task_runs',
    `/storage/v1/object/authenticated/reports/${reportPath}`, '/auth/v1/logout',
  ]);
});
