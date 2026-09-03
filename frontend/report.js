const reportScriptURL = new URL(document.currentScript.src);
(async function () {
  if (!await globalThis.KWCC?.ready) return;
  if (globalThis.KWCC.mode === 'live') {
    const main = document.querySelector('main');
    main.replaceChildren();
    const notice = document.createElement('p');
    notice.textContent = '私有报告读取尚未接入：不显示或导出演示报告。请返回任务页。';
    main.append(notice);
    return;
  }
  const dataPath = name => new URL(`${reportScriptURL.pathname.includes('/frontend/') ? '../' : './'}data/golden/${name}`, reportScriptURL).href;
  const reportUrl = dataPath('market-demo-report/master-table.json');
  const tableBody = document.querySelector('#report-rows');
  if (!tableBody) return;

  const state = { report: null, filter: 'all', query: '', currency: null };
  const labels = { add: '加投', defend: '防守', keep: '保持', cautious: '谨慎', optimize: '优化', stop_loss: '止损/暂停', data_missing: '数据待补' };
  const stages = { new: '新品期', growth: '上升期', stable: '稳定期', clearance: '清货期', seasonal_restart: '季节性重启' };
  const headers = ['搜索词', '角色 / 阶段', '结论', '展示', '点击', 'CTR', 'CPC', '花费', '订单', '销售额', 'CVR', 'ACOS', 'ROAS', '证据', '搜索量', '难度', '建议竞价', '自然位', '广告位', '下一步', '缺失字段'];
  const filterGroups = {
    add: ['scale_up'],
    defend: ['defend_rank'],
    keep: ['hold_steady'],
    optimize: ['optimize_listing', 'optimize_bid', 'optimize_structure'],
    cautious: ['cautious_test', 'continue_observation'],
    data_missing: ['data_missing'],
    stop_loss: ['stop_loss', 'reduce_or_pause'],
  };

  const isMissing = value => value === null || value === undefined || value === '';
  const normaliseMissingFields = value => Array.isArray(value) ? [...new Set(value.filter(item => typeof item === 'string' && item.trim()).map(item => item.trim()))].sort() : [];
  const missingFields = value => normaliseMissingFields(value).join(' · ') || '—';
  const text = (value, fallback = '—') => isMissing(value) ? fallback : String(value);
  const number = (value, digits = 0) => isMissing(value) || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-US', { maximumFractionDigits: digits });
  const money = value => isMissing(value) || !state.currency || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-US', { style: 'currency', currency: state.currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const percent = value => isMissing(value) || !Number.isFinite(Number(value)) ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
  const conclusion = row => row.ui_conclusion || ({ scale_up: 'add', defend_rank: 'defend', hold_steady: 'keep', cautious_test: 'cautious', continue_observation: 'cautious', optimize_listing: 'optimize', optimize_bid: 'optimize', optimize_structure: 'optimize', stop_loss: 'stop_loss', reduce_or_pause: 'stop_loss', data_missing: 'data_missing' }[row.action_group] || text(row.action_group, 'unknown'));

  function matches(row) {
    return (state.filter === 'all' || (filterGroups[state.filter] || []).includes(row.action_group)) && String(row.keyword || '').toLowerCase().includes(state.query);
  }

  function cell(value, className) {
    const td = document.createElement('td');
    if (className) td.className = className;
    td.textContent = text(value);
    return td;
  }

  function render() {
    const rows = state.report.rows.filter(matches);
    tableBody.replaceChildren();
    rows.forEach(row => {
      const tr = document.createElement('tr');
      const keyword = document.createElement('td');
      const strong = document.createElement('strong');
      strong.textContent = text(row.keyword);
      const small = document.createElement('small');
      small.textContent = row.rule_hits?.join(' · ') || '规则原因待补';
      keyword.append(strong, small);
      tr.append(keyword);
      tr.append(cell(`${text(row.keyword_role)} · ${stages[row.product_stage] || text(row.product_stage)}`));
      const result = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = `conclusion ${['green','blue','yellow','orange','red','gray'].includes(row.ui_color) ? row.ui_color : 'gray'}`;
      badge.textContent = labels[conclusion(row)] || '待确认';
      result.appendChild(badge);
    tr.append(result, cell(number(row.impressions)), cell(number(row.clicks)), cell(percent(row.ctr)), cell(money(row.cpc)), cell(money(row.spend)), cell(number(row.orders)), cell(money(row.sales)), cell(percent(row.cvr)), cell(percent(row.acos)), cell(isMissing(row.roas) || !Number.isFinite(Number(row.roas)) ? '—' : Number(row.roas).toFixed(2)), cell(row.evidence_level), cell(number(row.market_search_volume)), cell(percent(row.competitive_difficulty)), cell(money(row.suggested_bid)), cell(number(row.organic_rank)), cell(number(row.ad_rank)), cell(row.next_action_text), cell(missingFields(row.missing_fields)));
      tableBody.appendChild(tr);
    });
    document.querySelector('#keyword-count').textContent = `${number(rows.length)} 个搜索词`;
    document.querySelector('#report-filter-status').textContent = state.filter === 'all' ? '默认按结论组 → 搜索量 → 花费 → 关键词排序' : `当前筛选：${state.filter} · ${number(rows.length)} 个搜索词`;
    document.querySelectorAll('[data-action-filter]').forEach(button => { button.classList.toggle('active', button.dataset.actionFilter === state.filter); button.setAttribute('aria-pressed', String(button.dataset.actionFilter === state.filter)); });
    if (!rows.length) { const tr = document.createElement('tr'); const td = cell('没有符合条件的搜索词，请调整筛选或搜索。', 'table-empty'); td.colSpan = 21; tr.append(td); tableBody.append(tr); }
  }

  const headerRow = document.querySelector('.table-panel thead tr');
  if (headerRow) {
    headerRow.replaceChildren(...headers.map(label => {
      const th = document.createElement('th');
      th.textContent = label;
      return th;
    }));
  }

  function renderPhase4Modules(rank, negative) {
    const panel = document.createElement('section');
    panel.className = 'panel module-summary-grid';
    const rankCard = document.createElement('article');
    rankCard.className = 'notice notice--soft';
    rankCard.innerHTML = '<strong>Module 02 · 自然位标杆</strong>';
    const rankText = document.createElement('span');
    const knownRanks = (rank.rows || []).filter(row => row.my_organic_rank !== null && row.my_organic_rank !== undefined).length;
    rankText.textContent = `${rank.rows?.length || 0} 个关键词 · ${knownRanks} 个已上榜 · 未上榜保持 —`;
    rankCard.appendChild(rankText);
    const negativeCard = document.createElement('article');
    negativeCard.className = 'notice notice--cream';
    negativeCard.innerHTML = '<strong>Module 03 · 否定词候选</strong>';
    const negativeText = document.createElement('span');
    const direct = (negative.exact_negative || []).length;
    const phrase = (negative.phrase_negative || []).length;
    const cautious = (negative.cautious || []).length;
    negativeText.textContent = `精准 ${direct} · 词组 ${phrase} · 慎否 ${cautious} · 写回 Amazon：否`;
    negativeCard.appendChild(negativeText);
    panel.append(rankCard, negativeCard);
    document.querySelector('.table-panel')?.after(panel);
  }

  function showError() {
    tableBody.replaceChildren();
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 21;
    td.className = 'table-empty';
    td.textContent = '报告暂时无法读取，请刷新重试。持续失败请检查报告文件是否已生成。';
    tr.appendChild(td);
    tableBody.appendChild(tr);
    document.querySelector('#keyword-count').textContent = '报告加载失败';
    document.querySelector('#report-filter-status').textContent = '未生成分析结论';
  }

  document.querySelectorAll('[data-action-filter]').forEach(button => button.addEventListener('click', () => {
    state.filter = button.dataset.actionFilter;
    if (state.report) render();
  }));
  document.querySelector('#export-report')?.addEventListener('click', () => {
    if (!state.report) return;
    const blob = new Blob([JSON.stringify({ ...state.report, rows: state.report.rows.filter(matches), export_scope: { filter: state.filter, query: state.query } }, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'keyword-report.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 0);
  });
  document.querySelector('#keyword-search')?.addEventListener('input', event => { state.query = event.target.value.trim().toLowerCase(); if (state.report) render(); });
  fetch(reportUrl).then(response => {
    if (!response.ok) throw new Error(`report HTTP ${response.status}`);
    return response.json();
  }).then(report => {
    if (!report || !Array.isArray(report.rows) || !report.rows.every(row => row && typeof row === 'object')) throw new Error('invalid report');
    state.report = report;
    document.querySelector('#report-rule-version').textContent = text(report.rule_version);
    document.querySelector('#report-config-version').textContent = text(report.config_version);
    document.querySelector('#report-schema-version').textContent = text(report.schema_version);
    document.querySelector('#report-currency').textContent = text(report.currency_code);
    document.querySelector('#report-period-currency').textContent = text(report.currency_code);
    document.querySelector('#report-input-file').textContent = text(report.input_file);
    document.querySelector('#report-input-sha256').textContent = text(report.input_sha256);
    document.querySelector('#report-provider-version').textContent = text(report.provider_snapshot_version);
    document.querySelector('#report-missing-fields').textContent = missingFields(report.missing_fields);
    state.currency = /^[A-Z]{3}$/.test(report.currency_code || '') ? report.currency_code : null;
    document.querySelector('#report-reconciliation').textContent = report.reconciliation?.passed === true ? '通过 · 差值 0' : '失败';
    const strategySummary = document.querySelector('#report-strategy-summary');
    if (strategySummary) strategySummary.textContent = `当前策略：${text(report.config_version)} · 规则 ${text(report.rule_version)} · 对账${report.reconciliation?.passed === true ? '通过，差值 0' : '未通过，请勿执行建议'}`;
    document.querySelector('#export-report').disabled = false;
    const sum = key => report.rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);
    globalThis.ReportUI?.setMetrics([['搜索词', number(report.rows.length)], ['广告总花费', money(sum('spend'))], ['广告订单', number(sum('orders'))], ['整体 CTR', sum('impressions') ? percent(sum('clicks') / sum('impressions')) : '—']]);
    render();
  }).catch(showError);
  if (!globalThis.ReportUI) Promise.all([
    fetch(dataPath('market-demo-modules/rank-benchmark.json')).then(response => response.json()),
    fetch(dataPath('market-demo-modules/negative-keywords.json')).then(response => response.json()),
  ]).then(([rank, negative]) => renderPhase4Modules(rank, negative)).catch(() => {});
})();
