(function (root) {
  'use strict';
  const SESSION_KEY = 'kwcc_live_session';
  const DEMO_KEY = 'kwcc_demo_session';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const stages = ['new', 'growth', 'stable', 'clearance', 'seasonal_restart'];
  class ClientError extends Error {
    constructor(code, message, status = 0) { super(message); this.code = code; this.status = status; }
  }
  const fail = (code, message, status) => { throw new ClientError(code, message, status); };
  function jwtPayload(value) {
    try {
      const part = value.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      return JSON.parse(atob(part));
    } catch (_) { return null; }
  }
  function headerValue(value) {
    if (typeof value !== 'string' || !value || /[\s\x00-\x1f\x7f-\x9f]/.test(value))
      fail('CONFIG_INVALID', '请求凭据格式无效');
    if (/service_role|sb_secret_/i.test(value) || jwtPayload(value)?.role === 'service_role')
      fail('PRIVILEGED_KEY', '浏览器禁止使用服务密钥');
    return value;
  }
  function validateConfig(config = {}) {
    const mode = config.mode ?? 'demo';
    if (!['demo', 'live'].includes(mode)) fail('CONFIG_INVALID', '未知运行模式');
    if (mode === 'demo') return { mode };
    if (config.liveEnabled !== true) fail('LIVE_DISABLED', 'Live 尚未显式启用');
    let url;
    try { url = new URL(config.supabaseUrl); } catch (_) { fail('CONFIG_INVALID', 'Live 服务地址无效'); }
    if (typeof config.supabaseUrl !== 'string' || /[\s\x00-\x1f\x7f-\x9f]/.test(config.supabaseUrl)
      || url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/')
      fail('CONFIG_INVALID', 'Live 服务必须使用无路径、无凭据的 HTTPS origin');
    const key = headerValue(config.publicKey);
    if (!/^sb_publishable_[A-Za-z0-9_-]+$/.test(key)
      && !(key.split('.').length === 3 && jwtPayload(key)?.role === 'anon'))
      fail('CONFIG_INVALID', '前端仅接受公开 publishable / anon key');
    return { mode, origin: url.origin, key };
  }
  function createClient(options = {}) {
    const config = validateConfig(options.config);
    const storage = options.storage;
    const now = options.now || Date.now;
    const listeners = new Set();
    let session = null;
    let generation = 0;
    let state = 'signed_out';
    const emit = value => { state = value; listeners.forEach(fn => fn(value)); };
    const read = key => { try { return storage?.getItem(key); } catch (_) { return null; } };
    const remove = key => { try { storage?.removeItem(key); } catch (_) { /* memory is already cleared */ } };
    function clear(value = 'signed_out') { generation++; session = null; remove(SESSION_KEY); emit(value); }
    function requireSession() {
      if (!session) fail('AUTH_REQUIRED', '请先登录');
      if (!Number.isFinite(session.expires_at) || session.expires_at * 1000 <= now()) {
        clear('expired'); fail('SESSION_EXPIRED', '会话已过期，请重新登录');
      }
      return session;
    }
    async function request(path, { method = 'GET', body, token, rest = false } = {}) {
      if (typeof options.fetch !== 'function') fail('TRANSPORT_MISSING', '未配置请求 transport');
      const headers = { apikey: config.key, Accept: 'application/json' };
      if (token) headers.Authorization = `Bearer ${headerValue(token)}`;
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (rest) {
        headers['Accept-Profile'] = 'public';
        headers['Content-Profile'] = 'public';
        if (method === 'POST') headers.Prefer = 'return=representation';
      }
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await options.fetch(config.origin + path, {
          method, headers, body: body === undefined ? undefined : JSON.stringify(body),
          credentials: 'omit', redirect: 'error', cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) {
          const code = response.status === 401 ? 'AUTH_REQUIRED' : response.status === 403 ? 'FORBIDDEN' : 'REQUEST_FAILED';
          fail(code, response.status === 403 ? '权限不足，操作未获授权' : '请求失败，请重新登录或稍后重试', response.status);
        }
        if (response.status === 204) return null;
        try { return await response.json(); } catch (_) { fail('RESPONSE_INVALID', '服务响应格式无效'); }
      } catch (error) {
        if (error instanceof ClientError) throw error;
        fail('NETWORK_ERROR', '连接失败，操作结果未确认；请刷新查询后再决定是否重试');
      } finally { clearTimeout(timeout); }
    }
    async function privateRequest(path, params) {
      const current = requireSession();
      const stamp = generation;
      try {
        const result = await request(path, { ...params, token: current.access_token, rest: true });
        if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，响应已丢弃');
        requireSession();
        return result;
      } catch (error) {
        if (stamp === generation && [401, 403].includes(error.status)) clear(error.status === 403 ? 'forbidden' : 'expired');
        throw error;
      }
    }
    const liveAuth = {
      mode: 'live',
      async signIn(email, password) {
        clear();
        const stamp = generation;
        emit('signing_in');
        try {
          if (typeof email !== 'string' || !email.trim() || typeof password !== 'string' || !password)
            fail('INPUT_INVALID', '请输入邮箱和密码');
          const result = await request('/auth/v1/token?grant_type=password', { method: 'POST', body: { email: email.trim(), password } });
          headerValue(result?.access_token);
          const expires = Number.isFinite(result.expires_at) ? result.expires_at
            : Number.isFinite(result.expires_in) ? now() / 1000 + result.expires_in : 0;
          if (!UUID.test(result.user?.id) || expires * 1000 <= now()) fail('RESPONSE_INVALID', '登录响应无效或已过期');
          // Validate with Auth, never with a demo flag or decoded JWT alone.
          const user = await request('/auth/v1/user', { token: result.access_token });
          if (user?.id !== result.user.id) fail('RESPONSE_INVALID', '登录用户验证失败');
          if (stamp !== generation) fail('SESSION_CHANGED', '登录已取消');
          session = { access_token: result.access_token, expires_at: expires, user: { id: user.id } };
          requireSession();
          try { storage?.setItem(SESSION_KEY, JSON.stringify(session)); } catch (_) { /* memory-only session */ }
          emit('authenticated');
          return { id: user.id };
        } catch (error) { if (stamp === generation) clear(error.status === 403 ? 'forbidden' : 'signed_out'); throw error; }
      },
      async getUser() {
        if (!session) {
          try { session = JSON.parse(read(SESSION_KEY)); } catch (_) { clear(); }
        }
        if (!session) return null;
        const current = requireSession();
        const stamp = generation;
        try {
          const user = await request('/auth/v1/user', { token: current.access_token });
          if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变');
          if (!UUID.test(user?.id) || user.id !== current.user?.id) fail('RESPONSE_INVALID', '会话验证失败');
          requireSession();
          emit('authenticated');
          return { id: user.id };
        } catch (error) { if (stamp === generation) clear(error.status === 403 ? 'forbidden' : 'expired'); throw error; }
      },
      async signOut() {
        const token = session?.access_token;
        clear();
        if (token) await request('/auth/v1/logout', { method: 'POST', token });
      },
      checkSession: requireSession,
      subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
      get state() { return state; },
    };
    const demoAuth = {
      mode: 'demo',
      async signIn() { storage?.setItem(DEMO_KEY, '1'); emit('demo'); return { id: 'demo', demo: true }; },
      async getUser() { return read(DEMO_KEY) === '1' ? { id: 'demo', demo: true } : null; },
      async signOut() { remove(DEMO_KEY); emit('signed_out'); },
      subscribe: liveAuth.subscribe,
      checkSession() { if (read(DEMO_KEY) !== '1') fail('AUTH_REQUIRED', '请进入演示会话'); },
      get state() { return state; },
    };
    const liveTasks = {
      mode: 'live',
      async list() {
        const rows = await privateRequest('/rest/v1/tasks?select=*&order=created_at.desc');
        if (!Array.isArray(rows)) fail('RESPONSE_INVALID', '任务列表响应无效');
        return rows;
      },
      async create(input = {}) {
        const current = requireSession();
        if (input.file || input.report_file) fail('UPLOAD_UNAVAILABLE', '上传后端尚未接入，文件未上传，未创建任务');
        if (!UUID.test(input.store_id) || !UUID.test(input.task_id) || !/^B0[A-Z0-9]{8}$/.test(input.self_asin)
          || !stages.includes(input.product_stage)) fail('INPUT_INVALID', '店铺、任务 ID、ASIN 或阶段无效');
        // This is an EXISTING private backend object reference, never a file input's value.
        if (typeof input.input_file_path !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_./-]*$/.test(input.input_file_path)
          || input.input_file_path.split('/').some(part => !part || part === '.' || part === '..')
          || !/^[a-f0-9]{64}$/i.test(input.input_file_hash))
          fail('INPUT_INVALID', '需要已有私有对象引用与 SHA-256；本地文件路径无效');
        const payload = {
          task_id: input.task_id, created_by: current.user.id, store_id: input.store_id,
          self_asin: input.self_asin, product_stage: input.product_stage,
          input_file_path: input.input_file_path, input_file_hash: input.input_file_hash,
          status: 'pending', current_stage: 'ingestion',
        };
        const rows = await privateRequest('/rest/v1/tasks', { method: 'POST', body: payload });
        if (!Array.isArray(rows) || rows.length !== 1 || rows[0]?.task_id !== payload.task_id || rows[0]?.status !== 'pending')
          fail('RESPONSE_INVALID', '创建结果未确认，请查询任务列表，不要直接重试');
        return rows[0];
      },
    };
    const liveStrategies = {
      mode: 'live', canWrite: false,
      async list() {
        const rows = await privateRequest('/rest/v1/strategy_configs?select=*&order=created_at.desc');
        if (!Array.isArray(rows)) fail('RESPONSE_INVALID', '策略列表响应无效');
        return rows;
      },
      async save() { fail('STRATEGY_WRITE_DISABLED', '当前 RLS 未允许策略写入；未保存配置'); },
    };
    const defaults = config.mode === 'live' ? { auth: liveAuth, tasks: liveTasks, strategies: liveStrategies } : {
      auth: demoAuth,
      tasks: { mode: 'demo', async create() { return { demo: true, persisted: false }; } },
      strategies: { mode: 'demo', canWrite: false, async save() { return { demo: true, persisted: false }; } },
    };
    // Injection is a trusted application/test seam; cross-mode clients are never accepted.
    const clients = { auth: options.authClient || defaults.auth, tasks: options.taskClient || defaults.tasks, strategies: options.strategyClient || defaults.strategies };
    for (const client of Object.values(clients)) if (client.mode !== config.mode) fail('MODE_MISMATCH', '拒绝跨模式 client');
    return Object.freeze({ mode: config.mode, ...clients });
  }
  const api = { createClient, validateConfig, ClientError };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KWCCClient = api;
})(globalThis);
