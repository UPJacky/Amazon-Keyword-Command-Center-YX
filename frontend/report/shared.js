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
  function showError() {
    document.querySelector('#module-body')?.replaceChildren(el('p', '报告数据暂时无法读取。请刷新重试；持续失败请检查报告是否已生成。', 'module-empty'));
    const status = document.querySelector('#module-status');
    if (status) { status.textContent = '加载失败 · 未生成分析结论'; status.setAttribute('role', 'alert'); }
  }
  const ready = (async () => {
    if (!await globalThis.KWCC?.ready) return false;
    if (globalThis.KWCC.mode !== 'demo') {
      document.querySelector('main')?.replaceChildren(el('p', '私有报告读取尚未接入：不显示演示数据。请返回工具页。', 'module-empty'));
      return false;
    }
    const sidebar = document.querySelector('.report-sidebar');
    if (sidebar) {
      const nav = el('nav'); nav.setAttribute('aria-label', '报告模块');
      pages.forEach(([key, path, title], index) => {
        const link = el('a');
        const url = new URL(path, scriptURL);
        // Retain only the task selector, not arbitrary query params or credentials.
        const task = new URL(location.href).searchParams.get('task');
        if (task) url.searchParams.set('task', task);
        link.href = url.href;
        link.append(el('span', String(index + 1).padStart(2, '0')), el('span', title));
        if ((document.body.dataset.module || 'master') === key) { link.className = 'active'; link.setAttribute('aria-current', 'page'); }
        nav.append(link);
      });
      sidebar.replaceChildren(el('strong', '关键词作战台', 'sidebar-title'), el('p', '报告分析 · 六个独立模块', 'muted'), nav);
    }
    return true;
  })();
  async function load(name) {
    if (!await ready) throw new Error('report access denied');
    if (!['rank-benchmark.json', 'negative-keywords.json', 'competitors.json', 'listing-diagnostics.json', 'optimization-plan.json'].includes(name)) throw new Error('unknown artifact');
    const localSource = scriptURL.pathname.includes('/frontend/');
    const response = await fetch(new URL(`${localSource ? '../../' : '../'}data/golden/market-demo-modules/${name}`, scriptURL), { credentials: 'same-origin' });
    if (!response.ok) throw new Error('artifact unavailable');
    return response.json();
  }
  globalThis.ReportUI = Object.freeze({ ready, load, text, number, percent, money, el, metric, table, setMetrics, showError });
})();
