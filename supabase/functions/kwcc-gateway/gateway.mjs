// Small, cookie-free application gateway. Upstream RLS remains authoritative.
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const REPORT = new RegExp(`^/storage/v1/object/authenticated/reports/${UUID}/${UUID}/report-[0-9a-f]{48}\\.json$`, 'i');
const INPUT = new RegExp(`^/storage/v1/object/inputs/(${UUID})/(${UUID})/(${UUID})/input\\.(xlsx|csv)$`, 'i');
const TABLES = new Set(['profiles', 'stores', 'store_memberships', 'strategy_configs', 'tasks', 'task_runs']);
const HEADERS = ['authorization', 'apikey', 'content-type', 'accept-profile', 'content-profile', 'prefer'];
const PREFIX = '/functions/v1/kwcc-gateway';

function payload(value) {
  try { return JSON.parse(atob(value.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))); }
  catch { return null; }
}

function publicKey(value, project) {
  if (!value || /[\s\x00-\x1f\x7f-\x9f]/.test(value)) return false;
  if (/^sb_publishable_[A-Za-z0-9_-]+$/.test(value)) return true;
  const decoded = payload(value);
  // Decoding is only a rejection filter. Supabase validates authenticity.
  return decoded?.role === 'anon' && decoded.ref === project;
}

function userToken(value, project) {
  if (!/^Bearer [A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(value || '')) return false;
  const decoded = payload(value.slice(7));
  return decoded?.role === 'authenticated'
    && (!decoded.ref || decoded.ref === project)
    && (!decoded.iss || decoded.iss === `https://${project}.supabase.co/auth/v1`);
}

function route(url, method) {
  // Supabase's Edge runtime strips the public function prefix before invoking
  // the handler, while local contract tests use the full public URL path.
  const path = url.pathname.startsWith(PREFIX + '/')
    ? url.pathname.slice(PREFIX.length)
    : url.pathname;
  if (!path.startsWith('/')) return null;
  if (path === '/auth/v1/token' && method === 'POST'
      && url.search === '?grant_type=password') return { path, login: true };
  if (path === '/auth/v1/user' && method === 'GET' && !url.search) return { path };
  if (path === '/auth/v1/logout' && method === 'POST' && !url.search) return { path, logout: true };
  if (method === 'GET' && REPORT.test(path) && !url.search) return { path };
  const input = path.match(INPUT);
  if (method === 'POST' && input && !url.search) return { path, upload: input };
  if (method === 'POST' && ['kwcc_submit_task', 'kwcc_rerun_task', 'kwcc_save_strategy', 'kwcc_rollback_strategy'].some(name => path === '/rest/v1/rpc/' + name) && !url.search)
    return { path, rest: true, rpc: true };
  const table = path.match(/^\/rest\/v1\/([a-z_]+)$/)?.[1];
  if (TABLES.has(table) && method === 'GET') return { path, rest: true };
  if (table === 'tasks' && method === 'POST' && !url.search) return { path, rest: true, createTask: true };
  return null;
}

async function boundedBytes(stream, limit) {
  if (!stream) return new Uint8Array();
  const reader = stream.getReader();
  const chunks = [];
  let bytes = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) { await reader.cancel(); throw new Error('size'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const joined = new Uint8Array(bytes);
  let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.byteLength; }
  return joined;
}

async function boundedText(stream, limit) {
  return new TextDecoder('utf-8', { fatal: true }).decode(await boundedBytes(stream, limit));
}

function taskBody(data, token) {
  const fields = ['task_id', 'created_by', 'store_id', 'self_asin', 'product_stage', 'input_file_path', 'input_file_hash', 'status', 'current_stage'];
  if (!data || Array.isArray(data) || Object.keys(data).some(k => !fields.includes(k))) return false;
  const uuid = new RegExp(`^${UUID}$`, 'i');
  return uuid.test(data.task_id) && uuid.test(data.store_id)
    && data.created_by === payload(token.slice(7))?.sub
    && /^B0[A-Z0-9]{8}$/.test(data.self_asin || '')
    && ['new', 'growth', 'stable', 'clearance', 'seasonal_restart'].includes(data.product_stage)
    && /^[a-f0-9]{64}$/i.test(data.input_file_hash || '')
    && typeof data.input_file_path === 'string'
    && /^[A-Za-z0-9][A-Za-z0-9_./-]*$/.test(data.input_file_path)
    && data.input_file_path.split('/').every(p => p && p !== '.' && p !== '..')
    && data.status === 'pending' && data.current_stage === 'ingestion';
}

export function createGateway({ supabaseUrl, allowedOrigin, fetchImpl = fetch, timeoutMs = 15000 }) {
  const upstream = new URL(supabaseUrl);
  const origin = new URL(allowedOrigin);
  if (!/^https:\/\/[a-z0-9]+\.supabase\.co\/?$/.test(supabaseUrl)
      || origin.protocol !== 'https:' || origin.origin !== allowedOrigin
      || origin.username || origin.password || origin.search || origin.hash)
    throw new Error('Gateway configuration requires a Supabase origin and an exact HTTPS browser origin');
  const project = upstream.hostname.split('.')[0];

  return async function handle(request) {
    const requestOrigin = request.headers.get('Origin');
    const headers = new Headers({ 'Vary': 'Origin', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    if (requestOrigin === allowedOrigin) headers.set('Access-Control-Allow-Origin', allowedOrigin);
    const reject = (status, code) => new Response(JSON.stringify({ error: code }), {
      status, headers: new Headers([...headers, ['Content-Type', 'application/json']]),
    });
    if (requestOrigin !== allowedOrigin) return reject(403, 'ORIGIN_DENIED');
    const url = new URL(request.url);
    if (url.href.length > 8192) return reject(414, 'URL_TOO_LONG');
    const method = request.method === 'OPTIONS' ? request.headers.get('Access-Control-Request-Method') : request.method;
    const matched = route(url, method);
    if (!matched) return reject(404, 'ROUTE_NOT_ALLOWED');
    if (request.method === 'OPTIONS') {
      const requested = (request.headers.get('Access-Control-Request-Headers') || '').toLowerCase().split(',').map(x => x.trim()).filter(Boolean);
      if (requested.some(h => !HEADERS.includes(h))) return reject(403, 'HEADER_NOT_ALLOWED');
      headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      headers.set('Access-Control-Allow-Headers', HEADERS.join(', '));
      headers.set('Access-Control-Max-Age', '300');
      return new Response(null, { status: 204, headers });
    }
    const key = request.headers.get('apikey');
    const authorization = request.headers.get('authorization');
    if (!publicKey(key, project)) return reject(401, 'PUBLIC_KEY_REQUIRED');
    if (!matched.login && !userToken(authorization, project)) return reject(401, 'AUTH_REQUIRED');
    // Never forward caller cookies, privileged keys, profile overrides, or redirect headers.
    const upstreamHeaders = new Headers({ apikey: key, Accept: 'application/json' });
    if (!matched.login) upstreamHeaders.set('Authorization', authorization);
    if (matched.rest) {
      upstreamHeaders.set('Accept-Profile', 'public');
      upstreamHeaders.set('Content-Profile', 'public');
      if (matched.createTask) upstreamHeaders.set('Prefer', 'return=representation');
    }
    let body;
    if (matched.upload) {
      if (matched.upload[2] !== payload(authorization.slice(7))?.sub) return reject(403, 'INPUT_OWNER_MISMATCH');
      try {
        body = await boundedBytes(request.body, 10 * 1024 * 1024);
        if (!body.length) return reject(400, 'EMPTY_UPLOAD');
        if (matched.upload[4].toLowerCase() === 'xlsx') {
          if (body[0] !== 0x50 || body[1] !== 0x4b || body[2] !== 3 || body[3] !== 4) return reject(400, 'XLSX_INVALID');
          upstreamHeaders.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
        } else {
          if (body.includes(0)) return reject(400, 'CSV_INVALID');
          upstreamHeaders.set('Content-Type', 'text/csv');
        }
      } catch { return reject(413, 'UPLOAD_TOO_LARGE'); }
      upstreamHeaders.set('x-upsert', 'false');
    } else if (method === 'POST' && !matched.logout) {
      if (!/^application\/json(?:;|$)/i.test(request.headers.get('content-type') || '')) return reject(415, 'JSON_REQUIRED');
      try {
        body = await boundedText(request.body, 32768);
        const parsed = JSON.parse(body);
        if (matched.login) {
          if (!parsed || typeof parsed.email !== 'string' || !parsed.email.trim()
              || typeof parsed.password !== 'string' || !parsed.password
              || Object.keys(parsed).some(k => !['email', 'password'].includes(k))) return reject(400, 'LOGIN_INPUT_INVALID');
        } else if (matched.createTask && !taskBody(parsed, authorization)) return reject(400, 'TASK_INPUT_INVALID');
        else if (matched.rpc && (!parsed || Array.isArray(parsed) || typeof parsed !== 'object')) return reject(400, 'RPC_INPUT_INVALID');
      } catch { return reject(400, 'BODY_INVALID'); }
      upstreamHeaders.set('Content-Type', 'application/json');
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(upstream.origin + matched.path + url.search, {
        method, headers: upstreamHeaders, body, signal: controller.signal,
        redirect: 'error', credentials: 'omit', cache: 'no-store',
      });
      if (!response.ok) return reject(response.status >= 400 && response.status <= 599 ? response.status : 502, 'UPSTREAM_REJECTED');
      if (response.status === 204) return new Response(null, { status: 204, headers });
      if (!/^application\/json(?:;|$)/i.test(response.headers.get('content-type') || '')) return reject(502, 'UPSTREAM_FORMAT_INVALID');
      const responseBody = await boundedText(response.body, 16 * 1024 * 1024);
      JSON.parse(responseBody);
      headers.set('Content-Type', 'application/json');
      return new Response(responseBody, { status: response.status, headers });
    } catch { return reject(controller.signal.aborted ? 504 : 502, 'UPSTREAM_UNAVAILABLE'); }
    finally { clearTimeout(timer); }
  };
}
