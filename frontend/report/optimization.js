(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const data = await ui.load('optimization-plan.json');
    if (!data || !Array.isArray(data.actions) || data.actions.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
      throw new Error('优化方案结构无效：缺少 actions 行数组。');
    }
    const actions = data.actions;
    // Badge classes are selected only from this local mapping, never from data.
    const groups = {
      scale_up: ['加投候选', 'badge green'], defend_rank: ['核心防守', 'badge green'],
      hold_steady: ['保持 / 复盘', 'badge cyan'], cautious_test: ['新词测试', 'badge yellow'],
      continue_observation: ['继续观察', 'badge yellow'], optimize_listing: ['Listing 优化', 'badge orange'],
      optimize_bid: ['竞价优化', 'badge orange'], optimize_structure: ['结构优化', 'badge orange'],
      stop_loss: ['止损复核', 'badge red'], reduce_or_pause: ['降投 / 暂停复核', 'badge red'],
      data_missing: ['数据待补', 'badge gray'],
    };
    const factLabels = {
      impressions: '展示', clicks: '点击', spend: '花费（原币）', orders: '订单', sales: '销售额（原币）',
      ctr: 'CTR', cpc: 'CPC（原币）', cvr: 'CVR', acos: 'ACOS', roas: 'ROAS', organic_rank: '自然位',
      ad_rank: '广告位', market_search_volume: '市场搜索量', market_opportunity_score: '机会评分',
    };
    const configLabels = {
      config_version: '配置版本', stop_loss: '止损边界', organic_defense: '自然位防守', acos: 'ACOS 边界',
      diagnostics: '诊断阈值', evidence: '证据阈值', zero_order_clicks: '零单点击阈值', zero_order_spend: '零单花费阈值（原币）',
      core_max_rank: '核心最大位次', max_defense_acos: '最大防守 ACOS', target: '目标 ACOS', tolerance: '容忍 ACOS', break_even: '盈亏平衡 ACOS',
      low_ctr: '低 CTR 阈值', low_cvr: '低 CVR 阈值', insufficient_clicks_max: '证据不足点击上界',
      preliminary_clicks_min: '初步证据点击下界', sufficient_clicks_min: '充分证据点击下界',
      preliminary_orders_min: '初步证据订单下界', sufficient_orders_min: '充分证据订单下界',
    };
    const knownGroup = row => Object.hasOwn(groups, row.action_group) ? row.action_group : 'unknown';
    const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()) : [];
    const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    const valueText = value => value == null || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : typeof value === 'boolean' ? String(value) : ui.text(value);
    const hasValue = value => value != null && value !== '' && (!Array.isArray(value) || value.length > 0) && (typeof value !== 'object' || Object.keys(value).length > 0);
    const hasConfigValues = row => Object.entries(object(row.config_refs)).some(([key, value]) => key !== 'config_version' && hasValue(value));
    const completeTrace = row => Object.values(object(row.data_facts)).some(value => typeof value === 'number' && Number.isFinite(value)) && strings(row.rule_hits).length > 0 && hasConfigValues(row) && hasValue(row.next_action_text);
    const reviewFields = ['clicks', 'spend', 'orders', 'sales', 'ctr', 'cpc', 'cvr', 'acos', 'roas', 'organic_rank', 'ad_rank'];
    function factValue(key, value) {
      if (['ctr', 'cvr', 'acos'].includes(key)) return ui.percent(value);
      if (['spend', 'sales', 'cpc', 'roas', 'market_opportunity_score'].includes(key)) return ui.number(value, 2);
      if (['organic_rank', 'ad_rank'].includes(key) && (typeof value !== 'number' || !Number.isInteger(value) || value <= 0)) return '—';
      return ui.number(value);
    }
    function configList(value, parent = '') {
      const list = ui.el('ul');
      for (const [key, entry] of Object.entries(object(value))) {
        const label = Object.hasOwn(configLabels, key) ? configLabels[key] : key;
        const item = ui.el('li');
        const path = parent ? `${parent}.${key}` : key;
        if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
          item.append(ui.el('strong', `${label} (${path})`), configList(entry, path));
        } else {
          const isPercent = ['target', 'tolerance', 'break_even', 'max_defense_acos', 'low_ctr', 'low_cvr'].includes(key);
          item.textContent = `${label} (${path})：${isPercent ? ui.percent(entry) : valueText(entry)}`;
        }
        list.append(item);
      }
      if (!list.childNodes.length) list.append(ui.el('li', '—（配置值未提供）'));
      return list;
    }
    function trace(row) {
      const details = ui.el('details');
      details.append(ui.el('summary', completeTrace(row) ? '查看事实 → 规则 → 配置 → 动作' : '追溯待补 · 查看事实 → 规则 → 配置 → 动作'));
      details.append(ui.el('h3', '1 · 数据事实'));
      const facts = object(row.data_facts);
      const list = ui.el('ul');
      Object.entries(factLabels).forEach(([key, title]) => list.append(ui.el('li', `${title} (${key})：${factValue(key, facts[key])}`)));
      details.append(list, ui.el('h3', '2 · 规则命中'));
      const hits = strings(row.rule_hits);
      details.append(ui.el('p', hits.join(' → ') || '—（规则命中未提供）'));
      details.append(ui.el('p', `规则版本：${ui.text(row.rule_version ?? data.rule_version)}`, 'muted'));
      details.append(ui.el('h3', '3 · 当前配置值'), configList(row.config_refs));
      if (!hasConfigValues(row)) details.append(ui.el('p', '此动作的具体阈值未在产物中留底；不能仅凭配置版本认定追溯完整。', 'muted'));
      details.append(ui.el('h3', '4 · 最终动作'), ui.el('p', ui.text(row.next_action_text)), ui.el('p', `action_group：${ui.text(row.action_group)} · action_type：${ui.text(row.action_type)}`, 'muted'));
      return details;
    }
    function monitoring(row) {
      const block = ui.el('div');
      block.append(ui.el('strong', '观察窗口'), ui.el('p', hasValue(row.observation_window) ? valueText(row.observation_window) : '—（当前产物未提供，待确认周期）'));
      block.append(ui.el('strong', '退出条件'), ui.el('p', hasValue(row.exit_conditions) ? valueText(row.exit_conditions) : '—（当前产物未提供，待补配置化条件）'));
      block.append(ui.el('small', '落实前核对样本量、订单变化及对应配置边界；页面不会推算新的执行阈值。'));
      return block;
    }
    function review(row) {
      const details = ui.el('details'); details.append(ui.el('summary', '复盘指标与本期基线'));
      if (hasValue(row.review_metrics)) details.append(ui.el('p', `报告复盘安排：${valueText(row.review_metrics)}`));
      else details.append(ui.el('p', '以下为页面复核清单；实际复盘周期、目标和负责人待确认。', 'muted'));
      const list = ui.el('ul');
      reviewFields.forEach(key => list.append(ui.el('li', `${factLabels[key]}：本期 ${factValue(key, object(row.data_facts)[key])} → 下期 —（待采集）`)));
      details.append(list); return details;
    }
    ui.setMetrics([
      ['动作', ui.number(actions.length)], ['止损 / 暂停复核', ui.number(actions.filter(row => ['stop_loss', 'reduce_or_pause'].includes(row.action_group)).length)],
      ['追溯字段待补', ui.number(actions.filter(row => !completeTrace(row)).length)],
      ['观察退出待补', ui.number(actions.filter(row => !hasValue(row.exit_conditions) || !hasValue(row.observation_window)).length)],
    ]);
    body.replaceChildren();
    body.append(ui.el('p', '仅展示规则生成的运营方案，不写入 Amazon。AI 不决定动作；所有阈值只读自 config_refs。当前产物未携带的周期、币种、规则版本或观察退出条件保持待补，不据此直接执行。', 'notice'));
    if (data.ai_may_change_action !== false || actions.some(row => row.ai_may_change_action !== false)) {
      body.append(ui.el('p', '产物未确认 AI 动作只读契约，请先复核生成来源。本页仍不执行任何动作。', 'notice'));
    }
    const coverage = ui.el('section', undefined, 'panel');
    coverage.append(ui.el('h2', '运营方案覆盖范围'), ui.el('p', '已按产物呈现预算加投候选、核心防守、新词测试、止损与优化动作。Broad / Phrase / Exact 内耗、Search Term → Exact 迁移及具体 Broad 调价需要活动、广告组和匹配类型证据；当前 schema 未提供，保持待分析。', 'muted'));
    body.append(coverage);
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar');
    const label = ui.el('label', '搜索关键词 / 规则 ');
    const search = ui.el('input'); search.type = 'search'; search.placeholder = '输入关键词或规则编号'; label.append(search);
    const filters = ui.el('div', undefined, 'filters'); filters.setAttribute('aria-label', '优化动作筛选');
    let selected = 'all';
    const choices = [['all', '全部'], ...Object.entries(groups).map(([key, [title]]) => [key, title]), ['trace_missing', '追溯待补'], ['unknown', '未知动作']];
    const buttons = choices.map(([key, title]) => {
      const button = ui.el('button', title, 'filter'); button.type = 'button'; button.dataset.optimizationFilter = key;
      button.addEventListener('click', () => { selected = key; render(); }); filters.append(button); return [key, button];
    });
    const result = ui.el('div');
    function render() {
      const query = search.value.trim().toLocaleLowerCase();
      const visible = actions.filter(row => (selected === 'all' || (selected === 'trace_missing' ? !completeTrace(row) : knownGroup(row) === selected)) && (!query || [ui.text(row.keyword), ...strings(row.rule_hits)].some(value => value.toLocaleLowerCase().includes(query))));
      buttons.forEach(([key, button]) => { button.className = key === selected ? 'filter active' : 'filter'; button.setAttribute('aria-pressed', String(key === selected)); });
      result.replaceChildren(visible.length ? ui.table(
        ['关键词', '最终动作与执行类型', '事实 → 规则 → 配置 → 动作', '观察与退出条件', '下一轮复盘'],
        visible.map(row => {
          const [title, color] = Object.hasOwn(groups, row.action_group) ? groups[row.action_group] : ['未知动作 · 人工复核', 'badge gray'];
          const action = ui.el('div'); action.append(ui.el('span', title, color), ui.el('p', ui.text(row.next_action_text)), ui.el('small', ui.text(row.action_type)));
          return [ui.text(row.keyword), action, trace(row), monitoring(row), review(row)];
        }),
      ) : ui.el('p', actions.length ? '没有符合筛选条件的优化动作。' : '暂无优化方案；等待规则引擎生成带事实与配置的动作。', 'table-empty'));
      status.textContent = `Demo · ${visible.length} / ${actions.length} 个动作 · ${ui.text(data.schema_version)} · 来源 optimization-plan.json · 未执行 Amazon 写入`;
    }
    search.addEventListener('input', render); toolbar.append(label, filters); panel.append(toolbar, result); body.append(panel); render();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
