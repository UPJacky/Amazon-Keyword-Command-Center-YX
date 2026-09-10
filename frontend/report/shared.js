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
    document.querySelector('#module-metrics')?.replaceChildren(...values.map(([label, value]) => metric(label, value)));
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
    const state = data?._module_state;
    if (state?.status === 'ready') return '数据完整';
    if (state?.status === 'partial') return `部分数据（${text(state.reason, '原因未说明')}）`;
    return '状态未确认';
  }
  const ready = (async () => {
    if (!await globalThis.KWCC?.ready) return false;
    if (!['demo', 'live'].includes(globalThis.KWCC.mode)) {
      document.querySelector('main')?.replaceChildren(el('p', '报告访问已禁止：不显示演示数据。请返回工具页。', 'module-empty'));
      return false;
    }
    const sidebar = document.querySelector('.report-sidebar');
    if (sidebar) {
      const nav = el('nav'); nav.setAttribute('aria-label', '报告模块');
      pages.forEach(([key, path, title], index) => {
        const link = el('a');
        const url = new URL(path, scriptURL);
        // Preserve the exact run across modules; never forward credentials or object URLs.
        for (const key of ['task', 'run']) {
          const value = new URL(location.href).searchParams.get(key);
          if (value) url.searchParams.set(key, value);
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
      const current = new URL(location.href);
      for (const key of ['task', 'run']) if (current.searchParams.get(key)) url.searchParams.set(key, current.searchParams.get(key));
      link.href = url.href;
    });
    return true;
  })();
  async function load(name) {
    if (!await ready) throw new Error('report access denied');
    if (!['rank-benchmark.json', 'negative-keywords.json', 'competitors.json', 'category-features.json', 'listing-diagnostics.json', 'optimization-plan.json'].includes(name)) throw new Error('unknown artifact');
    if (globalThis.KWCC.mode === 'live') {
      const params = new URL(location.href).searchParams;
      return globalThis.KWCC.reports.readModule(params.get('task'), params.get('run'), name);
    }
    const localSource = scriptURL.pathname.includes('/frontend/');
    const response = await fetch(new URL(`${localSource ? '../../' : '../'}data/golden/market-demo-modules/${name}`, scriptURL), { credentials: 'same-origin' });
    if (!response.ok) throw new Error('artifact unavailable');
    return response.json();
  }
  globalThis.ReportUI = Object.freeze({ ready, load, text, number, percent, money, el, metric, table, setMetrics, showError, statusPrefix });
})();
