(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const data = await ui.load('listing-diagnostics.json');
    const isRows = value => Array.isArray(value) && value.every(row => row && typeof row === 'object' && !Array.isArray(row));
    if (!data || !isRows(data.checklist?.items) || !isRows(data.self_images?.images) || !isRows(data.competitor_images?.images) || !isRows(data.conversion_diagnostics)) {
      throw new Error('Listing 报告结构无效：缺少 checklist、图组或转化诊断数组。');
    }
    const items = data.checklist.items;
    const self = data.self_images;
    const competitors = data.competitor_images;
    const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()) : [];
    const values = value => value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : ui.text(value);
    const states = { pass: ['通过', 'badge green'], fail: ['未通过', 'badge red'], unknown: ['待核验', 'badge gray'] };
    const stateOf = item => Object.hasOwn(states, item.status) ? item.status : 'unknown';
    const badge = item => { const [label, color] = states[stateOf(item)]; return ui.el('span', `${label} · ${stateOf(item)}`, color); };
    function imageURL(value) {
      if (typeof value !== 'string' || value !== value.trim() || /[\s\u0000-\u001f\u007f-\u009f\\]/.test(value)) return null;
      try {
        const url = new URL(value);
        const host = url.hostname.toLowerCase().replace(/\.$/, '');
        if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443')) return null;
        if (!/^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/.test(host) || /^[\d.]+$/.test(host)) return null;
        if (/(^|\.)(example|localhost)(\.|$)|\.(invalid|test|local|internal)$/.test(host)) return null;
        return url.href;
      } catch (_) { return null; }
    }
    const evidenceItems = item => Array.isArray(item.evidence) ? item.evidence.filter(value => value != null && value !== '') : [];
    ui.setMetrics([
      ['检查项', ui.number(items.length)], ['待核验', ui.number(items.filter(item => stateOf(item) === 'unknown').length)],
      ['自有 / 竞品图记录', `${self.images.length} / ${competitors.images.length}`],
      ['转化检查触发', ui.number(data.conversion_diagnostics.filter(row => row.triggered === true).length)],
    ]);
    body.replaceChildren();
    body.append(ui.el('p', '状态与证据均来自报告。unknown 表示尚未核验，不计为通过。当前未请求视觉模型；不会根据占位图片生成观察结论。高机会、低转化只触发检查，不证明图片存在问题。', 'notice'));
    const meta = ui.el('p', `Schema：${ui.text(data.schema_version)} · checklist：${ui.text(data.checklist.schema_version)} · AI：${ui.text(data.checklist.ai_status)} · 已记录 Provider 调用：${ui.number(data.provider_calls)}`, 'muted');
    body.append(meta);
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar'); toolbar.append(ui.el('h2', 'Checklist 与证据状态'));
    const filters = ui.el('div', undefined, 'filters'); filters.setAttribute('aria-label', 'Checklist 状态筛选');
    let selected = 'all';
    const buttons = [['all', '全部'], ['unknown', '待核验'], ['fail', '未通过'], ['pass', '通过']].map(([key, title]) => {
      const button = ui.el('button', title, 'filter'); button.type = 'button'; button.dataset.listingFilter = key;
      button.addEventListener('click', () => { selected = key; renderChecklist(); });
      filters.append(button); return [key, button];
    });
    const result = ui.el('div');
    function evidence(item) {
      const block = ui.el('div'); const entries = evidenceItems(item);
      if (!entries.length) block.append(ui.el('p', '无观察证据；需人工核验或补充已审核的观察记录。'));
      entries.forEach(entry => block.append(ui.el('p', values(entry))));
      if (stateOf(item) !== 'unknown' && !entries.length) block.append(ui.el('strong', '报告已有结论，但缺少支撑证据，需复核。'));
      return block;
    }
    function renderChecklist() {
      const visible = items.filter(item => selected === 'all' || stateOf(item) === selected);
      buttons.forEach(([key, button]) => { button.className = key === selected ? 'filter active' : 'filter'; button.setAttribute('aria-pressed', String(key === selected)); });
      result.replaceChildren(visible.length ? ui.table(
        ['检查编号 / 分类', '检查问题（评价标准）', '重要度', '报告状态', '观察证据', '关联图片组'],
        visible.map(item => [ui.text(item.check_id) + ' / ' + ui.text(item.category), ui.text(item.question), ui.text(item.severity), badge(item), evidence(item), `自己：${ui.text(data.checklist.image_group_id)}；竞品：${ui.text(data.checklist.competitor_group_id)}`]),
      ) : ui.el('p', items.length ? '该状态下没有检查项。' : '暂无 checklist；等待检查标准与证据。', 'table-empty'));
      status.textContent = `${globalThis.KWCC?.mode === 'live' ? '私有报告' : 'Demo'} · 显示 ${visible.length} / ${items.length} 项检查 · 来源 listing-diagnostics.json`;
    }
    toolbar.append(filters); panel.append(toolbar, result); body.append(panel);
    function renderImages(group, title) {
      const section = ui.el('section', undefined, 'panel'); section.append(ui.el('h2', title), ui.el('p', `图片组：${ui.text(group.group_id)} · ${group.images.length} 张留底记录`, 'muted'));
      const grid = ui.el('div', undefined, 'image-grid');
      if (!group.images.length) grid.append(ui.el('p', '尚未提供图片组内容。', 'table-empty'));
      if (!group.images.some(img => imageURL(img.url))) grid.append(ui.el('p', '当前资料无有效图片；example.* 占位地址不会加载。', 'notice'));
      group.images.forEach(item => {
        const card = ui.el('figure', undefined, 'image-card');
        card.append(ui.el('figcaption', `图片 ${ui.text(item.image_id)} · 位置 ${ui.number(item.position)}`));
        const safe = imageURL(item.url);
        if (safe) {
          const load = ui.el('button', '加载图片（外部资源）', 'button secondary'); load.type = 'button';
          load.addEventListener('click', () => {
            const img = ui.el('img'); img.alt = `${title} · ${ui.text(item.image_id)}`; img.width = 240; img.height = 180;
            img.loading = 'lazy'; img.decoding = 'async'; img.referrerPolicy = 'no-referrer';
            img.addEventListener('error', () => img.replaceWith(ui.el('p', '图片加载失败；不生成识别结论。', 'muted')), { once: true });
            img.src = safe; load.replaceWith(img);
          }, { once: true });
          const link = ui.el('a', '查看图片 URL'); link.href = safe; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.referrerPolicy = 'no-referrer';
          card.append(load, link);
        } else { card.append(ui.el('p', '占位或不安全图片 URL，已拦截。', 'muted'), ui.el('code', ui.text(item.url))); }
        const observations = Array.isArray(item.observations) ? item.observations : [];
        card.append(ui.el('strong', '观察记录'));
        if (!observations.length) card.append(ui.el('p', '尚无观察记录；未执行视觉识别。', 'muted'));
        observations.forEach(observation => card.append(ui.el('p', values(observation))));
        grid.append(card);
      });
      section.append(grid); return section;
    }
    body.append(renderImages(self, '自有图片组'), renderImages(competitors, '竞品图片组'));
    const matrix = ui.el('section', undefined, 'panel');
    matrix.append(ui.el('h2', '卖点与图片对比矩阵'), ui.el('p', '当前 checklist 只记录总体状态。自有与竞品分组的具体观察、卖点差异尚未结构化提供。', 'muted'));
    matrix.append(items.length ? ui.table(['检查问题', '自有图组', '竞品图组', '卖点差异'], items.map(item => [ui.text(item.question), '—（分组证据待补）', '—（分组证据待补）', '—（待人工复核）'])) : ui.el('p', '暂无可对比的检查项。', 'table-empty'));
    body.append(matrix);
    const conversion = ui.el('section', undefined, 'panel');
    conversion.append(ui.el('h2', '广告转化承接检查'), ui.el('p', '保留机会评分、CVR、触发规则与 checklist 编号，便于核对检查来源。', 'muted'));
    conversion.append(data.conversion_diagnostics.length ? ui.table(
      ['关键词', '机会评分', 'CVR', '检查触发', '规则原因', '检查项引用'],
      data.conversion_diagnostics.map(row => [ui.text(row.keyword), ui.number(row.facts?.market_opportunity_score, 2), ui.percent(row.facts?.cvr), row.triggered === true ? '已触发' : row.triggered === false ? '未触发' : '—', ui.text(row.reason), strings(row.checklist_refs).join('、') || '—']),
    ) : ui.el('p', '暂无关键词转化诊断。', 'table-empty'));
    body.append(conversion); renderChecklist();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
