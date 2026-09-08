(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const data = await ui.load('negative-keywords.json');
    const groups = [
      ['exact_negative', '精准否定候选', 'exact_negative_candidate', 'badge red'],
      ['phrase_negative', '词组否定候选', 'phrase_negative_candidate', 'badge orange'],
      ['cautious', '慎否', 'cautious', 'badge yellow'],
      ['pending_confirmation', '待确认', 'pending_confirmation', 'badge gray'],
      ['low_cvr_high_spend', '低 CVR 高花费复核', 'low_cvr_high_spend', 'badge orange'],
      ['protected_converted', '已有订单保护', 'protected_converted', 'badge green'],
    ];
    // module03-0.1 artifacts predate the two diagnostic buckets; treat their
    // absence as an empty legacy bucket so old reports remain readable.
    for (const key of ['low_cvr_high_spend', 'protected_converted']) {
      if (!Array.isArray(data?.[key])) data[key] = [];
    }
    if (!data || groups.some(([key]) => !Array.isArray(data[key]) || data[key].some(row => !row || typeof row !== 'object' || Array.isArray(row)))) {
      throw new Error('否词报告结构无效：四类候选必须为行数组。');
    }
    const entries = groups.flatMap(([key, label, expected, color]) => data[key].map(row => ({ key, label, expected, color, row })));
    const reasons = {
      zero_orders_and_hard_stop_boundary: '零订单，达到配置中的点击与花费止损边界',
      zero_orders_with_preliminary_evidence: '零订单，已有初步点击证据；仍需核查词组影响范围',
      evidence_insufficient: '点击证据不足，慎否并继续观察',
      no_click_evidence: '尚无点击证据，待确认',
      required_ad_fields_missing: '广告必需字段缺失，待补数据',
    };
    const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()) : [];
    const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
    const normalize = value => typeof value === 'string' ? value.trim().normalize('NFC').toLocaleLowerCase() : '';
    // A keyword appearing in a cautious/pending bucket must never enter an export,
    // even if a malformed artifact duplicates it into a candidate bucket.
    const protectedKeywords = new Set(entries.filter(entry => entry.key === 'cautious' || entry.key === 'pending_confirmation' || entry.row.negative_status !== entry.expected).map(entry => normalize(entry.row.keyword)));
    const eligible = entry => ['exact_negative', 'phrase_negative'].includes(entry.key)
      && entry.row.export_eligible === true
      && entry.row.negative_status === entry.expected
      && normalize(entry.row.keyword) && !protectedKeywords.has(normalize(entry.row.keyword))
      && entry.row.relevance === 'unrelated' && !String(entry.row.reason || '').includes('conflict')
      && entry.row.orders === 0 && finite(entry.row.clicks) && entry.row.clicks > 0 && finite(entry.row.spend);
    ui.setMetrics(groups.map(([key, label]) => [label, ui.number(data[key].length)]));
    body.replaceChildren();
    body.append(ui.el('p', '候选仅供人工复核，不会写入 Amazon。相关/未知、慎否、待确认、词组冲突及已有订单保护的关键词不进入导出。低 CVR 高花费是独立复核组，不等于否定词。', 'notice'));
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar');
    const label = ui.el('label', '搜索关键词 ');
    const search = ui.el('input');
    search.type = 'search'; search.placeholder = '输入关键词'; label.append(search);
    const filters = ui.el('div', undefined, 'filters');
    filters.setAttribute('aria-label', '否词分类筛选');
    let selected = 'all';
    const buttons = [['all', '全部'], ...groups.map(([key, title]) => [key, title])].map(([key, title]) => {
      const button = ui.el('button', title, 'filter');
      button.type = 'button'; button.dataset.negativeFilter = key;
      button.addEventListener('click', () => { selected = key; render(); });
      filters.append(button); return [key, button];
    });
    const exportButton = ui.el('button', '导出当前候选（人工复核 JSON）', 'button secondary');
    exportButton.id = 'export-negative'; exportButton.type = 'button';
    const exportStatus = ui.el('p', undefined, 'muted'); exportStatus.setAttribute('role', 'status');
    const result = ui.el('div');
    function visibleEntries() {
      const query = search.value.trim().toLocaleLowerCase();
      return entries.filter(entry => (selected === 'all' || entry.key === selected) && (!query || ui.text(entry.row.keyword).toLocaleLowerCase().includes(query)));
    }
    function trace(row) {
      const block = ui.el('div');
      block.append(ui.el('strong', Object.hasOwn(reasons, row.reason) ? reasons[row.reason] : ui.text(row.reason)));
      block.append(ui.el('small', `候选依据：${ui.text(row.reason)} · 原动作规则：${strings(row.rule_hits).join('、') || '—'}`));
      block.append(ui.el('small', `相关性：${ui.text(row.relevance)} · 来源：${ui.text(row.relevance_source)} · 规则版本：${ui.text(row.rule_version)} · 生效配置：${ui.text(row.effective_config_version)}`));
      block.append(ui.el('small', `CVR：${ui.percent(row.cvr_observed)} · 高花费线：${ui.number(row.high_spend_threshold, 2)} · 证据：${ui.text(row.evidence_level)}`));
      block.append(ui.el('small', `原动作：${ui.text(row.action_group)} · ${ui.text(row.next_action_text)}`));
      block.append(ui.el('small', `缺失字段：${strings(row.missing_fields).join('、') || '—'}`));
      return block;
    }
    function render() {
      const visible = visibleEntries();
      const exportable = visible.filter(eligible);
      buttons.forEach(([key, button]) => { button.className = key === selected ? 'filter active' : 'filter'; button.setAttribute('aria-pressed', String(key === selected)); });
      exportButton.disabled = exportable.length === 0;
      exportStatus.textContent = `当前可导出 ${ui.number(exportable.length)} 条候选；导出保留原始数字与规则 / 配置版本，需要人工复核。`;
      result.replaceChildren(visible.length ? ui.table(
        ['关键词', '候选分类', '点击', '花费（原币）', '订单', '销售额（原币）', 'ACOS', '证据与追溯'],
        visible.map(({ row, label, color, expected }) => [ui.text(row.keyword), ui.el('span', row.negative_status === expected ? label : '状态冲突 · 待确认', row.negative_status === expected ? color : 'badge gray'), ui.number(row.clicks), ui.number(row.spend, 2), ui.number(row.orders), ui.number(row.sales, 2), ui.percent(row.acos), trace(row)]),
      ) : ui.el('p', entries.length ? '当前分类或关键词下没有候选。' : '暂无否词候选；不据此判断全部关键词都应保留。', 'table-empty'));
      status.textContent = `${ui.statusPrefix(data)} · ${globalThis.KWCC?.mode === 'live' ? '私有报告' : 'Demo'} · ${ui.number(visible.length)} / ${ui.number(entries.length)} 条 · ${ui.text(data.schema_version)} · 来源 negative-keywords.json`;
    }
    exportButton.addEventListener('click', () => {
      let url;
      let link;
      try {
        const candidates = visibleEntries().filter(eligible).map(({ key, row }) => ({ ...row, candidate_group: key }));
        if (!candidates.length) return;
        const payload = { schema_version: data.schema_version, source: 'negative-keywords.json', write_back: false, review_required: true, currency_code: data.currency_code || null, candidates };
        url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' }));
        link = ui.el('a'); link.href = url; link.download = 'negative-candidates-for-review.json';
        document.body.append(link); link.click();
        exportStatus.textContent = `已导出 ${ui.number(candidates.length)} 条人工复核候选；未写入 Amazon。`;
      } catch (_) { exportStatus.textContent = '导出失败，请重试；报告数据未改变。'; }
      finally { if (link) link.remove(); if (url) setTimeout(() => URL.revokeObjectURL(url), 1000); }
    });
    search.addEventListener('input', render);
    toolbar.append(label, filters, exportButton);
    panel.append(toolbar, exportStatus, result); body.append(panel);
    render();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
