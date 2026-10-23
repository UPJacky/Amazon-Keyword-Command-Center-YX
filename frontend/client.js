(function (root) {
  'use strict';
  const SESSION_KEY = 'kwcc_live_session';
  const DEMO_KEY = 'kwcc_demo_session';
  const LIVE_SUPABASE_PROJECT_REF = 'fcowaovsbxxtxljjhllp';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const canonicalUuid = value => typeof value === 'string' && UUID.test(value) ? value.toLowerCase() : null;
  const CONFIRMATION_TIMESTAMP = /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/i;
  const REPORT_ARTIFACTS = Object.freeze([
    'rank-benchmark.json', 'negative-keywords.json', 'competitors.json',
    'category-features.json', 'buyer-checklist.json', 'text-evidence.json',
    'listing-diagnostics.json', 'optimization-plan.json',
  ]);
  const BUNDLE_ARTIFACTS = new Set([...REPORT_ARTIFACTS,
    'rules-snapshot.json', 'run-meta.json', 'provider-usage.json',
    'provider-budget-receipts.json', 'business-input-snapshot.json']);
  // Mirrors worker/pipeline/selective_rerun.py: the successor plan only accepts
  // a dependency-closed selection emitted in this exact order.
  const MODULE_DEPENDENCIES = Object.freeze({
    'rank-benchmark.json': Object.freeze([]),
    'negative-keywords.json': Object.freeze([]),
    'competitors.json': Object.freeze([]),
    'category-features.json': Object.freeze([]),
    'buyer-checklist.json': Object.freeze(['category-features.json']),
    'text-evidence.json': Object.freeze(['competitors.json', 'buyer-checklist.json']),
    'listing-diagnostics.json': Object.freeze(['competitors.json', 'buyer-checklist.json']),
    'optimization-plan.json': Object.freeze([]),
  });
  function resolveSelectedModules(requested) {
    const selected = new Set(requested);
    const pending = [...requested];
    while (pending.length) {
      for (const dependency of MODULE_DEPENDENCIES[pending.pop()]) {
        if (selected.has(dependency)) continue;
        selected.add(dependency);
        pending.push(dependency);
      }
    }
    return REPORT_ARTIFACTS.filter(name => selected.has(name));
  }
  const ARTIFACT_HASH_ENCODING = 'kwcc-canonical-numeric-v1';
  const stages = ['new', 'growth', 'stable', 'clearance', 'seasonal_restart'];
  class ClientError extends Error {
    constructor(code, message, status = 0, details = null) { super(message); this.code = code; this.status = status; this.details = details; }
  }
  const fail = (code, message, status, details) => { throw new ClientError(code, message, status, details); };
  function validConfirmationProvenance(actor, timestamp) {
    if (typeof actor !== 'string' || !UUID.test(actor)
      || actor.toLowerCase() === '00000000-0000-0000-0000-000000000000'
      || typeof timestamp !== 'string') return false;
    const match = CONFIRMATION_TIMESTAMP.exec(timestamp);
    if (!match || !Number.isFinite(Date.parse(timestamp))) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return day <= daysInMonth[month - 1];
  }
  function canonicalJSON(value) {
    const normalize = input => {
      if (input === null || typeof input === 'string' || typeof input === 'boolean') return input;
      if (typeof input === 'number') {
        if (!Number.isFinite(input)) fail('RESPONSE_INVALID', '报告证据包含无效数字');
        return input;
      }
      if (Array.isArray(input)) return input.map(normalize);
      if (input && typeof input === 'object') {
        const output = {};
        for (const key of Object.keys(input).sort()) output[key] = normalize(input[key]);
        return output;
      }
      fail('RESPONSE_INVALID', '报告证据结构无效');
    };
    return JSON.stringify(normalize(value));
  }
  function canonicalHashNumber(value) {
    if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value)))
      fail('REPORT_INVALID', '报告数字超出可验证范围');
    if (value === 0) return '0';
    const source = value.toString().toLowerCase();
    const exponentIndex = source.indexOf('e');
    if (exponentIndex < 0) return source;
    const mantissa = source.slice(0, exponentIndex);
    const exponent = Number(source.slice(exponentIndex + 1));
    const negative = mantissa.startsWith('-');
    const unsigned = negative ? mantissa.slice(1) : mantissa;
    const point = unsigned.indexOf('.');
    const digitsBeforePoint = point < 0 ? unsigned.length : point;
    const digits = unsigned.replace('.', '');
    const shiftedPoint = digitsBeforePoint + exponent;
    let expanded;
    if (shiftedPoint <= 0) expanded = `0.${'0'.repeat(-shiftedPoint)}${digits}`;
    else if (shiftedPoint >= digits.length) expanded = `${digits}${'0'.repeat(shiftedPoint - digits.length)}`;
    else expanded = `${digits.slice(0, shiftedPoint)}.${digits.slice(shiftedPoint)}`;
    if (expanded.includes('.')) expanded = expanded.replace(/0+$/, '').replace(/\.$/, '');
    return negative ? `-${expanded}` : expanded;
  }
  function canonicalHashTree(value) {
    if (value === null) return ['null'];
    if (typeof value === 'boolean') return ['boolean', value];
    if (typeof value === 'number') return ['number', canonicalHashNumber(value)];
    if (typeof value === 'string') return ['string', value];
    if (Array.isArray(value)) return ['array', value.map(canonicalHashTree)];
    if (value && typeof value === 'object')
      return ['object', Object.keys(value).sort().map(key => [key, canonicalHashTree(value[key])])];
    fail('REPORT_INVALID', '报告证据结构无效');
  }
  function canonicalMasterRows(rows) {
    return JSON.stringify(canonicalHashTree(rows));
  }
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
    if (url.hostname !== `${LIVE_SUPABASE_PROJECT_REF}.supabase.co`)
      fail('CONFIG_INVALID', 'Live 服务必须使用当前受控网关绑定的 Supabase 项目');
    const key = headerValue(config.publicKey);
    if (!/^sb_publishable_[A-Za-z0-9_-]{20,128}$/.test(key)
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
    if (!gateway) fail('CONFIG_INVALID', 'Live 必须使用受控应用网关');
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
    const activeSubmissions = new Map();
    const emit = value => { state = value; listeners.forEach(fn => fn(value)); };
    const read = key => { try { return storage?.getItem(key); } catch (_) { return null; } };
    const remove = key => { try { storage?.removeItem(key); } catch (_) { /* memory is already cleared */ } };
    function clear(value = 'signed_out') {
      generation++;
      session = null;
      uploadedInputs.clear();
      activeSubmissions.clear();
      remove(SESSION_KEY);
      emit(value);
    }
    function requireSession() {
      if (!session) fail('AUTH_REQUIRED', '请先登录');
      if (!Number.isFinite(session.expires_at) || session.expires_at * 1000 <= now()) {
        clear('expired'); fail('SESSION_EXPIRED', '会话已过期，请重新登录');
      }
      return session;
    }
    async function sha256Text(value) {
      const cryptoImpl = options.crypto || globalThis.crypto;
      if (!cryptoImpl?.subtle || typeof TextEncoder !== 'function')
        fail('CRYPTO_REQUIRED', '浏览器需要 HTTPS 和 SHA-256 支持');
      const bytes = new TextEncoder().encode(value);
      const digest = await cryptoImpl.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    }
    async function sha256JSON(value) { return sha256Text(canonicalJSON(value)); }
    async function validateEvidenceManifest(content, taskId, runId, requestedArtifact = null, checkSession = null) {
      const manifest = content?.evidence_manifest;
      if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest))
        fail('REPORT_INVALID', '报告证据清单缺失或格式无效');
      const legacyManifest = manifest.schema_version === 'report-evidence-0.1';
      const generationScopedManifest = manifest.schema_version === 'report-evidence-0.4';
      const portableManifest = manifest.schema_version === 'report-evidence-0.3' || generationScopedManifest;
      const currentManifest = manifest.schema_version === 'report-evidence-0.2' || portableManifest;
      if ((!legacyManifest && !currentManifest && !portableManifest)
        || manifest.task_id !== taskId || manifest.run_id !== runId
        || typeof manifest.input_sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(manifest.input_sha256)
        || manifest.hash_encoding !== 'utf8-json-sort-keys-compact-ensure-ascii-false'
        || (portableManifest && manifest.artifact_hash_encoding !== ARTIFACT_HASH_ENCODING)
        || (!portableManifest && manifest.artifact_hash_encoding !== undefined)
        || (portableManifest && (typeof manifest.portable_manifest_sha256 !== 'string'
          || !/^[a-f0-9]{64}$/i.test(manifest.portable_manifest_sha256)))
        || !manifest.artifacts || typeof manifest.artifacts !== 'object' || Array.isArray(manifest.artifacts)
        || (generationScopedManifest && (!['full', 'selective'].includes(manifest.generation_scope)
          || content.generation_scope !== manifest.generation_scope
          || (manifest.generation_scope === 'selective'
            && (!content.selective_rerun || typeof content.selective_rerun !== 'object'
              || Array.isArray(content.selective_rerun)
              || !content.module_lineage || typeof content.module_lineage !== 'object'
              || Array.isArray(content.module_lineage)))
          || (manifest.generation_scope === 'full'
            && (content.selective_rerun !== undefined || content.module_lineage !== undefined))))
        || (!generationScopedManifest
          && (manifest.generation_scope !== undefined || content.generation_scope !== undefined))
        || typeof manifest.manifest_sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(manifest.manifest_sha256))
        fail('REPORT_INVALID', '报告证据清单身份或格式无效');
      const artifactNames = Object.keys(manifest.artifacts);
      if (artifactNames.some(name => !BUNDLE_ARTIFACTS.has(name)))
        fail('REPORT_INVALID', '报告包含未注册的证据文件');
      for (const name of artifactNames) {
        const entry = manifest.artifacts[name];
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)
          || typeof entry.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(entry.sha256)
          || !Number.isInteger(entry.bytes) || entry.bytes < 0
          || (portableManifest && (typeof entry.portable_sha256 !== 'string'
            || !/^[a-f0-9]{64}$/i.test(entry.portable_sha256))))
          fail('REPORT_INVALID', '报告证据条目无效');
      }
      if (currentManifest) {
        if (manifest.master_rows_hash_encoding !== 'kwcc-canonical-numeric-v1'
          || typeof manifest.master_rows_sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(manifest.master_rows_sha256)
          || !Number.isInteger(manifest.master_rows_bytes) || manifest.master_rows_bytes < 0
          || !Array.isArray(content.rows))
          fail('REPORT_INVALID', '作战总表哈希字段缺失或格式无效');
        const masterRows = canonicalMasterRows(content.rows);
        const masterRowsDigest = await sha256Text(masterRows);
        if (checkSession) checkSession();
        if (new TextEncoder().encode(masterRows).length !== manifest.master_rows_bytes
          || masterRowsDigest.toLowerCase() !== manifest.master_rows_sha256.toLowerCase())
          fail('REPORT_INVALID', '作战总表内容校验失败');
      }
      if (requestedArtifact !== null && !Object.prototype.hasOwnProperty.call(manifest.artifacts, requestedArtifact))
        fail('REPORT_INVALID', '报告模块未登记在证据清单中');
      const snapshotName = 'business-input-snapshot.json';
      const hasBusinessSnapshot = Object.prototype.hasOwnProperty.call(manifest.artifacts, snapshotName);
      if (hasBusinessSnapshot || manifest.business_input_sha256 !== undefined
        || content.business_input_sha256 !== undefined) {
        const snapshot = content.evidence_artifacts?.[snapshotName];
        const entry = manifest.artifacts[snapshotName];
        if (!entry || !snapshot || typeof manifest.business_input_sha256 !== 'string'
          || !/^[a-f0-9]{64}$/i.test(manifest.business_input_sha256)
          || content.business_input_sha256 !== manifest.business_input_sha256)
          fail('REPORT_INVALID', '业务输入快照校验失败');
        const snapshotDigest = await sha256JSON(snapshot);
        if (checkSession) checkSession();
        if (snapshotDigest.toLowerCase() !== entry.sha256.toLowerCase()
          || snapshotDigest.toLowerCase() !== manifest.business_input_sha256.toLowerCase()
          || new TextEncoder().encode(canonicalJSON(snapshot)).length !== entry.bytes)
          fail('REPORT_INVALID', '业务输入快照校验失败');
      }
      const unsigned = { ...manifest };
      delete unsigned.manifest_sha256;
      if (portableManifest) {
        delete unsigned.portable_manifest_sha256;
        const manifestDigest = await sha256Text(JSON.stringify(canonicalHashTree(unsigned)));
        if (checkSession) checkSession();
        if (manifestDigest.toLowerCase() !== manifest.portable_manifest_sha256.toLowerCase())
          fail('REPORT_INVALID', '报告证据清单校验失败');
      } else {
        const manifestDigest = await sha256JSON(unsigned);
        if (checkSession) checkSession();
        if (manifestDigest.toLowerCase() !== manifest.manifest_sha256.toLowerCase())
          fail('REPORT_INVALID', '报告证据清单校验失败');
      }
      if (requestedArtifact !== null) {
        const module = content.modules?.[requestedArtifact];
        const entry = manifest.artifacts[requestedArtifact];
        if (portableManifest) {
          const portableArtifactDigest = await sha256Text(JSON.stringify(canonicalHashTree(module)));
          if (checkSession) checkSession();
          if (portableArtifactDigest.toLowerCase() !== entry.portable_sha256.toLowerCase())
            fail('REPORT_INVALID', '报告模块内容校验失败');
        } else {
          const canonicalModule = canonicalJSON(module);
          if (new TextEncoder().encode(canonicalModule).length !== entry.bytes)
            fail('REPORT_INVALID', '报告模块字节长度校验失败');
          const artifactDigest = await sha256Text(canonicalModule);
          if (checkSession) checkSession();
          if (artifactDigest.toLowerCase() !== entry.sha256.toLowerCase())
            fail('REPORT_INVALID', '报告模块内容校验失败');
        }
      }
      return manifest;
    }
    async function request(path, { method = 'GET', body, rawBody, contentType, token, rest = false,
      accept = 'application/json', responseType = 'json' } = {}) {
      if (typeof options.fetch !== 'function') fail('TRANSPORT_MISSING', '未配置请求 transport');
      const headers = { apikey: config.key, Accept: accept };
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
        if (responseType === 'arrayBuffer') {
          if (typeof response.arrayBuffer !== 'function') fail('RESPONSE_INVALID', '文件响应格式无效');
          try { return await response.arrayBuffer(); } catch (_) { fail('RESPONSE_INVALID', '文件响应格式无效'); }
        }
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
      async get(taskId) {
        requireSession();
        if (!UUID.test(taskId || '')) fail('INPUT_INVALID', '任务 ID 无效');
        const rows = await privateRequest(`/rest/v1/tasks?task_id=eq.${taskId}&select=task_id,store_id,self_asin,product_stage,input_file_hash,input_size,status,confirmation_version,checklist_version,feature_review_version&limit=2`);
        if (!Array.isArray(rows) || rows.length !== 1 || rows[0]?.task_id !== taskId
          || !UUID.test(rows[0]?.store_id || '') || !/^B0[A-Z0-9]{8}$/.test(rows[0]?.self_asin || '')
          || !/^[a-f0-9]{64}$/i.test(rows[0]?.input_file_hash || ''))
          fail('RESPONSE_INVALID', '任务绑定信息无效');
        return rows[0];
      },
      async create(input = {}) {
        const current = requireSession();
        if (input.file || input.report_file) {
          if (!config.gateway) fail('UPLOAD_UNAVAILABLE', '上传网关尚未配置，未上传文件或创建任务');
          const stamp = generation;
          const storeId = input.store_id;
          if (!UUID.test(storeId || '')) return uploadAndCreate(input, current, stamp);
          const key = `${current.user.id.toLowerCase()}:${storeId.toLowerCase()}`;
          const owner = { stamp };
          if (activeSubmissions.has(key))
            fail('SUBMISSION_IN_PROGRESS', '当前店铺已有提交正在处理；请等待当前结果后再决定是否提交');
          if (stamp !== generation || session?.user?.id !== current.user?.id)
            fail('SESSION_CHANGED', '会话已改变，任务提交已取消');
          activeSubmissions.set(key, owner);
          try { return await uploadAndCreate(input, current, stamp); }
          finally { if (activeSubmissions.get(key) === owner) activeSubmissions.delete(key); }
        }
        if (!config.gateway) fail('GATEWAY_REQUIRED', '真实任务需要网关上传私有文件并原子登记 task/run');
        fail('UPLOAD_REQUIRED', '请上传 XLSX 或 CSV 报表后创建任务');
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
      async rerunSelectedModules(input = {}) {
        if (!config.gateway) fail('GATEWAY_REQUIRED', '选择性重跑需要已部署的应用网关');
        const current = requireSession();
        const stamp = generation;
        const canonicalTaskId = canonicalUuid(input.taskId);
        const canonicalPreviousRunId = canonicalUuid(input.previousRunId);
        const canonicalRunId = canonicalUuid(input.runId);
        const requestedModules = input.requestedModules;
        if (!canonicalTaskId || !canonicalPreviousRunId || !canonicalRunId
          || canonicalPreviousRunId === canonicalRunId)
          fail('INPUT_INVALID', '选择性重跑必须使用有效且互不相同的任务、源运行与新运行 ID');
        if (!Array.isArray(requestedModules) || requestedModules.length < 1
          || requestedModules.some(name => typeof name !== 'string' || !REPORT_ARTIFACTS.includes(name))
          || new Set(requestedModules).size !== requestedModules.length)
          fail('INPUT_INVALID', '请至少选择一个已知报告模块，且不得重复');
        // Resolve the closure synchronously so a caller editing its array while
        // the report is being read cannot change the submitted plan.
        const selectedModules = resolveSelectedModules(requestedModules);
        const assertOperationSession = () => {
          if (stamp !== generation || session !== current || session?.user?.id !== current?.user?.id)
            fail('SESSION_CHANGED', '会话已改变，选择性重跑已取消');
          requireSession();
        };
        // Only an authorized, manifest-verified source report may seed a plan:
        // every hash below is derived from it, never from the caller.
        const report = await liveReports.read(canonicalTaskId, canonicalPreviousRunId, assertOperationSession);
        assertOperationSession();
        const content = report.content;
        const manifest = content.evidence_manifest;
        if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest))
          fail('REPORT_INVALID', '源报告缺少可验证的证据清单');
        const inputSha256 = content.input_sha256;
        if (typeof inputSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(inputSha256)
          || inputSha256 !== manifest.input_sha256
          || typeof manifest.manifest_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(manifest.manifest_sha256))
          fail('REPORT_INVALID', '源报告输入哈希与证据清单不一致');
        const contractVersions = manifest.module_generation_contract_versions;
        if (!contractVersions || typeof contractVersions !== 'object' || Array.isArray(contractVersions)
          || Object.keys(contractVersions).length !== REPORT_ARTIFACTS.length
          || REPORT_ARTIFACTS.some(name => typeof contractVersions[name] !== 'string' || !contractVersions[name]))
          fail('REPORT_INVALID', '源报告模块生成契约版本不完整');
        const rulesSnapshot = content.evidence_artifacts?.['rules-snapshot.json'];
        const rulesEntry = manifest.artifacts?.['rules-snapshot.json'];
        if (!rulesSnapshot || typeof rulesSnapshot !== 'object' || Array.isArray(rulesSnapshot)
          || !rulesEntry || typeof rulesEntry !== 'object')
          fail('REPORT_INVALID', '源报告缺少规则快照');
        const rulesCanonical = canonicalJSON(rulesSnapshot);
        const rulesSnapshotSha256 = await sha256Text(rulesCanonical);
        assertOperationSession();
        if (rulesEntry.sha256 !== rulesSnapshotSha256
          || rulesEntry.bytes !== new TextEncoder().encode(rulesCanonical).length)
          fail('REPORT_INVALID', '源报告规则快照校验失败');
        const businessInputSha256 = manifest.business_input_sha256;
        if (typeof businessInputSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(businessInputSha256))
          fail('REPORT_INVALID', '源报告业务输入哈希缺失');
        // Strings, arrays and objects only: the payload must hash identically
        // under this canonical JSON encoder and the worker's Python encoder.
        const plan = {
          schema_version: 'selective-rerun-plan-0.2',
          task_id: canonicalTaskId,
          source_run_id: canonicalPreviousRunId,
          source_manifest_sha256: manifest.manifest_sha256,
          input_sha256: inputSha256,
          business_input_sha256: businessInputSha256,
          rules_snapshot_sha256: rulesSnapshotSha256,
          selected_modules: selectedModules,
          generation_contract_versions: { ...contractVersions },
        };
        const rerunPlanSha256 = await sha256JSON(plan);
        assertOperationSession();
        const result = await privateRequest('/rest/v1/rpc/kwcc_rerun_task_selected_modules', { method: 'POST', body: {
          p_task_id: canonicalTaskId, p_previous_run_id: canonicalPreviousRunId, p_run_id: canonicalRunId,
          p_selected_modules: selectedModules, p_source_manifest_sha256: plan.source_manifest_sha256,
          p_rerun_plan_sha256: rerunPlanSha256,
        } });
        assertOperationSession();
        if (canonicalUuid(result?.task_id) !== canonicalTaskId || canonicalUuid(result?.run_id) !== canonicalRunId
          || result.status !== 'pending' || !Array.isArray(result.selected_modules)
          || canonicalJSON(result.selected_modules) !== canonicalJSON(selectedModules))
          fail('RESPONSE_INVALID', '选择性重跑结果未确认，请刷新任务列表');
        return { ...result, task_id: canonicalTaskId, run_id: canonicalRunId };
      },
      async confirmChecklistAndRerun(input = {}) {
        if (!config.gateway) fail('GATEWAY_REQUIRED', '确认并重跑需要已部署的应用网关');
        const current = requireSession();
        const stamp = generation;
        const { taskId, previousRunId, runId, version, selfAsin, items, inputHash,
          candidateSnapshot, sourceRunId, excludedItems } = input;
        const canonicalTaskId = canonicalUuid(taskId);
        const canonicalPreviousRunId = canonicalUuid(previousRunId);
        const canonicalRunId = canonicalUuid(runId);
        const canonicalSourceRunId = canonicalUuid(sourceRunId);
        // Snapshot caller-owned arrays and objects before any asynchronous work. Validation
        // and the eventual RPC must use the same values even if the caller edits its inputs.
        const itemsSnapshot = Array.isArray(items) ? Object.freeze(items.slice()) : items;
        const excludedItemsSnapshot = Array.isArray(excludedItems)
          ? Object.freeze(excludedItems.map(item => item && typeof item === 'object' && !Array.isArray(item)
            ? Object.freeze({ ...item }) : item)) : excludedItems;
        let candidateSnapshotForHash = candidateSnapshot;
        if (candidateSnapshot && typeof candidateSnapshot === 'object' && !Array.isArray(candidateSnapshot)
          && Array.isArray(candidateSnapshot.features)) {
          candidateSnapshotForHash = JSON.parse(canonicalJSON(candidateSnapshot));
          const freezeTree = value => {
            if (value && typeof value === 'object') {
              Object.values(value).forEach(freezeTree);
              Object.freeze(value);
            }
            return value;
          };
          freezeTree(candidateSnapshotForHash);
        }
        const candidateIds = [];
        const seenCandidateIds = new Set();
        if (candidateSnapshotForHash && typeof candidateSnapshotForHash === 'object' && !Array.isArray(candidateSnapshotForHash)
          && Array.isArray(candidateSnapshotForHash.features)) {
          for (const feature of candidateSnapshotForHash.features) {
            const id = typeof feature?.feature_id === 'string' ? feature.feature_id.trim()
              : typeof feature?.element_id === 'string' ? feature.element_id.trim() : '';
            const name = typeof feature?.name === 'string' ? feature.name.trim()
              : typeof feature?.element_name === 'string' ? feature.element_name.trim() : '';
            if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(id) || !name || seenCandidateIds.has(id)) continue;
            seenCandidateIds.add(id); candidateIds.push(id);
            if (candidateIds.length === 7) break;
          }
        }
        const validExcluded = Array.isArray(excludedItemsSnapshot) && excludedItemsSnapshot.every(item => item
          && typeof item === 'object' && !Array.isArray(item)
          && Object.keys(item).every(key => ['feature_id', 'reason_code', 'note'].includes(key))
          && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(item.feature_id || '')
          && ['not_relevant', 'not_applicable', 'already_covered', 'unverified', 'other'].includes(item.reason_code)
          && (item.note === undefined || (typeof item.note === 'string' && item.note.trim().length <= 300
            && !/[\r\n\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(item.note)))
          && (item.reason_code !== 'other' || (typeof item.note === 'string' && item.note.trim().length > 0)));
        if (!canonicalTaskId || !canonicalPreviousRunId || !canonicalRunId
          || !canonicalSourceRunId || canonicalPreviousRunId === canonicalRunId
          || !/^B0[A-Z0-9]{8}$/.test(selfAsin || '')
          || !/^checklist-v2-[A-Za-z0-9_.:-]{1,100}$/.test(version || '')
          || !/^[a-f0-9]{64}$/i.test(inputHash || '')
          || !Array.isArray(itemsSnapshot) || itemsSnapshot.length < 1 || itemsSnapshot.length > 7
          || itemsSnapshot.some(item => typeof item !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(item))
          || new Set(itemsSnapshot).size !== itemsSnapshot.length
          || canonicalSourceRunId !== canonicalPreviousRunId
          || candidateIds.length < 1 || !validExcluded
          || new Set(excludedItemsSnapshot.map(item => item.feature_id)).size !== excludedItemsSnapshot.length
          || itemsSnapshot.some(item => excludedItemsSnapshot.some(excluded => excluded.feature_id === item))
          || new Set([...itemsSnapshot, ...excludedItemsSnapshot.map(item => item.feature_id)]).size !== candidateIds.length
          || candidateIds.some(id => !itemsSnapshot.includes(id) && !excludedItemsSnapshot.some(item => item.feature_id === id)))
          fail('INPUT_INVALID', '确认清单或运行绑定无效');
        const candidateSnapshotSha256 = await sha256Text(JSON.stringify(canonicalHashTree(candidateSnapshotForHash)));
        if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，清单确认已取消');
        requireSession();
        const result = await privateRequest('/rest/v1/rpc/kwcc_confirm_task_and_rerun_v2', { method: 'POST', body: {
          p_task_id: canonicalTaskId, p_previous_run_id: canonicalPreviousRunId, p_run_id: canonicalRunId,
          p_version: version, p_self_asin: selfAsin, p_items: itemsSnapshot, p_excluded_items: excludedItemsSnapshot,
          p_source_run_id: canonicalSourceRunId, p_candidate_snapshot_sha256: candidateSnapshotSha256,
          p_input_hash: inputHash,
        } });
        if (canonicalUuid(result?.task_id) !== canonicalTaskId || canonicalUuid(result?.run_id) !== canonicalRunId
          || result.status !== 'pending'
          || result.confirmation_version !== version)
          fail('RESPONSE_INVALID', '确认与重跑结果未确认，请刷新任务列表');
        return { ...result, task_id: canonicalTaskId, run_id: canonicalRunId };
      },
      async listNegativeReviewConfirmations(taskId, storeId, runId, reportHash, selfAsin) {
        requireSession();
        if (!UUID.test(taskId || '') || !UUID.test(storeId || '') || !UUID.test(runId || '')
          || !/^[a-f0-9]{64}$/.test(reportHash || '') || !/^B0[A-Z0-9]{8}$/.test(selfAsin || ''))
          fail('INPUT_INVALID', '否词确认查询缺少有效任务、运行、报告或 ASIN 绑定');
        const query = new URLSearchParams({
          object_id: 'eq.negative-review', task_id: `eq.${taskId}`, store_id: `eq.${storeId}`,
          self_asin: `eq.${selfAsin}`, 'items->0->>run_id': `eq.${runId}`,
          'items->0->>report_sha256': `eq.${reportHash}`, input_hash: `eq.${reportHash}`,
          select: 'confirmation_id,object_id,version,store_id,task_id,self_asin,status,items,input_hash,confirmed_by,confirmed_at',
          order: 'confirmed_at.desc', limit: '200',
        });
        const rows = await privateRequest(`/rest/v1/task_confirmations?${query.toString()}`);
        if (!Array.isArray(rows) || rows.length > 200)
          fail('RESPONSE_INVALID', '否词确认历史格式或任务绑定无效');
        for (const row of rows) {
          const meta = row?.items?.[0];
          if (!row || row.object_id !== 'negative-review' || row.task_id !== taskId
            || row.store_id !== storeId || row.self_asin !== selfAsin || !UUID.test(row.confirmation_id || '')
            || !/^negative-v1-[a-f0-9]{64}$/.test(row.version || '') || row.status !== 'confirmed'
            || !Array.isArray(row.items) || row.items.length !== 1 || !/^[a-f0-9]{64}$/.test(row.input_hash || '')
            || !validConfirmationProvenance(row.confirmed_by, row.confirmed_at) || !meta || Array.isArray(meta)
            || Object.keys(meta).length !== 5
            || !['kind', 'schema_version', 'run_id', 'report_sha256', 'candidates'].every(key => Object.hasOwn(meta, key))
            || meta.kind !== 'negative-review-confirmation'
            || meta.schema_version !== 'negative-review-confirmation-0.1' || meta.run_id !== runId
            || meta.report_sha256 !== reportHash || row.input_hash !== reportHash
            || !Array.isArray(meta.candidates) || meta.candidates.length < 1 || meta.candidates.length > 5000)
            fail('RESPONSE_INVALID', '否词确认历史格式或任务/运行/报告绑定无效');
          const candidates = meta.candidates;
          if (candidates.some(item => !item || typeof item !== 'object' || Array.isArray(item)
            || Object.keys(item).length !== 2 || !['exact_negative', 'phrase_negative'].includes(item.group)
            || typeof item.keyword !== 'string' || item.keyword.length < 1 || item.keyword.length > 200
            || item.keyword !== item.keyword.trim() || /[\r\n\u0000-\u001f\u007f\u2028\u2029]/.test(item.keyword))
            || new Set(candidates.map(item => item.keyword.normalize('NFC').trim().toLowerCase().replace(/\s+/g, ' '))).size !== candidates.length)
            fail('RESPONSE_INVALID', '否词确认历史候选身份无效');
          const orderedCandidates = [...candidates].sort((a, b) => a.group.localeCompare(b.group)
            || a.keyword.normalize('NFC').trim().toLowerCase().replace(/\s+/g, ' ')
              .localeCompare(b.keyword.normalize('NFC').trim().toLowerCase().replace(/\s+/g, ' ')));
          if (canonicalJSON(candidates) !== canonicalJSON(orderedCandidates))
            fail('RESPONSE_INVALID', '否词确认历史候选顺序无效');
          const expectedVersion = `negative-v1-${await sha256JSON({ schema_version: 'negative-review-confirmation-0.1',
            task_id: taskId.toLowerCase(), run_id: runId.toLowerCase(), report_sha256: reportHash,
            candidates: orderedCandidates })}`;
          if (row.version !== expectedVersion)
            fail('RESPONSE_INVALID', '否词确认历史版本与候选身份不匹配');
        }
        return rows;
      },
      async confirmNegativeReview(input = {}) {
        if (!config.gateway) fail('GATEWAY_REQUIRED', '持久化否词确认需要已部署的应用网关');
        const current = requireSession();
        const stamp = generation;
        // Freeze the auth generation and a deep copy of the candidates before the first
        // await: a logout or re-login during the digest must never turn this confirmation
        // into the next user's write.
        const assertOperationSession = () => {
          if (stamp !== generation || session !== current || session?.user?.id !== current.user?.id)
            fail('SESSION_CHANGED', '会话已改变，否词确认已取消');
          requireSession();
        };
        const { taskId, runId, version, selfAsin, reportHash, candidates } = input;
        if (![taskId, runId].every(id => UUID.test(id || ''))
          || !/^negative-v1-[a-f0-9]{64}$/.test(version || '')
          || !/^B0[A-Z0-9]{8}$/.test(selfAsin || '')
          || !/^[a-f0-9]{64}$/.test(reportHash || '')
          || !Array.isArray(candidates) || candidates.length < 1 || candidates.length > 5000
          || candidates.some(item => !item || typeof item !== 'object' || Array.isArray(item)
            || Object.keys(item).length !== 2 || !['exact_negative', 'phrase_negative'].includes(item.group)
            || typeof item.keyword !== 'string' || item.keyword.length < 1 || item.keyword.length > 200
            || item.keyword !== item.keyword.trim() || /[\r\n\u0000-\u001f\u007f\u2028\u2029]/.test(item.keyword))
          || new Set(candidates.map(item => item.keyword.normalize('NFC').trim().toLowerCase().replace(/\s+/g, ' '))).size !== candidates.length)
          fail('INPUT_INVALID', '否词确认内容或报告版本无效');
        const candidatesSnapshot = Object.freeze(candidates.map(item =>
          Object.freeze({ group: item.group, keyword: item.keyword })));
        const orderedCandidates = [...candidatesSnapshot].sort((a, b) => a.group.localeCompare(b.group)
          || a.keyword.normalize('NFC').trim().toLowerCase().replace(/\s+/g, ' ')
            .localeCompare(b.keyword.normalize('NFC').trim().toLowerCase().replace(/\s+/g, ' ')));
        const expectedVersion = `negative-v1-${await sha256JSON({ schema_version: 'negative-review-confirmation-0.1',
          task_id: taskId.toLowerCase(), run_id: runId.toLowerCase(), report_sha256: reportHash,
          candidates: orderedCandidates })}`;
        assertOperationSession();
        if (version !== expectedVersion) fail('INPUT_INVALID', '否词确认版本与任务/运行/报告/候选内容不匹配');
        assertOperationSession();
        const result = await privateRequest('/rest/v1/rpc/kwcc_confirm_negative_review', { method: 'POST', body: {
          p_task_id: taskId, p_run_id: runId, p_version: version, p_self_asin: selfAsin,
          p_report_hash: reportHash, p_candidates: orderedCandidates,
        } });
        assertOperationSession();
        const savedMeta = result?.items?.[0];
        if (result?.object_id !== 'negative-review' || result.version !== version || result.task_id !== taskId
          || result.self_asin !== selfAsin || result.status !== 'confirmed' || result.input_hash !== reportHash
          || !Array.isArray(result.items) || result.items.length !== 1
          || savedMeta?.kind !== 'negative-review-confirmation'
          || savedMeta.schema_version !== 'negative-review-confirmation-0.1'
          || savedMeta.run_id !== runId || savedMeta.report_sha256 !== reportHash
          || canonicalJSON(savedMeta.candidates) !== canonicalJSON(orderedCandidates)
          || !UUID.test(result.confirmation_id || '')
          || !UUID.test(result.store_id || '')
          || !validConfirmationProvenance(result.confirmed_by, result.confirmed_at))
          fail('RESPONSE_INVALID', '否词确认结果未验证；请刷新确认记录后再操作');
        assertOperationSession();
        return result;
      },
    };
    async function uploadAndCreate(input, current, stamp = generation) {
      const assertOperationSession = () => {
        if (stamp !== generation || session?.user?.id !== current.user?.id)
          fail('SESSION_CHANGED', '会话已改变，提交已取消');
        requireSession();
      };
      const file = input.file || input.report_file;
      const fileName = file?.name;
      const fileSize = file?.size;
      const extension = typeof fileName === 'string' && fileName.toLowerCase().match(/\.(xlsx|csv)$/)?.[1];
      if (!extension || !Number.isInteger(fileSize) || fileSize <= 0 || fileSize > 10 * 1024 * 1024
        || typeof file.arrayBuffer !== 'function') fail('INPUT_INVALID', '请选择 10 MB 内非空的 .xlsx 或 .csv 文件');
      const hasExplicitIdentity = input.task_id !== undefined || input.run_id !== undefined;
      if ((hasExplicitIdentity && ![input.task_id, input.run_id].every(id => UUID.test(id || '')))
        || !UUID.test(input.store_id || '')
        || !/^B0[A-Z0-9]{8}$/.test(input.self_asin || '') || !stages.includes(input.product_stage))
        fail('INPUT_INVALID', '请选择店铺、有效 ASIN 与产品阶段');
      const storeId = input.store_id.toLowerCase();
      const selfAsin = input.self_asin;
      const productStage = input.product_stage;
      const explicitTaskId = hasExplicitIdentity ? input.task_id.toLowerCase() : null;
      const explicitRunId = hasExplicitIdentity ? input.run_id.toLowerCase() : null;
      const competitorInput = input.competitor_asins ?? [];
      if (!Array.isArray(competitorInput) || competitorInput.length > 5
        || competitorInput.some(value => typeof value !== 'string'))
        fail('INPUT_INVALID', '指定竞对最多 5 个，请检查后重新提交');
      const competitorAsins = competitorInput.map(value => value.trim().toUpperCase());
      if (competitorAsins.some(value => !/^B0[A-Z0-9]{8}$/.test(value) || value === selfAsin)
        || new Set(competitorAsins).size !== competitorAsins.length)
        fail('INPUT_INVALID', '指定竞对 ASIN 无效、重复或包含自有 ASIN');
      const primaryInput = input.primary_core_keyword ?? null;
      if (primaryInput !== null && typeof primaryInput !== 'string')
        fail('INPUT_INVALID', '主关键词必须是文本');
      const primaryCoreKeyword = primaryInput === null ? null : primaryInput.trim();
      const keywordInput = input.core_keywords === undefined
        ? (primaryCoreKeyword ? [primaryCoreKeyword] : []) : (input.core_keywords ?? []);
      if (!Array.isArray(keywordInput) || keywordInput.length > 200
        || keywordInput.some(value => typeof value !== 'string'))
        fail('INPUT_INVALID', '关键词最多 200 个，且每项必须是文本');
      const coreKeywords = keywordInput.map(value => value.trim());
      const invalidKeyword = value => value.length === 0 || Array.from(value).length > 200
        || /[\u0000-\u001f\u007f-\u009f]/u.test(value);
      if ((primaryCoreKeyword !== null && invalidKeyword(primaryCoreKeyword))
        || coreKeywords.some(invalidKeyword)
        || (primaryCoreKeyword && !coreKeywords.includes(primaryCoreKeyword)))
        fail('INPUT_INVALID', '关键词不得超过 200 个字符；主关键词也必须包含在关键词列表中');
      const businessInputs = { primary_core_keyword: primaryCoreKeyword,
        competitor_asins: competitorAsins, core_keywords: coreKeywords };
      for (const field of ['competitor_selection_version', 'product_facts_version',
        'feature_review_version', 'checklist_version', 'confirmation_version']) {
        const value = input[field] ?? null;
        if (value !== null && (typeof value !== 'string' || Array.from(value).length > 128
          || /[\u0000-\u001f\u007f-\u009f]/u.test(value)))
          fail('INPUT_INVALID', `版本标识 ${field} 无效`);
        businessInputs[field] = value;
      }
      const strategyId = input.strategy_id ?? null;
      if (strategyId !== null && !UUID.test(strategyId)) fail('INPUT_INVALID', '策略版本标识无效');
      assertOperationSession();
      const bytes = await file.arrayBuffer();
      assertOperationSession();
      if (bytes.byteLength !== fileSize) fail('INPUT_INVALID', '文件大小发生变化，请重新选择');
      const cryptoImpl = options.crypto || globalThis.crypto;
      if (!cryptoImpl?.subtle) fail('CRYPTO_REQUIRED', '浏览器需要 HTTPS 和 SHA-256 支持');
      assertOperationSession();
      const fileDigest = await cryptoImpl.subtle.digest('SHA-256', bytes);
      assertOperationSession();
      const digest = Array.from(new Uint8Array(fileDigest), b => b.toString(16).padStart(2, '0')).join('');
      assertOperationSession();
      const requestIdentity = await sha256JSON({
        user_id: current.user.id.toLowerCase(), store_id: storeId, input_file_hash: digest,
        input_file_size: bytes.byteLength, input_file_extension: extension,
        self_asin: selfAsin, product_stage: productStage,
        strategy_id: strategyId, business_inputs: businessInputs,
      });
      assertOperationSession();
      const draftKey = `kwcc_live_submission_v1:${current.user.id.toLowerCase()}:${storeId}`;
      let draftText;
      try {
        assertOperationSession();
        if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function')
          fail('RECOVERY_UNAVAILABLE', '当前浏览器无法安全保存提交身份；未上传或创建任务');
        draftText = storage.getItem(draftKey);
        assertOperationSession();
      } catch (error) {
        if (error instanceof ClientError) throw error;
        fail('RECOVERY_UNAVAILABLE', '当前浏览器无法读取提交恢复记录；未上传或创建任务');
      }
      let draft = null;
      if (draftText !== null && draftText !== undefined) {
        try { draft = JSON.parse(draftText); } catch (_) {
          fail('SUBMISSION_RECOVERY_INVALID', '提交恢复记录损坏；请勿创建新任务，请联系支持人员');
        }
        if (!draft || draft.schema_version !== 1 || !UUID.test(draft.task_id || '')
          || !UUID.test(draft.run_id || '') || !/^[a-f0-9]{64}$/.test(draft.request_sha256 || ''))
          fail('SUBMISSION_RECOVERY_INVALID', '提交恢复记录无效；请勿创建新任务，请联系支持人员');
        if (draft.request_sha256 !== requestIdentity)
          fail('TASK_CONFLICT', '已有提交结果尚未确认；请重新选择原文件并保持输入不变以恢复同一任务');
      }
      const cryptoIds = options.crypto || globalThis.crypto;
      const taskId = draft?.task_id || (hasExplicitIdentity
        ? explicitTaskId : cryptoIds?.randomUUID?.()?.toLowerCase());
      const runId = draft?.run_id || (hasExplicitIdentity
        ? explicitRunId : cryptoIds?.randomUUID?.()?.toLowerCase());
      if (!UUID.test(taskId || '') || !UUID.test(runId || ''))
        fail('CRYPTO_REQUIRED', '浏览器无法生成稳定的 task/run 身份；未上传或创建任务');
      if (hasExplicitIdentity && draft
        && (explicitTaskId !== taskId || explicitRunId !== runId))
        fail('TASK_CONFLICT', '已有提交身份与当前 task/run 不一致；未继续提交');
      if (!draft) {
        draft = { schema_version: 1, task_id: taskId, run_id: runId, request_sha256: requestIdentity };
        try {
          assertOperationSession();
          storage.setItem(draftKey, JSON.stringify(draft));
          assertOperationSession();
        } catch (error) {
          if (error instanceof ClientError) throw error;
          fail('RECOVERY_UNAVAILABLE', '无法保存稳定提交身份；未上传或创建任务');
        }
      }
      const objectPath = `${storeId}/${current.user.id.toLowerCase()}/${taskId}/input.${extension}`;
      const signature = [runId, objectPath, digest, selfAsin, productStage,
        strategyId || '', JSON.stringify(businessInputs)].join('|');
      const existing = uploadedInputs.get(taskId);
      if (existing && existing !== signature) fail('TASK_CONFLICT', '本次任务输入已改变，请使用新的任务 ID');
      const recoveryBody = {
        p_task_id: taskId, p_run_id: runId, p_store_id: storeId,
        p_self_asin: selfAsin, p_product_stage: productStage,
        p_input_file_path: objectPath, p_input_file_hash: digest, p_input_size: bytes.byteLength,
        p_strategy_id: strategyId, p_business_inputs: businessInputs,
      };
      const authorizeRecovery = async () => {
        assertOperationSession();
        const recovery = await privateRequest('/rest/v1/rpc/kwcc_submit_task_with_business_inputs', {
          method: 'POST', body: { ...recoveryBody, p_contract_version: 'private-input-recovery-0.1' },
        });
        assertOperationSession();
        const commonKeys = ['contract_version', 'outcome', 'store_id', 'task_id', 'run_id',
          'input_file_path', 'input_file_hash', 'input_size'];
        const allowedOutcomes = ['registered', 'upload_only', 'confirmed_absent', 'permission_denied', 'unknown'];
        if (!recovery || typeof recovery !== 'object' || Array.isArray(recovery)
          || commonKeys.some(key => !Object.hasOwn(recovery, key))
          || Object.keys(recovery).some(key => ![...commonKeys, 'status', 'reason'].includes(key))
          || recovery.contract_version !== 'private-input-recovery-0.1'
          || !allowedOutcomes.includes(recovery.outcome)
          || recovery.store_id !== storeId || recovery.task_id !== taskId || recovery.run_id !== runId
          || recovery.input_file_path !== objectPath || recovery.input_file_hash !== digest
          || recovery.input_size !== bytes.byteLength
          || (recovery.outcome === 'registered'
            && !['pending', 'processing', 'completed', 'failed'].includes(recovery.status))
          || (recovery.outcome !== 'registered' && Object.hasOwn(recovery, 'status'))
          || (Object.hasOwn(recovery, 'reason')
            && (recovery.outcome !== 'unknown' || !['unsupported_contract', 'invalid_input',
              'identity_conflict', 'object_conflict', 'authorization_check_failed'].includes(recovery.reason))))
          fail('SUBMISSION_STATE_UNKNOWN', '提交恢复授权响应格式或身份绑定无效；恢复草稿已保留');
        return recovery;
      };
      const readAuthorizedObject = async () => {
        assertOperationSession();
        try {
          const stored = await privateRequest(`/storage/v1/object/authenticated/inputs/${objectPath}`, {
            rest: false, accept: '*/*', responseType: 'arrayBuffer',
          });
          assertOperationSession();
          return stored;
        } catch (error) {
          if (stamp !== generation || session?.user?.id !== current.user?.id) {
            if (error instanceof ClientError && [401, 403].includes(error.status)) throw error;
            fail('SESSION_CHANGED', '会话已改变，输入对象响应已丢弃');
          }
          if (error.status === 404)
            fail('SUBMISSION_STATE_UNKNOWN', '授权确认的输入对象读取失败；未按 404 判断对象不存在，恢复草稿已保留');
          throw error;
        }
      };
      const verifyAuthorizedObject = async stored => {
        if (!(stored instanceof ArrayBuffer) || stored.byteLength !== bytes.byteLength)
          fail('TASK_CONFLICT', '同一 task/run 的私有输入对象与当前文件不一致；未覆盖对象或登记任务');
        assertOperationSession();
        const storedDigest = await cryptoImpl.subtle.digest('SHA-256', stored);
        assertOperationSession();
        const storedHash = Array.from(new Uint8Array(storedDigest), b => b.toString(16).padStart(2, '0')).join('');
        if (storedHash !== digest)
          fail('TASK_CONFLICT', '同一 task/run 的私有输入 hash 不匹配；未覆盖对象或登记任务');
      };
      const submitTask = async () => {
        assertOperationSession();
        const result = await privateRequest('/rest/v1/rpc/kwcc_submit_task_with_business_inputs', {
          method: 'POST', body: recoveryBody,
        });
        assertOperationSession();
        if (result?.task_id !== taskId || result?.run_id !== runId
          || result.demo === true || result.persisted === false
          || !['pending', 'processing', 'completed', 'failed'].includes(result.status))
          fail('RESPONSE_INVALID', '任务登记结果未确认，请刷新查询；重试将沿用本次 task/run 编号');
        return result;
      };
      const clearConfirmedDraft = () => {
        try {
          assertOperationSession();
          const currentDraftText = storage.getItem(draftKey);
          assertOperationSession();
          const currentDraft = JSON.parse(currentDraftText || 'null');
          if (currentDraft?.task_id === taskId && currentDraft?.run_id === runId) {
            assertOperationSession();
            storage.removeItem(draftKey);
            assertOperationSession();
          }
        } catch (error) {
          if (error instanceof ClientError) throw error;
          // A confirmed server result remains authoritative if draft cleanup fails.
        }
      };
      const completeRegistered = status => {
        assertOperationSession();
        uploadedInputs.set(taskId, signature);
        assertOperationSession();
        return { task_id: taskId, run_id: runId, status };
      };
      const authorizeAndFinish = async recovery => {
        if (recovery.outcome === 'registered') return completeRegistered(recovery.status);
        if (recovery.outcome === 'permission_denied')
          fail('RECOVERY_PERMISSION_DENIED', '当前账号无权恢复此店铺提交；原恢复草稿已保留');
        if (recovery.outcome === 'unknown') {
          if (recovery.reason === 'identity_conflict')
            fail('TASK_CONFLICT', '提交身份与现有 task/run 不匹配；原恢复草稿已保留');
          fail('SUBMISSION_STATE_UNKNOWN', '无法确认提交或私有输入状态；原恢复草稿已保留');
        }
        if (recovery.outcome === 'upload_only') {
          const stored = await readAuthorizedObject();
          await verifyAuthorizedObject(stored);
          return submitTask();
        }
        if (recovery.outcome !== 'confirmed_absent')
          fail('SUBMISSION_STATE_UNKNOWN', '无法确认输入对象状态；原恢复草稿已保留');

        let uploaded = false;
        try {
          assertOperationSession();
          await privateRequest(`/storage/v1/object/inputs/${objectPath}`, { method: 'POST', rawBody: bytes,
            contentType: extension === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', rest: false });
          assertOperationSession();
          uploaded = true;
        } catch (error) {
          if (stamp !== generation || session?.user?.id !== current.user?.id) {
            if (error instanceof ClientError && [401, 403].includes(error.status)) throw error;
            fail('SESSION_CHANGED', '会话已改变，上传响应已丢弃');
          }
          if (error.status !== 409) throw error;
        }
        if (!uploaded) {
          const collisionState = await authorizeRecovery();
          if (collisionState.outcome === 'registered') return completeRegistered(collisionState.status);
          if (collisionState.outcome !== 'upload_only')
            fail('SUBMISSION_STATE_UNKNOWN', '上传冲突后的对象状态未确认；未覆盖对象或重复上传，恢复草稿已保留');
          const stored = await readAuthorizedObject();
          await verifyAuthorizedObject(stored);
        }
        return submitTask();
      };
      const recovery = await authorizeRecovery();
      const result = await authorizeAndFinish(recovery);
      assertOperationSession();
      if (result?.task_id === taskId && result?.run_id === runId) {
        // Only a server-confirmed registration is cached for this generation.
        uploadedInputs.set(taskId, signature);
        clearConfirmedDraft();
      }
      assertOperationSession();
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
      async read(taskId, runId, checkOperationSession = null) {
        const current = requireSession();
        const stamp = generation;
        [taskId, runId] = reportIds(taskId, runId);
        // One auth generation and one user token for the entire authorization/object chain.
        const check = () => {
          if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，报告已丢弃');
          requireSession();
        };
        const readBound = async (path, rest = true) => {
          // Report reads are idempotent.  A transient Gateway 502/503/504
          // must not turn an existing private report into a false
          // "not generated" result, but writes and uploads are never retried
          // by this helper. Keep the retry count small and bounded.
          const retryable = error => [502, 503, 504].includes(error?.status);
          const delays = [250, 750];
          for (let attempt = 0; ; attempt += 1) {
            check();
            let result;
            try {
              result = await request(path, { token: current.access_token, rest });
            } catch (error) {
              check();
              if ([401, 403].includes(error.status)) clear(error.status === 403 ? 'forbidden' : 'expired');
              if (!retryable(error) || attempt >= delays.length) throw error;
              await new Promise(resolve => setTimeout(resolve, delays[attempt]));
              continue;
            }
            // Keep the post-request session check outside the retry catch so
            // expiry/change errors retain their original security semantics.
            check();
            return result;
          }
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
          || content.task_id !== taskId || content.run_id !== runId)
          fail('RESPONSE_INVALID', '报告结构或运行绑定无效');
        if (content.report_scope !== 'ad_only' || content.evidence_manifest)
          await validateEvidenceManifest(content, taskId, runId, null, checkOperationSession);
        if (checkOperationSession) checkOperationSession();
        check();
        return { task_id: taskId, run_id: runId, report_path: run.report_path, content };
      },
      async readFailureReceipt(taskId, runId) {
        const current = requireSession();
        const stamp = generation;
        [taskId, runId] = reportIds(taskId, runId);
        const check = () => {
          if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，失败回执已丢弃');
          requireSession();
        };
        const readBound = async (path, rest = true) => {
          const delays = [250, 750];
          for (let attempt = 0; ; attempt += 1) {
            check();
            let result;
            try {
              result = await request(path, { token: current.access_token, rest });
            } catch (error) {
              check();
              if ([401, 403].includes(error.status)) clear(error.status === 403 ? 'forbidden' : 'expired');
              if (![502, 503, 504].includes(error?.status) || attempt >= delays.length) throw error;
              await new Promise(resolve => setTimeout(resolve, delays[attempt]));
              continue;
            }
            check();
            return result;
          }
        };
        const exactKeys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value)
          && Object.keys(value).length === expected.length
          && expected.every(key => Object.prototype.hasOwnProperty.call(value, key));
        const tasks = await readBound(`/rest/v1/tasks?task_id=eq.${taskId}&select=task_id&limit=2`);
        if (!Array.isArray(tasks) || tasks.length !== 1 || tasks[0]?.task_id !== taskId)
          fail('REPORT_UNAVAILABLE', '失败回执不存在或无权读取');
        const runs = await readBound(`/rest/v1/task_runs?task_id=eq.${taskId}&run_id=eq.${runId}`
          + '&select=task_id,run_id,status,report_path,failure_receipt_path&limit=2');
        if (!Array.isArray(runs) || runs.length !== 1 || runs[0]?.task_id !== taskId || runs[0]?.run_id !== runId)
          fail('REPORT_UNAVAILABLE', '失败回执不存在或无权读取');
        const run = runs[0];
        if (run.status !== 'failed' || run.report_path !== null || typeof run.failure_receipt_path !== 'string')
          fail('REPORT_NOT_GENERATED', '该失败运行尚无可读取的私有回执');
        const prefix = `${taskId}/${runId}/`;
        const relativePath = run.failure_receipt_path.startsWith(prefix)
          ? run.failure_receipt_path.slice(prefix.length) : '';
        if (run.failure_receipt_path.length !== prefix.length + 61
          || !/^failure-[a-f0-9]{48}\.json$/.test(relativePath))
          fail('REPORT_PATH_INVALID', '失败回执对象绑定无效');
        const content = await readBound(`/storage/v1/object/authenticated/reports/${run.failure_receipt_path}`, false);
        const receiptKeys = ['schema_version', 'task_id', 'run_id', 'recovery_reason', 'failure_reason', 'provider_receipts'];
        if (!exactKeys(content, receiptKeys) || content.schema_version !== 1
          || content.task_id !== taskId || content.run_id !== runId
          || !['ordinary_failure', 'lease_expired'].includes(content.recovery_reason)
          || !Array.isArray(content.provider_receipts) || content.provider_receipts.length < 1
          || content.provider_receipts.length > 100)
          fail('RESPONSE_INVALID', '失败回执结构或运行绑定无效');
        const failure = content.failure_reason;
        if (failure !== null && (!exactKeys(failure, ['code', 'stage', 'retryable'])
          || typeof failure.code !== 'string' || !/^[A-Z][A-Z0-9_]{1,63}$/.test(failure.code)
          || !['task', 'worker', 'ingestion', 'reconciliation', 'config', 'competitors', 'provider', 'report', 'storage'].includes(failure.stage)
          || failure.retryable !== false))
          fail('RESPONSE_INVALID', '失败回执原因字段无效');
        const providerNames = ['xiyou', 'sorftime', 'visual'];
        const providerKeys = ['provider', 'status', 'attempt', 'tool', 'request_sha256', 'response_sha256',
          'response_status', 'reserved_calls', 'actual_calls', 'reserved_credits', 'actual_credits',
          'reserved_tokens', 'actual_tokens'];
        const validDigest = value => value === null || (typeof value === 'string' && /^[a-f0-9]{64}$/.test(value));
        const validCount = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
        if (!content.provider_receipts.every(item => exactKeys(item, providerKeys)
          && providerNames.includes(item.provider) && item.status === 'uncertain'
          && Number.isSafeInteger(item.attempt) && item.attempt > 0
          && typeof item.tool === 'string' && /^[a-z0-9_]{1,100}$/.test(item.tool)
          && validDigest(item.request_sha256) && validDigest(item.response_sha256)
          && (item.response_status === null || (Number.isInteger(item.response_status)
            && item.response_status >= 100 && item.response_status <= 599))
          && ['reserved_calls', 'actual_calls', 'reserved_credits', 'actual_credits',
            'reserved_tokens', 'actual_tokens'].every(key => validCount(item[key]))))
          fail('RESPONSE_INVALID', '失败回执调用记录字段无效');
        check();
        return { task_id: taskId, run_id: runId, failure_receipt_path: run.failure_receipt_path, content };
      },
      async readModule(taskId, runId, name) {
        const operationSession = requireSession();
        const stamp = generation;
        const checkOperationSession = () => {
          if (stamp !== generation) fail('SESSION_CHANGED', '会话已改变，报告已丢弃');
          if (requireSession() !== operationSession)
            fail('SESSION_CHANGED', '会话已改变，报告已丢弃');
        };
        [taskId, runId] = reportIds(taskId, runId);
        if (!REPORT_ARTIFACTS.includes(name))
          fail('INPUT_INVALID', '未知报告模块');
        // 004 authorizes only task_runs.report_path: modules must come from that same bundle.
        const report = await liveReports.read(taskId, runId, checkOperationSession);
        checkOperationSession();
        const legacyAdOnlyWithoutManifest = report.content.report_scope === 'ad_only'
          && !report.content.evidence_manifest;
        if ((report.content.report_scope && report.content.report_scope !== 'ad_only') || report.content.evidence_manifest)
          await validateEvidenceManifest(report.content, taskId, runId, name, checkOperationSession);
        checkOperationSession();
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
        if (state?.status === 'failed')
          fail('REPORT_MODULE_FAILED', '该模块生成失败。', 0, { module_state: state });
        if (state?.status === 'not_generated')
          fail('REPORT_NOT_GENERATED', '该模块尚未生成可读取的真实报告。', 0, { module_state: state });
        if (legacyAdOnlyWithoutManifest)
          fail('REPORT_INVALID', '报告模块缺少可验证的证据清单');
        const module = { ...content };
        Object.defineProperty(module, '_module_state', {
          value: state?.status ? state : { status: 'partial', reason: 'legacy_bundle_without_module_states' },
          enumerable: false,
        });
        checkOperationSession();
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
  const api = { createClient, validateConfig, ClientError, REPORT_ARTIFACTS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KWCCClient = api;
})(globalThis);
