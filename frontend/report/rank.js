(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const data = await ui.load('rank-benchmark.json');
    if (!data || !Array.isArray(data.rows) || data.rows.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
      throw new Error('排名报告结构无效：缺少 rows 数组或行对象。');
    }
    const rows = data.rows;
    const validRank = value => typeof value === 'number' && Number.isInteger(value) && value > 0;
    const rank = value => validRank(value) ? ui.number(value) : '—';
    const signed = value => typeof value === 'number' && Number.isFinite(value) ? (value > 0 ? '+' : '') + ui.number(value) : '—';
    const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()) : [];
    const benchmarks = row => Array.isArray(row.benchmarks)
      ? row.benchmarks.filter(item => item && typeof item === 'object' && validRank(item.organic_rank)).slice(0, 3)
      : (validRank(row.benchmark_organic_rank) ? [{ asin: row.benchmark_asin, organic_rank: row.benchmark_organic_rank, rank_gap: row.rank_gap }] : []);
    const benchmarkText = item => item ? `${ui.text(item.asin)} · #${rank(item.organic_rank)}${typeof item.rank_gap === 'number' ? ` · 差 ${signed(item.rank_gap)}` : ''}` : '—';
    const missing = row => Array.from(new Set([
      ...strings(row.missing_fields),
      ...['my_organic_rank', 'my_ad_rank'].filter(key => !validRank(row[key])),
      ...['my_asin'].filter(key => !row[key]),
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
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar');
    const label = ui.el('label', '搜索关键词或 ASIN ');
    const search = ui.el('input');
    search.type = 'search';
    search.placeholder = '输入关键词或 ASIN';
    label.append(search);
    const filters = ui.el('div', undefined, 'filters');
    filters.setAttribute('aria-label', '排名筛选');
    const result = ui.el('div');
    let selected = 'all';
    const choices = [['all', '全部'], ['ranked', '有自然位'], ['missing', '自然位待补'], ['benchmark', '有标杆位次']];
    const buttons = choices.map(([key, title]) => {
      const button = ui.el('button', title, 'filter');
      button.type = 'button';
      button.dataset.rankFilter = key;
      button.addEventListener('click', () => { selected = key; render(); });
      filters.append(button);
      return [key, button];
    });
    function render() {
      const query = search.value.trim().toLocaleLowerCase();
      const visible = rows.filter(row => {
        const matches = [row.keyword, row.my_asin, ...benchmarks(row).map(item => item.asin)].some(value => typeof value === 'string' && value.toLocaleLowerCase().includes(query));
        return (!query || matches) && (selected === 'all' || (selected === 'ranked' && validRank(row.my_organic_rank)) || (selected === 'missing' && (!validRank(row.my_organic_rank) || benchmarks(row).length < 3)) || (selected === 'benchmark' && benchmarks(row).length > 0));
      });
      buttons.forEach(([key, button]) => { button.className = key === selected ? 'filter active' : 'filter'; button.setAttribute('aria-pressed', String(key === selected)); });
      result.replaceChildren(visible.length ? ui.table(
        ['关键词', '周搜索量', '统计周期', '自己 ASIN', '我的自然位', '标杆 1', '标杆 2', '标杆 3', '7 天变化', '14 天变化', '30 天变化', '缺失字段'],
        visible.map(row => {
          const items = benchmarks(row);
          const period = row.aba_report_from_date || row.aba_report_to_date ? `${ui.text(row.aba_report_from_date)} 至 ${ui.text(row.aba_report_to_date)}` : '—';
          return [ui.text(row.keyword), ui.number(row.weekly_search_volume), period, ui.text(row.my_asin), rank(row.my_organic_rank), benchmarkText(items[0]), benchmarkText(items[1]), benchmarkText(items[2]), signed(row.rank_change_7d), signed(row.rank_change_14d), signed(row.rank_change_30d), missing(row).join('、') || '—'];
        }),
      ) : ui.el('p', rows.length ? '没有符合筛选条件的排名记录。' : '暂无排名数据；等待有排名快照的报告。', 'table-empty'));
      status.textContent = `${ui.statusPrefix(data)} · ${globalThis.KWCC?.mode === 'live' ? '私有报告' : 'Demo'} · ${ui.number(visible.length)} / ${ui.number(rows.length)} 条 · ${ui.text(data.schema_version)} · 来源 rank-benchmark.json`;
    }
    search.addEventListener('input', render);
    toolbar.append(label, filters);
    panel.append(toolbar, result);
    body.append(panel);
    render();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
