const reportScriptURL = new URL(document.currentScript.src);
(async function () {
  'use strict';
  if (!await globalThis.KWCC?.ready) return;
  if (!['demo', 'live'].includes(globalThis.KWCC.mode)) return;
  const reportUI = globalThis.ReportUI;
  if (reportUI?.ready && await reportUI.ready !== true) return;
  const live = globalThis.KWCC.mode === 'live';
  const dataPath = name => new URL(`${reportScriptURL.pathname.includes('/frontend/') ? '../' : './'}data/golden/${name}`, reportScriptURL).href;
  const reportUrl = dataPath('market-demo-report/master-table.json');
  const tableBody = document.querySelector('#report-rows');
  if (!tableBody) return;

  let lifecycleToken = null;
  if (typeof reportUI?.operationToken === 'function') {
    try { lifecycleToken = reportUI.operationToken(); } catch (_) { return; }
  }
  let lifecycleInvalidated = false;
  const canceledOperation = () => {
    const error = new Error('report operation was invalidated');
    error.name = 'AbortError';
    error.code = 'SESSION_CHANGED';
    return error;
  };
  function assertLifecycle(token = lifecycleToken) {
    if (lifecycleInvalidated) throw canceledOperation();
    if (token && typeof reportUI?.assertOperation === 'function') return reportUI.assertOperation(token);
    if (token && typeof reportUI?.operationIsActive === 'function' && !reportUI.operationIsActive(token)) throw canceledOperation();
  }
  function isLifecycleActive(token = lifecycleToken) {
    if (lifecycleInvalidated) return false;
    try { assertLifecycle(token); return true; } catch (_) { return false; }
  }
  const state = { report: null, filter: 'all', query: '', currency: null };
  const exportButton = document.querySelector('#export-report');
  if (exportButton) exportButton.disabled = true;
  let reportSession = null;
  let report = null;
  let failureReceipt = null;
  let liveSelection = null;
  const exportRecords = new Set();
  function releaseExport(record) {
    if (!record) return;
    if (record.timer !== null) {
      if (typeof clearTimeout === 'function') clearTimeout(record.timer);
      record.timer = null;
    }
    record.payload = null;
    record.link?.remove?.();
    record.link = null;
    const release = record.release;
    const url = record.url;
    record.release = null;
    record.url = null;
    exportRecords.delete(record);
    if (release) release();
    else if (url) { try { URL.revokeObjectURL(url); } catch (_) { /* unsupported URL implementation */ } }
  }
  function clearPrivateState() {
    report = null;
    failureReceipt = null;
    state.report = null;
    state.filter = 'all';
    state.query = '';
    state.currency = null;
    reportSession = null;
    liveSelection = null;
    if (exportButton) exportButton.disabled = true;
    const search = document.querySelector('#keyword-search');
    if (search) search.value = '';
    document.querySelectorAll('[data-action-filter]').forEach(button => {
      button.classList.toggle('active', false);
      button.setAttribute('aria-pressed', 'false');
    });
    for (const record of [...exportRecords]) releaseExport(record);
  }
  if (typeof reportUI?.onInvalidate === 'function') reportUI.onInvalidate(() => {
    lifecycleInvalidated = true;
    clearPrivateState();
  });
  const checkReportSession = () => {
    assertLifecycle();
    if (live && globalThis.KWCC.auth.checkSession() !== reportSession) throw new Error('report session changed');
    assertLifecycle();
  };
  if (live) globalThis.KWCC.auth.subscribe(value => {
    if (value !== 'authenticated') showError();
  });
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

  // The master table is judged by its own evidence, never by the full-report
  // flag: a usable keyword table can coexist with missing images, competitors
  // or market data.  An absent or unrecognised state renders nothing, so demo
  // fixtures and legacy bundles keep their existing summary unchanged.
  const MASTER_STATUS_LABELS = {
    ready: '核心总表可用', partial: '核心总表未就绪',
    failed: '核心总表生成失败', not_generated: '核心总表未生成',
  };
  const MASTER_REASON_LABELS = {
    master_not_generated: '总表尚未生成',
    master_schema_unsupported: '总表 schema 不受支持',
    master_rows_missing: '总表行缺失',
    reconciliation_failed: '总表对账未通过',
    master_identity_mismatch: '总表身份不匹配',
    master_versions_missing: '规则或配置版本缺失',
  };
  function masterState(report) {
    for (const candidate of [report?.module_status, report?.module_states?.['master-table.json']]) {
      if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) continue;
      if (typeof MASTER_STATUS_LABELS[candidate.status] !== 'string') continue;
      return {
        status: candidate.status,
        reason: typeof candidate.reason === 'string' ? candidate.reason : '',
      };
    }
    return null;
  }
  function masterReadinessPrefix(report) {
    const master = masterState(report);
    if (!master) return '';
    const head = MASTER_STATUS_LABELS[master.status];
    const reason = MASTER_REASON_LABELS[master.reason];
    const parts = [reason ? `${head}（${reason}）` : head];
    if (master.status === 'ready') {
      parts.push(master.reason === 'advertising_facts_complete_market_data_missing' ? '市场数据待补'
        : ['advertising_facts_complete_market_data_present', 'advertising_and_market_data_complete']
          .includes(master.reason) ? '已补充市场数据；覆盖范围见各行来源与缺失项' : '');
    }
    parts.push(report?.full_report_complete === true ? '六模块证据齐全' : '六模块部分完成');
    return `${parts.filter(Boolean).join('；')}。`;
  }

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
    if (!isLifecycleActive() || !state.report) return;
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
      badge.className = `conclusion ${['green','blue','cyan','yellow','orange','red','gray'].includes(row.ui_color) ? row.ui_color : 'gray'}`;
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
    if (!isLifecycleActive()) return;
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

  function showError(error) {
    if (!isLifecycleActive()) { clearPrivateState(); return; }
    clearPrivateState();
    state.report = null;
    document.querySelectorAll('[data-failure-receipt]').forEach(node => node.remove());
    reportUI?.setMetrics([]);
    document.querySelectorAll('[id^="report-"]').forEach(node => {
      if (!['report-rows', 'report-filter-status'].includes(node.id) && !node.children.length) node.textContent = '—';
    });
    tableBody.replaceChildren();
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 21;
    td.className = 'table-empty';
    td.textContent = error?.code === 'REPORT_NOT_GENERATED' ? '该运行的真实报告尚未生成。'
      : error?.code === 'INPUT_INVALID' ? '请选择任务和运行记录；报告地址需要 task 与 run UUID。'
      : '报告暂时无法读取，请确认运行记录和登录权限后重试。';
    tr.appendChild(td);
    tableBody.appendChild(tr);
    document.querySelector('#keyword-count').textContent = '报告加载失败';
    document.querySelector('#report-filter-status').textContent = '未生成分析结论';
  }

  function renderFailureReceipt(receipt) {
    if (!isLifecycleActive()) return;
    showError({ code: 'REPORT_NOT_GENERATED' });
    if (!isLifecycleActive()) return;
    document.querySelector('#keyword-count').textContent = `失败运行 · ${receipt.provider_receipts.length} 条调用回执`;
    document.querySelector('#report-filter-status').textContent = '仅显示登录后读取的脱敏调用证据；此处不是关键词报告，也不包含完整 Provider 响应。';
    const empty = tableBody.querySelector('.table-empty');
    if (empty) empty.textContent = '该运行没有可展示的报告行；下方是失败或进程崩溃恢复回执。';

    const panel = document.createElement('section');
    panel.className = 'panel panel--large';
    panel.dataset.failureReceipt = 'true';
    const title = document.createElement('h2');
    title.textContent = '失败调用证据';
    const summary = document.createElement('p');
    const reason = receipt.failure_reason;
    const reasonText = reason ? `失败阶段：${reason.stage} · 代码：${reason.code}` : '失败阶段：进程租约过期或异常中断';
    const recoveryText = receipt.recovery_reason === 'lease_expired' ? '崩溃后恢复' : '任务失败记录';
    summary.textContent = `${reasonText} · ${recoveryText} · Run ${receipt.run_id}`;
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent = '“结果不确定”只表示本地无法确认 Provider 调用的最终结果；它不证明调用成功或失败。请不要据此自动重放付费请求。';
    const wrap = document.createElement('div');
    wrap.className = 'table-scroll';
    const table = document.createElement('table');
    const head = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const label of ['Provider', '工具', '尝试', '结果', 'HTTP 状态', '请求 SHA-256', '响应 SHA-256', '预留 → 实际（调用 / Credit / Token）']) {
      const th = document.createElement('th'); th.textContent = label; headerRow.appendChild(th);
    }
    head.appendChild(headerRow);
    const body = document.createElement('tbody');
    for (const item of receipt.provider_receipts) {
      const tr = document.createElement('tr');
      const values = [item.provider, item.tool, String(item.attempt), '不确定',
        item.response_status === null ? '未收到状态' : String(item.response_status),
        item.request_sha256?.slice(0, 12) || '—', item.response_sha256?.slice(0, 12) || '—',
        `${item.reserved_calls} → ${item.actual_calls} / ${item.reserved_credits} → ${item.actual_credits} / ${item.reserved_tokens} → ${item.actual_tokens}`];
      for (const value of values) { const td = document.createElement('td'); td.textContent = value; tr.appendChild(td); }
      body.appendChild(tr);
    }
    table.append(head, body); wrap.appendChild(table);
    panel.append(title, summary, note, wrap);
    document.querySelector('.report-meta')?.after(panel);
  }

  document.querySelectorAll('[data-action-filter]').forEach(button => button.addEventListener('click', () => {
    if (!isLifecycleActive()) { clearPrivateState(); return; }
    try { checkReportSession(); } catch (error) { showError(error); return; }
    state.filter = button.dataset.actionFilter;
    if (state.report) render();
  }));
  document.querySelector('#export-report')?.addEventListener('click', () => {
    if (!isLifecycleActive()) { clearPrivateState(); return; }
    try { checkReportSession(); } catch (error) { showError(error); return; }
    if (!state.report) return;
    const record = { payload: null, link: null, url: null, release: null, timer: null };
    exportRecords.add(record);
    try {
      assertLifecycle();
      record.payload = { ...state.report, rows: state.report.rows.filter(matches), export_scope: { filter: state.filter, query: state.query } };
      const blob = new Blob([JSON.stringify(record.payload, null, 2)], { type: 'application/json' });
      record.payload = null;
      record.url = URL.createObjectURL(blob);
      if (typeof reportUI?.trackExportObjectURL === 'function') {
        record.release = lifecycleToken
          ? reportUI.trackExportObjectURL(record.url, lifecycleToken)
          : reportUI.trackExportObjectURL(record.url);
      }
      assertLifecycle();
      record.link = document.createElement('a');
      record.link.href = record.url;
      record.link.download = 'keyword-report.json';
      assertLifecycle();
      record.link.click();
      assertLifecycle();
      record.timer = setTimeout(() => releaseExport(record), 0);
    } catch (_) {
      releaseExport(record);
      if (!isLifecycleActive()) clearPrivateState();
    }
  });
  document.querySelector('#keyword-search')?.addEventListener('input', event => {
    if (!isLifecycleActive()) { clearPrivateState(); return; }
    try { checkReportSession(); } catch (error) { showError(error); return; }
    state.query = event.target.value.trim().toLowerCase(); if (state.report) render();
  });
  try {
    assertLifecycle();
    if (live) {
      reportSession = globalThis.KWCC.auth.checkSession();
      const params = new URL(location.href).searchParams;
      const taskIds = params.getAll('task');
      const runIds = params.getAll('run');
      if (taskIds.length !== 1 || runIds.length !== 1) {
        const error = new Error('报告地址必须只包含一个 task 和一个 run');
        error.code = 'INPUT_INVALID';
        throw error;
      }
      liveSelection = { taskId: taskIds[0], runId: runIds[0] };
      const result = await globalThis.KWCC.reports.read(liveSelection.taskId, liveSelection.runId);
      assertLifecycle();
      report = result?.content;
      checkReportSession();
    } else {
      const response = await fetch(reportUrl);
      assertLifecycle();
      if (!response.ok) throw new Error(`report HTTP ${response.status}`);
      report = await response.json();
      assertLifecycle();
    }
    assertLifecycle();
    if (!report || !Array.isArray(report.rows) || !report.rows.every(row => row && typeof row === 'object')) throw new Error('invalid report');
    assertLifecycle();
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
    const providerEvidence = report.provider_evidence && typeof report.provider_evidence === 'object'
      ? report.provider_evidence : {};
    const providerStatus = providerEvidence.status || report.provider_status ||
      (report.provider_snapshot_version ? 'snapshot_available' : 'not_requested');
    const providerLabels = {
      not_requested: '未请求', snapshot_available: '已有快照', no_market_data: '无市场数据',
      injected_data: '本地注入数据', real_provider_data: '真实 Provider 数据',
      partial: '部分完成', failed: '调用失败', not_generated: '未生成',
    };
    const aiStatus = document.querySelector('#report-ai-status');
    if (aiStatus) aiStatus.textContent = providerLabels[providerStatus] || '状态未确认';
    state.currency = /^[A-Z]{3}$/.test(report.currency_code || '') ? report.currency_code : null;
    document.querySelector('#report-reconciliation').textContent = report.reconciliation?.passed === true ? '通过 · 差值 0' : '失败';
    const strategySummary = document.querySelector('#report-strategy-summary');
    if (strategySummary) {
      const readiness = masterReadinessPrefix(report);
      const legacy = live && report.full_report_complete !== true ? (report.report_scope === 'ad_only' ? '广告数据报告；市场、竞品与图片证据尚未补齐。 ' : '部分数据报告；不代表全部模块验收完成。 ') : '';
      strategySummary.textContent = `${readiness || legacy}当前策略：${text(report.config_version)} · 规则 ${text(report.rule_version)} · 对账${report.reconciliation?.passed === true ? '通过，差值 0' : '未通过，请勿执行建议'}`;
    }
    document.querySelector('#export-report').disabled = false;
    const sum = key => {
      if (!report.rows.length) return null;
      let total = 0;
      for (const row of report.rows) {
        const value = row[key];
        const numeric = typeof value === 'number'
          ? value
          : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
        if (!Number.isFinite(numeric)) return null;
        total += numeric;
      }
      return total;
    };
    const spend = sum('spend');
    const orders = sum('orders');
    const clicks = sum('clicks');
    const impressions = sum('impressions');
    const ctr = clicks === null || impressions === null
      ? '\u5f85\u8865'
      : impressions > 0 ? percent(clicks / impressions) : '—';
    assertLifecycle();
    reportUI?.setMetrics([
      ['\u641c\u7d22\u8bcd', number(report.rows.length)],
      ['\u5e7f\u544a\u603b\u82b1\u8d39', spend === null ? '\u5f85\u8865' : money(spend)],
      ['\u5e7f\u544a\u8ba2\u5355', orders === null ? '\u5f85\u8865' : number(orders)],
      ['整体 CTR', ctr],
    ]);
    render();
    report = null;
  } catch (error) {
    if (!isLifecycleActive()) { clearPrivateState(); return; }
    if (live && error?.code === 'REPORT_NOT_GENERATED') {
      try {
        const result = await globalThis.KWCC.reports.readFailureReceipt(liveSelection.taskId, liveSelection.runId);
        assertLifecycle();
        checkReportSession();
        failureReceipt = result?.content;
        renderFailureReceipt(failureReceipt);
        failureReceipt = null;
        return;
      } catch (receiptError) {
        if (!isLifecycleActive()) { clearPrivateState(); return; }
        showError(receiptError); return;
      }
    }
    showError(error);
  }
  if (!live && !reportUI && isLifecycleActive()) Promise.all([
    fetch(dataPath('market-demo-modules/rank-benchmark.json')).then(async response => { assertLifecycle(); const value = await response.json(); assertLifecycle(); return value; }),
    fetch(dataPath('market-demo-modules/negative-keywords.json')).then(async response => { assertLifecycle(); const value = await response.json(); assertLifecycle(); return value; }),
  ]).then(([rank, negative]) => { if (isLifecycleActive()) renderPhase4Modules(rank, negative); }).catch(() => {});
})();
