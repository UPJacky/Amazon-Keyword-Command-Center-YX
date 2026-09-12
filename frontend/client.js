(function (root) {
  'use strict';
  const SESSION_KEY = 'kwcc_live_session';
  const DEMO_KEY = 'kwcc_demo_session';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const stages = ['new', 'growth', 'stable', 'clearance', 'seasonal_restart'];
  class ClientError extends Error {
    constructor(code, message, status = 0, details = null) { super(message); this.code = code; this.status = status; this.details = details; }
  }
  const fail = (code, message, status, details) => { throw new ClientError(code, message, status, details); };
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
    const project = url.hostname.match(/^([a-z0-9]+)\.supabase\.co$/)?.[1];
    if (project && key.split('.').length === 3 && jwtPayload(key)?.ref !== project)
      fail('CONFIG_INVALID', '公开 key 与 Supabase 项目不匹配');
    let gateway = null;
    if (config.gatewayUrl !== undefined && config.gatewayUrl !== '') {
      let endpoint;
      try { endpoint = new URL(config.gatewayUrl); } catch (_) { fail('CONFIG_INVALID', '应用网关地址无效'); }
      if (endpoint.origin !== url.origin || endpoint.pathname !== '/functions/v1/kwcc-gateway'
        || endpoint.username || endpoint.password || endpoint.search || endpoint.hash
        || endpoint.href !== config.gatewayUrl)
        fail('CONFIG_INVALID', '网关必须是同一 Supabase 项目的受控函数地址');
      gateway = endpoint.href;
    }
    return { mode, origin: url.origin, key, gateway };
  }
  function createClient(options = {}) {
    const config = validateConfig(options.config);
    const storage = options.storage;
    const now = options.now || Date.now;
    const listeners = new Set();
    let session = null;
    let generation = 0;
    let state = 'signed_out';
    const uploadedInputs = new Map();
    const emit = value => { state = value; listeners.forEach(fn => fn(value)); };
    const read = key => { try { return storage?.getItem(key); } catch (_) { return null; } };
    const remove = key => { try { storage?.removeItem(key); } catch (_) { /* memory is already cleared */ } };
    function clear(value = 'signed_out') { generation++; session = null; uploadedInputs.clear(); remove(SESSION_KEY); emit(value); }
    function requireSession() {
      if (!session) fail('AUTH_REQUIRED', '请先登录');
      if (!Number.isFinite(session.expires_at) || session.expires_at * 1000 <= now()) {
        clear('expired'); fail('SESSION_EXPIRED', '会话已过期，请重新登录');
      }
      return session;
    }
    async function request(path, { method = 'GET', body, rawBody, contentType, token, rest = false } = {}) {
      if (typeof options.fetch !== 'function') fail('TRANSPORT_MISSING', '未配置请求 transport');
      const headers = { apikey: config.key, Accept: 'application/json' };
      if (token) headers.Authorization = `Bearer ${headerValue(token)}`;
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (rawBody !== undefined) headers['Content-Type'] = contentType;
      if (rest) {
        headers['Accept-Profile'] = 'public';
        headers['Content-Profile'] = 'public';
        if (method === 'POST') headers.Prefer = 'return=representation';
      }
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await options.fetch((config.gateway || config.origin) + path, {
          method, headers, body: rawBody !== undefined ? rawBody : body === undefined ? undefined : JSON.stringify(body),
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
        const result = await request(path, { rest: true, ...params, token: current.access_token });
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
      mode: 'live', canUpload: Boolean(config.gateway),
      async list() {
        const rows = await privateRequest('/rest/v1/tasks?select=*&order=created_at.desc');
        if (!Array.isArray(rows)) fail('RESPONSE_INVALID', '任务列表响应无效');
        return rows;
      },
      async create(input = {}) {
        const current = requireSession();
        if (input.file || input.report_file) {
          if (!config.gateway) fail('UPLOAD_UNAVAILABLE', '上传网关尚未配置，未上传文件或创建任务');
          return uploadAndCreate(input, current);
        }
        if (config.gateway) fail('UPLOAD_REQUIRED', '请从工具页上传报表后创建任务');
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
      async latestRun(taskId) {
        requireSession();
        if (!UUID.test(taskId || '')) fail('INPUT_INVALID', '任务 ID 无效');
        const rows = await privateRequest(`/rest/v1/task_runs?task_id=eq.${taskId}&select=task_id,run_id,status&order=created_at.desc&limit=1`);
        if (!Array.isArray(rows) || rows.length > 1 || (rows.length && (rows[0].task_id !== taskId || !UUID.test(rows[0].run_id))))
          fail('RESPONSE_INVALID', '运行记录响应无效');
        return rows[0] || null;
      },
      async rerun(taskId, previousRunId, runId) {
        if (!config.gateway) fail('GATEWAY_REQUIRED', '重跑需要已部署的应用网关');
        if (![taskId, previousRunId, runId].every(id => UUID.test(id || '')) || previousRunId === runId)
          fail('INPUT_INVALID', '重跑必须使用新的运行 ID');
        const result = await privateRequest('/rest/v1/rpc/kwcc_rerun_task', { method: 'POST', body: {
          p_task_id: taskId, p_previous_run_id: previousRunId, p_run_id: runId,
        } });
        if (result?.task_id !== taskId || result?.run_id !== runId || result.status !== 'pending')
          fail('RESPONSE_INVALID', '重跑结果未确认，请刷新任务列表');
        return result;
      },
    };
    async function uploadAndCreate(input, current) {
      const stamp = generation;
      const file = input.file || input.report_file;
      const extension = typeof file?.name === 'string' && file.name.toLowerCase().match(/\.(xlsx|csv)$/)?.[1];
      if (!extension || !Number.isInteger(file.size) || file.size <= 0 || file.size > 10 * 1024 * 1024
        || typeof file.arrayBuffer !== 'function') fail('INPUT_INVALID', '请选择 10 MB 内非空的 .xlsx 或 .csv 文件');
      if (![input.task_id, input.run_id, input.store_id].every(id => UUID.test(id || ''))
        || !/^B0[A-Z0-9]{8}$/.test(input.self_asin || '') || !stages.includes(input.product_stage))
        fail('INPUT_INVALID', '请选择店铺、有效 ASIN 与产品阶段');
      const bytes = await file.arrayBuffer();
      if (bytes.byteLength !== file.size) fail('INPUT_INVALID', '文件大小发生变化，请重新选择');
      const cryptoImpl = options.crypto || globalThis.crypto;
      if (!cryptoImpl?.subtle) fail('CRYPTO_REQUIRED', '浏览器需要 HTTPS 和 SHA-256 支持');
      const digest = Array.from(new Uint8Array(await cryptoImpl.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
      if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，上传已取消');
      requireSession();
      const objectPath = `${input.store_id}/${current.user.id}/${input.task_id}/input.${extension}`;
      const signature = [input.run_id, objectPath, digest, input.self_asin, input.product_stage].join('|');
      const existing = uploadedInputs.get(input.task_id);
      if (existing && existing !== signature) fail('TASK_CONFLICT', '本次任务输入已改变，请使用新的任务 ID');
      if (!existing) {
        await privateRequest(`/storage/v1/object/inputs/${objectPath}`, { method: 'POST', rawBody: bytes,
          contentType: extension === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', rest: false });
        uploadedInputs.set(input.task_id, signature);
      }
      if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，任务登记已取消');
      const result = await privateRequest('/rest/v1/rpc/kwcc_submit_task_with_business_inputs', { method: 'POST', body: {
        p_task_id: input.task_id, p_run_id: input.run_id, p_store_id: input.store_id,
        p_self_asin: input.self_asin, p_product_stage: input.product_stage,
        p_input_file_path: objectPath, p_input_file_hash: digest, p_input_size: bytes.byteLength,
        p_business_inputs: { primary_core_keyword: input.primary_core_keyword || null,
          competitor_asins: Array.isArray(input.competitor_asins) ? input.competitor_asins : [],
          core_keywords: Array.isArray(input.core_keywords) ? input.core_keywords : [],
          competitor_selection_version: input.competitor_selection_version || null,
          product_facts_version: input.product_facts_version || null,
          feature_review_version: input.feature_review_version || null,
          checklist_version: input.checklist_version || null,
          confirmation_version: input.confirmation_version || null },
      } });
      if (result?.task_id !== input.task_id || result?.run_id !== input.run_id || result.status !== 'pending')
        fail('RESPONSE_INVALID', '任务登记结果未确认，请刷新查询；重试将沿用本次任务编号');
      return result;
    }
    const liveStores = {
      mode: 'live', async list() {
        const rows = await privateRequest('/rest/v1/stores?select=store_id,name,marketplace&order=name.asc');
        if (!Array.isArray(rows) || rows.some(row => !UUID.test(row?.store_id || ''))) fail('RESPONSE_INVALID', '店铺列表响应无效');
        return rows;
      },
    };
    const liveStrategies = {
      mode: 'live', canWrite: Boolean(config.gateway),
      async list() {
        const rows = await privateRequest('/rest/v1/strategy_configs?select=*&order=created_at.desc');
        if (!Array.isArray(rows)) fail('RESPONSE_INVALID', '策略列表响应无效');
        return rows;
      },
      async permissions() {
        const rows = await privateRequest('/rest/v1/store_memberships?select=store_id,role');
        if (!Array.isArray(rows) || rows.some(row => !UUID.test(row?.store_id || '') || !['user', 'admin'].includes(row.role)))
          fail('RESPONSE_INVALID', '店铺角色响应无效');
        return rows;
      },
      async save(input = {}) {
        if (!config.gateway) fail('STRATEGY_WRITE_DISABLED', '策略写入网关尚未配置；未保存配置');
        requireSession();
        if (!UUID.test(input.config_id || '') || !UUID.test(input.store_id || '') || !stages.includes(input.product_stage)
          || !input.config || typeof input.config !== 'object' || Array.isArray(input.config)
          || typeof input.config_version !== 'string' || typeof input.rule_version !== 'string')
          fail('INPUT_INVALID', '策略版本与配置输入无效');
        const row = await privateRequest('/rest/v1/rpc/kwcc_save_strategy', { method: 'POST', body: {
          p_store_id: input.store_id, p_product_stage: input.product_stage, p_config: input.config,
          p_config_version: input.config_version, p_rule_version: input.rule_version, p_config_id: input.config_id,
        } });
        if (row?.config_id !== input.config_id || row.store_id !== input.store_id || row.config_version !== input.config_version)
          fail('RESPONSE_INVALID', '策略保存结果未确认，请刷新版本列表');
        return row;
      },
      async rollback(input = {}) {
        if (!config.gateway) fail('STRATEGY_WRITE_DISABLED', '策略写入网关尚未配置；未回滚配置');
        requireSession();
        if (!UUID.test(input.config_id || '') || !UUID.test(input.new_config_id || '') || input.config_id === input.new_config_id
          || typeof input.config_version !== 'string') fail('INPUT_INVALID', '回滚需要旧版本和新的配置编号');
        const row = await privateRequest('/rest/v1/rpc/kwcc_rollback_strategy', { method: 'POST', body: {
          p_config_id: input.config_id, p_new_config_id: input.new_config_id, p_config_version: input.config_version,
        } });
        if (row?.config_id !== input.new_config_id || row.config_version !== input.config_version)
          fail('RESPONSE_INVALID', '回滚结果未确认，请刷新版本列表');
        return row;
      },
    };
    function reportIds(taskId, runId) {
      if (typeof taskId !== 'string' || typeof runId !== 'string' || taskId.length !== 36 || runId.length !== 36 || !UUID.test(taskId) || !UUID.test(runId))
        fail('INPUT_INVALID', '请选择任务和运行记录；报告需要有效的 task / run UUID');
      // PostgreSQL uuid is returned in canonical lower case.
      return [taskId.toLowerCase(), runId.toLowerCase()];
    }
    const liveReports = {
      mode: 'live',
      async read(taskId, runId) {
        const current = requireSession();
        const stamp = generation;
        [taskId, runId] = reportIds(taskId, runId);
        // One auth generation and one user token for the entire authorization/object chain.
        const check = () => {
          if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，报告已丢弃');
          requireSession();
        };
        const readBound = async (path, rest = true) => {
          check();
          let result;
          try {
            result = await request(path, { token: current.access_token, rest });
          } catch (error) {
            check();
            if ([401, 403].includes(error.status)) clear(error.status === 403 ? 'forbidden' : 'expired');
            throw error;
          }
          check();
          return result;
        };
        const tasks = await readBound(`/rest/v1/tasks?task_id=eq.${taskId}&select=task_id&limit=2`);
        if (!Array.isArray(tasks) || tasks.length !== 1 || tasks[0]?.task_id !== taskId)
          fail('REPORT_UNAVAILABLE', '报告不存在或无权读取');
        const runs = await readBound(`/rest/v1/task_runs?task_id=eq.${taskId}&run_id=eq.${runId}&select=task_id,run_id,status,report_path&limit=2`);
        if (!Array.isArray(runs) || runs.length !== 1 || runs[0]?.task_id !== taskId || runs[0]?.run_id !== runId)
          fail('REPORT_UNAVAILABLE', '报告不存在或无权读取');
        const run = runs[0];
        if (run.status !== 'completed' || run.report_path === null || run.report_path === undefined)
          fail('REPORT_NOT_GENERATED', '该运行的真实报告尚未生成');
        const prefix = `${taskId}/${runId}/`;
        if (typeof run.report_path !== 'string' || !run.report_path.startsWith(prefix)
          || run.report_path.length !== prefix.length + 60
          || !/^report-[a-f0-9]{48}\.json$/.test(run.report_path.slice(prefix.length)))
          fail('REPORT_PATH_INVALID', '报告对象绑定无效');
        const content = await readBound(`/storage/v1/object/authenticated/reports/${run.report_path}`, false);
        if (!content || Array.isArray(content) || content.schema_version !== 'report-0.2'
          || !Array.isArray(content.rows) || !content.rows.every(row => row && typeof row === 'object' && !Array.isArray(row))
          || ('task_id' in content && content.task_id !== taskId) || ('run_id' in content && content.run_id !== runId))
          fail('RESPONSE_INVALID', '报告结构或运行绑定无效');
        check();
        return { task_id: taskId, run_id: runId, report_path: run.report_path, content };
      },
      async readModule(taskId, runId, name) {
        requireSession();
        const stamp = generation;
        [taskId, runId] = reportIds(taskId, runId);
        if (!['rank-benchmark.json', 'negative-keywords.json', 'competitors.json', 'category-features.json', 'buyer-checklist.json', 'text-evidence.json', 'listing-diagnostics.json', 'optimization-plan.json'].includes(name))
          fail('INPUT_INVALID', '未知报告模块');
        // 004 authorizes only task_runs.report_path: modules must come from that same bundle.
        const report = await liveReports.read(taskId, runId);
        if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，报告已丢弃');
        requireSession();
        const modules = report.content.modules;
        if (modules === undefined || modules === null)
          fail('REPORT_NOT_GENERATED', '该模块尚未生成可读取的真实报告');
        if (typeof modules !== 'object' || Array.isArray(modules))
          fail('RESPONSE_INVALID', '报告模块结构无效');
        const states = report.content.module_states;
        const state = states && typeof states === 'object' && !Array.isArray(states) ? states[name] : null;
        if (!Object.prototype.hasOwnProperty.call(modules, name) || modules[name] === null) {
          if (state?.status === 'failed') fail('REPORT_MODULE_FAILED', '该模块生成失败。', 0, { module_state: state });
          fail('REPORT_NOT_GENERATED', '该模块尚未生成可读取的真实报告。', 0, { module_state: state || { status: 'not_generated', reason: 'artifact_not_generated' } });
        }
        const content = modules[name];
        if (!content || typeof content !== 'object' || Array.isArray(content)
          || ('task_id' in content && content.task_id !== taskId) || ('run_id' in content && content.run_id !== runId))
          fail('RESPONSE_INVALID', '报告模块结构或运行绑定无效');
        const module = { ...content };
        Object.defineProperty(module, '_module_state', {
          value: state?.status ? state : { status: 'partial', reason: 'legacy_bundle_without_module_states' },
          enumerable: false,
        });
        return module;
      },
    };
    const defaults = config.mode === 'live' ? { auth: liveAuth, tasks: liveTasks, strategies: liveStrategies, reports: liveReports, stores: liveStores } : {
      auth: demoAuth,
      tasks: { mode: 'demo', async create() { return { demo: true, persisted: false }; } },
      strategies: { mode: 'demo', canWrite: false, async save() { return { demo: true, persisted: false }; } },
      reports: { mode: 'demo', async read() { fail('REPORT_UNAVAILABLE', '演示报告由页面加载本地 fixture'); } },
      stores: { mode: 'demo', async list() { return []; } },
    };
    // Injection is a trusted application/test seam; cross-mode clients are never accepted.
    const clients = { auth: options.authClient || defaults.auth, tasks: options.taskClient || defaults.tasks, strategies: options.strategyClient || defaults.strategies, reports: options.reportClient || defaults.reports, stores: defaults.stores };
    for (const client of Object.values(clients)) if (client.mode !== config.mode) fail('MODE_MISMATCH', '拒绝跨模式 client');
    return Object.freeze({ mode: config.mode, ...clients });
  }
  const api = { createClient, validateConfig, ClientError };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KWCCClient = api;
})(globalThis);
