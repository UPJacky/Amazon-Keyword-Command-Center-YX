/* Shared presentation and access gate; business rendering stays in each module. */
(function () {
  'use strict';
  const scriptURL = new URL(document.currentScript.src);
  const pages = [
    ['master', 'index.html', '关键词作战总表'], ['rank', 'rank.html', '自然位标杆'],
    ['negative', 'negative.html', '否定词清单'], ['competitors', 'competitors.html', '竞对对比'],
    ['listing', 'listing.html', '图片与卖点诊断'], ['optimization', 'optimization.html', '广告诊断与优化'],
  ];
  const missing = value => value === null || value === undefined || value === '';
  const text = (value, fallback = '—') => missing(value) ? fallback : String(value);
  const numeric = value => !missing(value) && typeof value !== 'boolean' && Number.isFinite(Number(value));
  const number = (value, digits = 0) => numeric(value) ? Number(value).toLocaleString('en-US', { maximumFractionDigits: digits }) : '—';
  const percent = value => numeric(value) ? `${(Number(value) * 100).toFixed(1)}%` : '—';
  function money(value, currency = 'USD') {
    if (!numeric(value) || !/^[A-Z]{3}$/.test(currency || '')) return '—';
    try { return Number(value).toLocaleString('en-US', { style: 'currency', currency }); } catch { return '—'; }
  }
  function el(tag, value, className) {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = text(value);
    if (className) node.className = className;
    return node;
  }
  function metric(label, value) {
    const card = el('article', undefined, 'metric-card');
    card.append(el('span', label), el('strong', value));
    return card;
  }
  function setMetrics(values) {
    if (isInvalidated()) return;
    document.querySelector('#module-metrics')?.replaceChildren(...values.map(([label, value]) => metric(label, value)));
  }
  const lifecycle = globalThis.KWCC?.reportLifecycle;
  const DEFAULT_INVALIDATION_MESSAGE = '会话已结束或身份已改变，报告内容和导出已清除。请重新验证身份。';
  let invalidated = lifecycle?.invalidated === true;
  let loadRevision = Number.isInteger(lifecycle?.revision) ? lifecycle.revision : 0;
  let boundIdentityKey = null;
  const pendingLoads = new Set();
  const invalidationCallbacks = new Set();
  const exportObjectURLs = new Set();
  function isInvalidated() {
    if (lifecycle?.invalidated === true && !invalidated) invalidate(lifecycle.reason || DEFAULT_INVALIDATION_MESSAGE);
    return invalidated;
  }
  function identityKey(identity) {
    return identity ? JSON.stringify([identity.taskId, identity.runId]) : null;
  }
  function routeIdentityKey() {
    return identityKey(uniqueBoundIdentity(new URL(location.href).searchParams));
  }
  function canceledLoad() {
    const error = new Error('报告读取已取消：会话或 task/run 身份已改变。');
    error.name = 'AbortError';
    error.code = 'SESSION_CHANGED';
    return error;
  }
  function clearView(reason) {
    const message = typeof reason === 'string' && reason.trim() ? reason : DEFAULT_INVALIDATION_MESSAGE;
    document.querySelector('#module-metrics')?.replaceChildren();
    const status = document.querySelector('#module-status');
    if (status) {
      status.textContent = '会话已结束 · 报告数据和导出已清除';
      status.setAttribute('role', 'alert');
    }

    // Blank report state before detaching the page. Module scripts keep local
    // references to these nodes, so removing the old report tree prevents a
    // late continuation from making sensitive output visible again.
    const main = document.querySelector('main');
    if (!main) return;
    const queryAll = selector => typeof main.querySelectorAll === 'function' ? main.querySelectorAll(selector) : [];
    const rows = document.querySelector('#report-rows');
    rows?.replaceChildren();
    for (const selector of [
      '#keyword-count', '#report-filter-status', '#report-period-currency',
      '#report-rule-version', '#report-config-version', '#report-schema-version',
      '#report-currency', '#report-input-file', '#report-input-sha256',
      '#report-provider-version', '#report-missing-fields', '#report-ai-status',
      '#report-reconciliation', '#report-strategy-summary',
    ]) {
      const node = document.querySelector(selector);
      if (node) node.textContent = '';
    }
    const exportButton = document.querySelector('#export-report');
    if (exportButton) exportButton.disabled = true;
    for (const input of queryAll('input, textarea, select')) {
      if (input.type === 'checkbox' || input.type === 'radio') input.checked = false;
      if ('value' in input) input.value = '';
      input.disabled = true;
    }
    for (const button of queryAll('button')) button.disabled = true;
    for (const image of queryAll('img')) {
      image.removeAttribute?.('src');
      image.removeAttribute?.('srcset');
    }
    for (const link of queryAll('a')) {
      const href = link.getAttribute?.('href') || link.href || '';
      if (typeof href === 'string' && href.startsWith('blob:')) {
        try { URL.revokeObjectURL(href); } catch (_) { /* unsupported URL implementation */ }
      }
      link.removeAttribute?.('href');
    }
    queryAll('[data-failure-receipt]').forEach(node => node.remove?.());
    document.querySelector('#module-body')?.replaceChildren();
    const notice = el('p', message, 'module-empty');
    notice.setAttribute('role', 'alert');
    main.replaceChildren(notice);
  }
  function operationToken() {
    const operation = Object.freeze({
      revision: loadRevision,
      identityKey: boundIdentityKey,
      sessionRevision: Number.isInteger(lifecycle?.revision) ? lifecycle.revision : null,
    });
    assertOperation(operation);
    return operation;
  }
  function assertOperation(token) {
    if (!token || typeof token !== 'object' || !Number.isInteger(token.revision)) throw canceledLoad();
    assertCurrent(token.revision, token.identityKey);
    if (token.sessionRevision !== (Number.isInteger(lifecycle?.revision) ? lifecycle.revision : null)) {
      invalidate(lifecycle?.reason || DEFAULT_INVALIDATION_MESSAGE);
      throw canceledLoad();
    }
  }
  function operationIsActive(token) {
    try { assertOperation(token); return true; } catch (_) { return false; }
  }
  function onInvalidate(callback) {
    if (typeof callback !== 'function') throw new TypeError('invalidation callback must be a function');
    if (isInvalidated()) { callback(); return () => {}; }
    invalidationCallbacks.add(callback);
    return () => invalidationCallbacks.delete(callback);
  }
  function trackExportObjectURL(url, token = operationToken()) {
    assertOperation(token);
    if (typeof url !== 'string' || !url.startsWith('blob:')) throw new TypeError('export URL must be a blob URL');
    const record = { url, active: true };
    const release = () => {
      if (!record.active) return;
      record.active = false;
      exportObjectURLs.delete(record);
      try { URL.revokeObjectURL(record.url); } catch (_) { /* unsupported URL implementation */ }
    };
    record.release = release;
    exportObjectURLs.add(record);
    return release;
  }
  function invalidate(reason = DEFAULT_INVALIDATION_MESSAGE) {
    if (!invalidated) {
      invalidated = true;
      loadRevision++;
      const error = canceledLoad();
      for (const cancel of pendingLoads) cancel(error);
      pendingLoads.clear();
      for (const callback of invalidationCallbacks) {
        try { callback(); } catch (_) { /* teardown must continue for every registered owner */ }
      }
      invalidationCallbacks.clear();
      for (const record of [...exportObjectURLs]) record.release();
    }
    if (lifecycle) {
      lifecycle.invalidated = true;
      lifecycle.reason = reason;
      if (!Number.isInteger(lifecycle.revision) || lifecycle.revision < loadRevision)
        lifecycle.revision = loadRevision;
    }
    clearView(reason);
    return true;
  }
  function assertCurrent(revision, requestedIdentityKey) {
    if (isInvalidated() || revision !== loadRevision) throw canceledLoad();
    if (requestedIdentityKey !== routeIdentityKey()) {
      invalidate('报告 task/run 身份已改变，旧报告内容和导出已清除。请重新打开报告。');
      throw canceledLoad();
    }
  }
  async function withCancellation(operation, revision, requestedIdentityKey) {
    let cancel;
    const canceled = new Promise((_, reject) => { cancel = reject; });
    pendingLoads.add(cancel);
    try {
      const value = await Promise.race([operation, canceled]);
      assertCurrent(revision, requestedIdentityKey);
      return value;
    } finally {
      pendingLoads.delete(cancel);
    }
  }
  function table(headers, rows) {
    const wrap = el('div', undefined, 'table-scroll');
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', '数据表，可左右滚动');
    const node = el('table', undefined, 'data-table module-table');
    const head = el('thead'), headRow = el('tr'), body = el('tbody');
    headers.forEach(label => { const th = el('th', label); th.scope = 'col'; headRow.append(th); });
    head.append(headRow);
    rows.forEach(values => {
      const tr = el('tr');
      values.forEach(value => { const td = el('td'); value instanceof Node ? td.append(value) : td.textContent = text(value); tr.append(td); });
      body.append(tr);
    });
    if (!rows.length) {
      const row = el('tr'), td = el('td', '当前条件下没有记录。', 'module-empty');
      td.colSpan = headers.length; row.append(td); body.append(row);
    }
    node.append(head, body); wrap.append(node); return wrap;
  }
  function showError(error) {
    if (isInvalidated()) return;
    const unavailable = error?.code === 'REPORT_NOT_GENERATED';
    const failed = error?.code === 'REPORT_MODULE_FAILED';
    const reason = error?.details?.module_state?.reason;
    const safeReason = typeof reason === 'string' && /^[a-z0-9_]{1,80}$/i.test(reason) ? reason : null;
    setMetrics([]);
    const message = unavailable ? `该模块尚未生成可读取的真实报告。${safeReason ? ` 原因：${safeReason}` : ''}`
      : failed ? `该模块生成失败。${safeReason ? ` 原因：${safeReason}` : ''}`
      : '报告数据暂时无法读取。请确认任务、运行记录和登录权限。';
    document.querySelector('#module-body')?.replaceChildren(el('p', message, 'module-empty'));
    const status = document.querySelector('#module-status');
    if (status) { status.textContent = unavailable ? '真实报告尚未生成 · 无可读取数据' : failed ? '生成失败 · 查看失败原因' : '加载失败 · 未生成分析结论'; status.setAttribute('role', 'alert'); }
  }
  function statusPrefix(data) {
    // The live client envelope is authoritative; demo artifacts may only carry
    // their persisted root module_status.
    const hasLiveState = data && Object.prototype.hasOwnProperty.call(data, '_module_state');
    const state = hasLiveState ? data._module_state : data?.module_status;
    if (state?.status === 'ready') return '数据完整';
    if (state?.status === 'partial') return `部分数据（${text(state.reason, '原因未说明')}）`;
    if (state?.status === 'failed') return `生成失败（${text(state.reason, '原因未说明')}）`;
    if (state?.status === 'not_generated') return `尚未生成（${text(state.reason, '原因未说明')}）`;
    return '状态未确认';
  }
  function uniqueBoundIdentity(params) {
    const taskIds = params.getAll('task');
    const runIds = params.getAll('run');
    if (taskIds.length !== 1 || runIds.length !== 1 || !taskIds[0] || !runIds[0]) return null;
    return { taskId: taskIds[0], runId: runIds[0] };
  }
  const ready = (async () => {
    if (!await globalThis.KWCC?.ready) return false;
    if (isInvalidated()) { clearView(lifecycle?.reason); return false; }
    if (!['demo', 'live'].includes(globalThis.KWCC.mode)) {
      document.querySelector('main')?.replaceChildren(el('p', '报告访问已禁止：不显示演示数据。请返回工具页。', 'module-empty'));
      return false;
    }
    const identity = uniqueBoundIdentity(new URL(location.href).searchParams);
    boundIdentityKey = identityKey(identity);
    const sidebar = document.querySelector('.report-sidebar');
    if (sidebar) {
      const nav = el('nav'); nav.setAttribute('aria-label', '报告模块');
      pages.forEach(([key, path, title], index) => {
        const link = el('a');
        const url = new URL(path, scriptURL);
        // Preserve the exact run across modules; never forward credentials or object URLs.
        if (identity) {
          url.searchParams.set('task', identity.taskId);
          url.searchParams.set('run', identity.runId);
        }
        link.href = url.href;
        link.append(el('span', String(index + 1).padStart(2, '0')), el('span', title));
        if ((document.body.dataset.module || 'master') === key) { link.className = 'active'; link.setAttribute('aria-current', 'page'); }
        nav.append(link);
      });
      sidebar.replaceChildren(el('strong', '关键词作战台', 'sidebar-title'), el('p', '报告分析 · 六个独立模块', 'muted'), nav);
    }
    const reportLinks = typeof document.querySelectorAll === 'function' ? document.querySelectorAll('.topbar a[href="index.html"]') : [];
    reportLinks.forEach(link => {
      const url = new URL(link.getAttribute('href'), scriptURL);
      if (identity) {
        url.searchParams.set('task', identity.taskId);
        url.searchParams.set('run', identity.runId);
      }
      link.href = url.href;
    });
    return true;
  })();
  if (invalidated) clearView(lifecycle?.reason);
  if (typeof globalThis.addEventListener === 'function') {
    globalThis.addEventListener('popstate', () => {
      if (boundIdentityKey !== routeIdentityKey())
        invalidate('报告 task/run 身份已改变，旧报告内容和导出已清除。请重新打开报告。');
    });
  }
  async function load(name) {
    if (!await ready) throw new Error('report access denied');
    if (isInvalidated()) throw canceledLoad();
    if (!['rank-benchmark.json', 'negative-keywords.json', 'competitors.json', 'category-features.json', 'buyer-checklist.json', 'text-evidence.json', 'listing-diagnostics.json', 'optimization-plan.json'].includes(name)) throw new Error('unknown artifact');
    const revision = loadRevision;
    if (globalThis.KWCC.mode === 'live') {
      const identity = uniqueBoundIdentity(new URL(location.href).searchParams);
      if (!identity) {
        const error = new Error('report identity is missing or ambiguous');
        error.code = 'INPUT_INVALID';
        throw error;
      }
      const requestedIdentityKey = identityKey(identity);
      assertCurrent(revision, requestedIdentityKey);
      const operation = Promise.resolve().then(() => {
        assertCurrent(revision, requestedIdentityKey);
        return globalThis.KWCC.reports.readModule(identity.taskId, identity.runId, name);
      });
      return withCancellation(operation, revision, requestedIdentityKey);
    }
    const localSource = scriptURL.pathname.includes('/frontend/');
    const operation = Promise.resolve().then(async () => {
      assertCurrent(revision, boundIdentityKey);
      const response = await fetch(new URL(`${localSource ? '../../' : '../'}data/golden/market-demo-modules/${name}`, scriptURL), { credentials: 'same-origin' });
      if (!response.ok) throw new Error('artifact unavailable');
      return response.json();
    });
    return withCancellation(operation, revision, boundIdentityKey);
  }
  globalThis.ReportUI = Object.freeze({ ready, load, text, number, percent, money, el, metric, table, setMetrics, showError, statusPrefix,
    invalidate, operationToken, assertOperation, operationIsActive, onInvalidate, trackExportObjectURL });
})();
