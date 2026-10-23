(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const lifecycleToken = ui.operationToken();
    let data = null, rows = [], rawShareRows = [], shareRows = [], shareBuckets = new Map();
    let comparableShareGroups = [], shareState = null, selected = 'all', search = null;
    ui.onInvalidate(() => {
      data = null; rows = []; rawShareRows = []; shareRows = [];
      shareBuckets.clear(); comparableShareGroups = []; shareState = null;
      selected = 'all';
      if (search) search.value = '';
      search = null;
    });
    data = await ui.load('rank-benchmark.json');
    ui.assertOperation(lifecycleToken);
    if (!data || !Array.isArray(data.rows) || data.rows.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
      throw new Error('排名报告结构无效：缺少 rows 数组或行对象。');
    }
    rows = data.rows;
    const validRank = value => typeof value === 'number' && Number.isInteger(value) && value > 0;
    const validAsin = value => typeof value === 'string' && /^[A-Z0-9]{10}$/i.test(value.trim());
    const rank = value => validRank(value) ? ui.number(value) : '—';
    const signed = value => typeof value === 'number' && Number.isFinite(value) ? (value > 0 ? '+' : '') + ui.number(value) : '—';
    const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()) : [];
    const benchmarks = row => {
      const source = Array.isArray(row.benchmarks)
        ? row.benchmarks
        : (validAsin(row.benchmark_asin) && validRank(row.benchmark_organic_rank)
          ? [{ asin: row.benchmark_asin, organic_rank: row.benchmark_organic_rank, rank_gap: row.rank_gap }]
          : []);
      return source
        .filter(item => item && typeof item === 'object' && validAsin(item.asin) && validRank(item.organic_rank))
        .map(item => ({ ...item, asin: item.asin.trim().toUpperCase() }))
        .sort((left, right) => left.organic_rank - right.organic_rank || left.asin.localeCompare(right.asin))
        .slice(0, 3);
    };
    const benchmarkText = item => item ? `${ui.text(item.asin)} · #${rank(item.organic_rank)}${typeof item.rank_gap === 'number' ? ` · 差 ${signed(item.rank_gap)}` : ''}` : '—';
    const rankSampleInfo = row => {
      const scope = row.rank_scope && typeof row.rank_scope === 'object' && !Array.isArray(row.rank_scope) ? row.rank_scope : {};
      const period = row.rank_period && typeof row.rank_period === 'object' && !Array.isArray(row.rank_period) ? row.rank_period : {};
      const hasDateRange = period.start_date || period.end_date;
      const dateRange = hasDateRange ? `${ui.text(period.start_date)} 至 ${ui.text(period.end_date)}` : '未提供精确日期范围';
      return [
        `站点 ${ui.text(scope.country)}`,
        `窗口 ${ui.text(period.window)}`,
        `日期 ${dateRange}`,
        `采样 ${ui.text(row.rank_sampled_at)}`,
        `来源 ${ui.text(row.provider_source)}`,
      ].join(' · ');
    };
    const missing = row => Array.from(new Set([
      ...strings(row.missing_fields),
      ...['my_organic_rank', 'my_ad_rank'].filter(key => !validRank(row[key])),
      ...['my_asin'].filter(key => !validAsin(row[key])),
      ...(benchmarks(row).length < 3 ? ['benchmark_asins'] : []),
      ...['rank_gap', 'rank_change_7d', 'rank_change_14d', 'rank_change_30d'].filter(key => typeof row[key] !== 'number' || !Number.isFinite(row[key])),
    ]));
    ui.setMetrics([
      ['关键词', ui.number(rows.length)],
      ['有自然位', ui.number(rows.filter(row => validRank(row.my_organic_rank)).length)],
      ['三标杆齐全', ui.number(rows.filter(row => benchmarks(row).length === 3).length)],
      ['待补采', ui.number(rows.filter(row => !validRank(row.my_organic_rank) || benchmarks(row).length < 3).length)],
    ]);
    body.replaceChildren();
    const benchmarkCount = rows.filter(row => validRank(row.my_organic_rank) && benchmarks(row).length > 0).length;
    const historyCount = rows.filter(row => [row.rank_change_7d, row.rank_change_14d, row.rank_change_30d].some(value => typeof value === 'number' && Number.isFinite(value))).length;
    if (rows.length && (benchmarkCount < rows.length || historyCount < rows.length)) {
      body.append(ui.el('p', `数据覆盖不足：${rows.length} 个关键词中，仅 ${benchmarkCount} 条可对比自己与标杆自然位，${historyCount} 条有历史变化。缺失项需补采快照，当前不能形成完整标杆或趋势结论。`, 'notice'));
    }
    body.append(ui.el('p', '位次越小越靠前。差距 = 我的自然位 − 标杆自然位；正数表示落后。未上榜或未返回一律显示 —。7 / 14 / 30 天变化按原始快照呈现；缺少历史时不推算趋势。', 'notice'));
    const shareBoardPresent = Object.hasOwn(data, 'share_board');
    const shareBoardMalformed = shareBoardPresent && !Array.isArray(data.share_board);
    rawShareRows = Array.isArray(data.share_board) ? data.share_board : [];
    shareRows = rawShareRows.filter(row => row && typeof row === 'object' && !Array.isArray(row));
    const rejectedShareRows = rawShareRows.length - shareRows.length;
    const sharePanel = ui.el('section', undefined, 'panel');
    const shareStatePresent = Object.hasOwn(data, 'share_module_status');
    shareState = data.share_module_status;
    const shareStateValid = shareState && typeof shareState === 'object' && !Array.isArray(shareState)
      && ['ready', 'partial', 'failed', 'not_generated'].includes(shareState.status);
    const shareStateLabel = shareStateValid
      ? ui.statusPrefix({ _module_state: shareState })
      : shareStatePresent
        ? '状态未确认（份额模块状态结构异常）'
        : '状态未确认（未提供份额模块状态）';
    sharePanel.append(ui.el('h2', '流量份额与依赖度'), ui.el('p', `份额模块：${shareStateLabel}`, shareStateValid && shareState.status === 'ready' ? 'muted' : 'notice'), ui.el('p', shareRows.length
      ? '每行按关键词和 ASIN 独立呈现。市场份额、ASIN 对该词依赖度、流量获取率使用各自明确口径；未知或不兼容分母保持缺失，不合并或跨行比较。'
      : shareBoardMalformed || rejectedShareRows
        ? '份额数据结构异常，不能将结构错误当作“没有数据”；请检查产物版本与 schema。'
        : '当前报告没有可核查的份额数据，不能用自然位或广告数据代替份额。', shareRows.length ? 'muted' : 'notice'));
    if (shareBoardMalformed) sharePanel.append(ui.el('p', 'share_board 类型异常：应为数组；未生成份额结论。', 'notice'));
    if (rejectedShareRows) sharePanel.append(ui.el('p', `已忽略 ${rejectedShareRows} 行结构异常份额数据；其余有效行仍可查看。`, 'notice'));
    const shareValue = item => {
      if (!item || item.status !== 'valid') {
        if (item?.status === 'invalid_value' || item?.status === 'invalid_unit') return `不可用（原值 ${ui.text(item.raw_value)}，单位 ${ui.text(item.raw_unit)}）`;
        if (item?.status === 'unknown_unit') return `—（单位未验证：${ui.text(item.raw_unit)}）`;
        if (item?.status === 'unknown_denominator') return '—（分母口径/证据缺失）';
        if (item?.status === 'scope_unknown') return '—（ASIN、周期、范围或来源未绑定）';
        return '—（数据未返回）';
      }
      const denominator = item.denominator === null || item.denominator === undefined ? '直接值' : ui.number(item.denominator);
      return `${ui.percent(item.value)} · ${ui.text(item.unit)} · ${ui.text(item.denominator_definition)} (${denominator}) · schema ${ui.text(item.schema_version)}`;
    };
    if (shareRows.length) sharePanel.append(ui.table(
      ['关键词', 'ASIN', '市场份额（值/单位/分母口径）', 'ASIN 关键词依赖度（值/单位/分母口径）', '流量获取率（独立口径）', '范围/周期/来源/状态'],
      shareRows.map(row => [ui.text(row.keyword), ui.text(row.asin || row.my_asin || '未绑定 ASIN'), shareValue(row.keyword_market_share), shareValue(row.asin_keyword_dependency), shareValue(row.traffic_acquisition_rate), `${ui.text(row.scope)} / ${ui.text(row.period)} / ${ui.text(row.source)} / ${ui.text(row.status)}`]),
    ));
    for (const row of shareRows) {
      const item = row.keyword_market_share;
      const asin = typeof (row.asin || row.my_asin) === 'string' ? (row.asin || row.my_asin).trim().toUpperCase() : '';
      const keyword = typeof row.keyword === 'string' ? row.keyword.trim() : '';
      const denominator = item?.denominator;
      if (!keyword || !validAsin(asin) || item?.status !== 'valid'
          || typeof item.value !== 'number' || !Number.isFinite(item.value) || item.value < 0 || item.value > 1
          || typeof row.scope !== 'string' || !row.scope.trim() || row.scope.trim().toLowerCase() === 'unknown'
          || typeof row.period !== 'string' || !row.period.trim()
          || typeof row.source !== 'string' || !row.source.trim()
          || typeof item.schema_version !== 'string' || !item.schema_version.trim()
          || typeof item.denominator_definition !== 'string' || !item.denominator_definition.trim()
          || !['ratio', 'percent_number', 'percent_text'].includes(item.unit)
          || (denominator != null && (typeof denominator !== 'number' || !Number.isFinite(denominator) || denominator <= 0))) continue;
      const signature = [keyword.toLocaleLowerCase(), row.scope.trim().toLocaleLowerCase(), row.period.trim(),
        row.source.trim(), item.schema_version.trim(), item.unit, item.denominator_definition.trim(),
        denominator == null ? 'direct' : String(denominator)].join('\u0000');
      const group = shareBuckets.get(signature) || {keyword, scope: row.scope.trim(), period: row.period.trim(),
        source: row.source.trim(), denominatorDefinition: item.denominator_definition.trim(), rows: []};
      group.rows.push({asin, value: item.value});
      shareBuckets.set(signature, group);
    }
    comparableShareGroups = [...shareBuckets.values()].filter(group => {
      const asins = group.rows.map(item => item.asin);
      return asins.length >= 2 && new Set(asins).size === asins.length;
    });
    const shareComparison = ui.el('section', undefined, 'panel share-comparison');
    shareComparison.append(ui.el('h2', '同口径市场份额对比'), ui.el('p', '仅比较 ASIN、站点、周期、来源、Schema 与分母口径一致的有效市场份额；自然位标杆仅按排名快照显示。', 'muted'));
    if (!comparableShareGroups.length) {
      shareComparison.append(ui.el('p', '当前没有至少两个 ASIN 的同口径有效份额；不绘制对比条。', 'table-empty'));
    } else {
      comparableShareGroups.forEach(group => {
        const panel = ui.el('div', undefined, 'share-comparison-group');
        panel.append(ui.el('h3', group.keyword), ui.el('p', `范围 ${group.scope} · 周期 ${group.period} · 来源 ${group.source} · 分母 ${group.denominatorDefinition}`, 'muted'));
        const rankRow = rows.find(row => typeof row.keyword === 'string' && row.keyword.trim().toLocaleLowerCase() === group.keyword.toLocaleLowerCase());
        const naturalRanks = new Map(benchmarks(rankRow || {}).map(item => [item.asin.trim().toUpperCase(), item.organic_rank]));
        const leaderValue = Math.max(...group.rows.map(item => item.value));
        const barRows = [...group.rows].sort((left, right) => right.value - left.value || left.asin.localeCompare(right.asin)).map(item => {
          const line = ui.el('div', undefined, 'share-bar-row');
          const labels = ui.el('div', undefined, 'share-bar-labels');
          labels.append(ui.el('strong', item.asin), ui.el('span', `${ui.percent(item.value)}${item.value === leaderValue ? ' · 份额领先者' : ''}`));
          const bar = document.createElement('progress');
          bar.max = 1; bar.value = item.value; bar.setAttribute('max', '1');
          bar.setAttribute('value', String(item.value)); bar.setAttribute('aria-label', `${item.asin} 市场份额 ${ui.percent(item.value)}`);
          line.append(labels, bar);
          const organicRank = naturalRanks.get(item.asin);
          if (organicRank !== undefined) line.append(ui.el('small', `自然位标杆：第 ${ui.number(organicRank)} 位`));
          return line;
        });
        panel.append(...barRows);
        shareComparison.append(panel);
      });
    }
    sharePanel.append(shareComparison);
    body.append(sharePanel);
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar');
    const label = ui.el('label', '搜索关键词或 ASIN ');
    search = ui.el('input');
    search.type = 'search';
    search.placeholder = '输入关键词或 ASIN';
    label.append(search);
    const filters = ui.el('div', undefined, 'filters');
    filters.setAttribute('aria-label', '排名筛选');
    const result = ui.el('div');
    const choices = [['all', '全部'], ['ranked', '有自然位'], ['missing', '自然位待补'], ['benchmark', '有标杆位次']];
    const buttons = choices.map(([key, title]) => {
      const button = ui.el('button', title, 'filter');
      button.type = 'button';
      button.dataset.rankFilter = key;
      button.addEventListener('click', () => {
        if (!ui.operationIsActive(lifecycleToken)) return;
        selected = key; render();
      });
      filters.append(button);
      return [key, button];
    });
    function render() {
      if (!ui.operationIsActive(lifecycleToken)) return;
      const query = search.value.trim().toLocaleLowerCase();
      const visible = rows.filter(row => {
        const matches = [row.keyword, row.my_asin, ...benchmarks(row).map(item => item.asin)].some(value => typeof value === 'string' && value.toLocaleLowerCase().includes(query));
        return (!query || matches) && (selected === 'all' || (selected === 'ranked' && validRank(row.my_organic_rank)) || (selected === 'missing' && (!validRank(row.my_organic_rank) || benchmarks(row).length < 3)) || (selected === 'benchmark' && benchmarks(row).length > 0));
      });
      buttons.forEach(([key, button]) => { button.className = key === selected ? 'filter active' : 'filter'; button.setAttribute('aria-pressed', String(key === selected)); });
      result.replaceChildren(visible.length ? ui.table(
        ['关键词', '周搜索量', 'ABA统计周期', '排名站点/窗口/日期/采样/来源', '自己 ASIN', '我的自然位', '我的广告位', '标杆 1', '标杆 2', '标杆 3', '7 天变化', '14 天变化', '30 天变化', '缺失字段'],
        visible.map(row => {
          const items = benchmarks(row);
          const period = row.aba_report_from_date || row.aba_report_to_date ? `${ui.text(row.aba_report_from_date)} 至 ${ui.text(row.aba_report_to_date)}` : '—';
          return [ui.text(row.keyword), ui.number(row.weekly_search_volume), period, rankSampleInfo(row), ui.text(row.my_asin), rank(row.my_organic_rank), rank(row.my_ad_rank), benchmarkText(items[0]), benchmarkText(items[1]), benchmarkText(items[2]), signed(row.rank_change_7d), signed(row.rank_change_14d), signed(row.rank_change_30d), missing(row).join('、') || '—'];
        }),
      ) : ui.el('p', rows.length ? '没有符合筛选条件的排名记录。' : '暂无排名数据；等待有排名快照的报告。', 'table-empty'));
      status.textContent = `${ui.statusPrefix(data)} · ${globalThis.KWCC?.mode === 'live' ? '私有报告' : 'Demo'} · ${ui.number(visible.length)} / ${ui.number(rows.length)} 条 · ${ui.text(data.schema_version)} · 来源 rank-benchmark.json`;
    }
    search.addEventListener('input', () => {
      if (ui.operationIsActive(lifecycleToken)) render();
    });
    toolbar.append(label, filters);
    panel.append(toolbar, result);
    body.append(panel);
    render();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
