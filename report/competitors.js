(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const data = await ui.load('competitors.json');
    // Category features are a separate private artifact. A missing artifact
    // is shown as unavailable; it must not make the basic profile disappear.
    const category = globalThis.KWCC?.mode === 'live'
      ? await ui.load('category-features.json').catch(() => null)
      : null;
    const buyerChecklist = globalThis.KWCC?.mode === 'live'
      ? await ui.load('buyer-checklist.json').catch(() => null)
      : null;
    const textEvidence = globalThis.KWCC?.mode === 'live'
      ? await ui.load('text-evidence.json').catch(() => null)
      : null;
    if (!data || !Array.isArray(data.competitors) || data.competitors.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
      throw new Error('竞对档案结构无效：缺少 competitors 行数组。');
    }
    const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()) : [];
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
    // The current builder carries only self_asin; never borrow competitor fields
    // to fill the own-product column. Future explicit self_product fields can render.
    const selfFields = data.self_product && typeof data.self_product === 'object' && !Array.isArray(data.self_product) ? data.self_product : {};
    const own = { ...selfFields, asin: data.self_asin, role: 'self' };
    const products = [...(data.self_asin ? [own] : []), ...data.competitors.map(row => ({ ...row, role: 'competitor' }))];
    const imagesFor = row => Array.from(new Set([...strings(row.image_urls), ...[row.main_image_url].filter(value => typeof value === 'string')]));
    const validImages = row => imagesFor(row).map(imageURL).filter(Boolean);
    ui.setMetrics([
      ['自己 ASIN', ui.text(data.self_asin)], ['竞品', ui.number(data.competitors.length)],
      ['有效图片 URL', ui.number(products.reduce((sum, row) => sum + validImages(row).length, 0))],
      ['档案 Provider 调用', ui.number(data.provider_calls)],
    ]);
    body.replaceChildren();
    body.append(ui.el('p', '档案仅展示已有元数据。没有字段就显示 —；价格、销量、评分与自有商品详情未提供时不估算。图片不会自动请求，点击有效图片的加载按钮才会读取外部资源。', 'notice'));
    const meta = ui.el('section', undefined, 'panel');
    meta.append(ui.el('h2', '档案来源'), ui.el('p', `站点：${ui.text(data.marketplace)} · 快照：${ui.text(data.snapshot_version)} · Schema：${ui.text(data.schema_version)}`), ui.el('p', `缓存键：${ui.text(data.cache_key)}`, 'muted'));
    body.append(meta);
    const featurePanel = ui.el('section', undefined, 'panel');
    featurePanel.append(ui.el('h2', '类目特征表达'), ui.el('p', category ? `主核心词：${ui.text(category.primary_core_keyword)} · 站点：${ui.text(category.marketplace)} · 来源：${ui.text(category.source)}` : '类目特征报告尚未生成；没有 Provider 证据时不编造维度或占比。', category ? 'muted' : 'notice'));
    if (category && Array.isArray(category.features) && category.features.length) {
      const featurePercent = value => typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—';
      const featureRatio = (feature, key) => {
        const ratioKey = `${key}_ratio`;
        if (typeof feature[ratioKey] === 'number' && Number.isFinite(feature[ratioKey])) return feature[ratioKey];
        const points = feature[key];
        return typeof points === 'number' && Number.isFinite(points) ? points / 100 : null;
      };
      featurePanel.append(ui.table(['特征', '商品覆盖占比', '月销量占比', '说明', '来源序号'], category.features.map(feature => [
        ui.text(feature.name), featurePercent(featureRatio(feature, 'product_count_share')), featurePercent(featureRatio(feature, 'monthly_sales_share')),
        ui.text(feature.feature_description), ui.text(feature.source_index),
      ])));
      featurePanel.append(ui.el('p', category.module_status?.status === 'ready' ? '类目特征已完成结构校验；剔除与缺口仍需按确认版本参与正式判断。' : `类目特征状态：${ui.text(category.module_status?.reason, '待复核')}`, 'muted'));
    }
    body.append(featurePanel);
    if (buyerChecklist) {
      const panel = ui.el('section', undefined, 'panel');
      panel.append(ui.el('h2', '买家下单前决策清单'), ui.el('p', `状态：${ui.text(buyerChecklist.status)} · 版本：${ui.text(buyerChecklist.confirmation_version, '未确认')}`, buyerChecklist.status === 'ready' ? 'success-text' : 'notice'));
      const items = Array.isArray(buyerChecklist.items) ? buyerChecklist.items : [];
      panel.append(items.length ? ui.table(['要素', '买家关心点', '证据状态', '来源'], items.map(item => [ui.text(item.name), ui.text(item.why_buyer_cares), ui.text(item.evidence_status), ui.text(item.source_refs)])) : ui.el('p', '暂无有证据的清单项。', 'table-empty'));
      body.append(panel);
    }
    if (textEvidence) {
      const panel = ui.el('section', undefined, 'panel');
      const cells = Array.isArray(textEvidence.cells) ? textEvidence.cells : [];
      const mentioned = cells.filter(cell => cell.status === 'mentioned').length;
      panel.append(ui.el('h2', '标题 / 五点文字证据'), ui.el('p', `状态：${ui.text(textEvidence.status)} · 已提及 ${ui.number(mentioned)} / ${ui.number(cells.length)} 个特征-商品单元`, textEvidence.status === 'ready' ? 'success-text' : 'notice'));
      panel.append(cells.length ? ui.table(['特征', 'ASIN', '结果', '原文证据'], cells.slice(0, 80).map(cell => [ui.text(cell.feature_id), ui.text(cell.asin), ui.text(cell.status), ui.text((cell.quotes || []).map(quote => quote.quote).join('；'))])) : ui.el('p', '暂无文字证据。', 'table-empty'));
      body.append(panel);
    }
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar');
    const label = ui.el('label', '搜索 ASIN / 品牌 / 标题 ');
    const search = ui.el('input'); search.type = 'search'; search.placeholder = '输入 ASIN、品牌或标题'; label.append(search);
    const filters = ui.el('div', undefined, 'filters');
    filters.setAttribute('aria-label', '商品角色筛选');
    let selected = 'all';
    const buttons = [['all', '全部'], ['self', '自己'], ['competitor', '竞品']].map(([key, title]) => {
      const button = ui.el('button', title, 'filter'); button.type = 'button'; button.dataset.competitorFilter = key;
      button.addEventListener('click', () => { selected = key; render(); });
      filters.append(button); return [key, button];
    });
    const result = ui.el('div');
    const imageSection = ui.el('section', undefined, 'panel');
    const imageBody = ui.el('div', undefined, 'image-grid');
    imageSection.append(ui.el('h2', '主图与图片资料'), imageBody);
    const display = value => Array.isArray(value) ? strings(value).join('、') || '—' : ui.text(value);
    const monetary = (row, key) => typeof row[key] !== 'number' || !Number.isFinite(row[key]) ? '—' : /^[A-Z]{3}$/.test(row.currency_code || '') ? ui.money(row[key], row.currency_code) : `${ui.number(row[key], 2)}（币种待补）`;
    const fields = [
      ['身份', row => row.role === 'self' ? '自己' : '竞品'],
      ['品牌', row => ui.text(row.brand)], ['标题', row => ui.text(row.title)],
      ['价格', row => monetary(row, 'price')], ['月销量', row => ui.number(row.monthly_sales)],
      ['评分', row => ui.number(row.rating, 1)], ['评论数', row => ui.number(row.review_count)],
      ['类目', row => display(row.category)], ['BSR', row => ui.number(row.bsr)],
      ['数据来源', row => ui.text(row.source || data.snapshot_version)], ['采样时间', row => ui.text(row.sampled_at || data.snapshot_version)],
      ['核心关键词', row => display(row.core_keywords)], ['卖点', row => display(row.bullet_points)],
      ['有效图片 / 留底 URL', row => `${validImages(row).length} / ${imagesFor(row).length}`],
      ['未提供的比较字段', row => ['brand', 'title', 'price', 'monthly_sales', 'rating', 'review_count', 'category', 'bsr', 'bullet_points'].filter(key => row[key] == null || row[key] === '').join('、') || '—'],
      ['原始缺失字段', row => display(row.missing_fields)],
    ];
    function imageCard(row, raw, index) {
      const card = ui.el('figure', undefined, 'image-card');
      const safe = imageURL(raw);
      card.append(ui.el('figcaption', `${row.role === 'self' ? '自己' : '竞品'} ${ui.text(row.asin)} · 图片 ${index + 1}`));
      if (!safe) {
        card.append(ui.el('p', '无有效图片：占位或不安全 URL 已拦截。', 'table-empty'), ui.el('code', ui.text(raw)));
        return card;
      }
      const link = ui.el('a', '查看图片 URL'); link.href = safe; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.referrerPolicy = 'no-referrer';
      const load = ui.el('button', '加载图片（外部资源）', 'button secondary'); load.type = 'button';
      load.addEventListener('click', () => {
        const img = ui.el('img'); img.alt = `${ui.text(row.asin)} 的留底图片 ${index + 1}`; img.width = 240; img.height = 180;
        img.loading = 'lazy'; img.referrerPolicy = 'no-referrer'; img.decoding = 'async';
        img.addEventListener('error', () => img.replaceWith(ui.el('p', '图片加载失败；URL 元数据仍保留。', 'muted')), { once: true });
        img.src = safe; load.replaceWith(img);
      }, { once: true });
      card.append(load, link); return card;
    }
    function render() {
      const query = search.value.trim().toLocaleLowerCase();
      const visible = products.filter(row => (selected === 'all' || row.role === selected) && (!query || [row.asin, row.brand, row.title].some(value => typeof value === 'string' && value.toLocaleLowerCase().includes(query))));
      buttons.forEach(([key, button]) => { button.className = key === selected ? 'filter active' : 'filter'; button.setAttribute('aria-pressed', String(key === selected)); });
      result.replaceChildren(visible.length ? ui.table(['比较字段', ...visible.map(row => `${row.role === 'self' ? '自己' : '竞品'} · ${ui.text(row.asin)}`)], fields.map(([title, format]) => [title, ...visible.map(format)])) : ui.el('p', products.length ? '没有符合筛选条件的商品。' : '暂无自有商品或竞品档案。', 'table-empty'));
      imageBody.replaceChildren();
      const count = visible.reduce((sum, row) => sum + validImages(row).length, 0);
      if (!count) imageBody.append(ui.el('p', '当前资料无有效图片可展示；未加载 example.* 占位地址。', 'notice'));
      for (const row of visible) {
        const urls = imagesFor(row);
        if (!urls.length) imageBody.append(ui.el('p', `${row.role === 'self' ? '自己' : '竞品'} ${ui.text(row.asin)}：尚未提供图片资料。`, 'muted'));
        urls.forEach((raw, index) => imageBody.append(imageCard(row, raw, index)));
      }
      status.textContent = `${ui.statusPrefix(data)} · ${globalThis.KWCC?.mode === 'live' ? '私有报告' : 'Demo'} · 显示 ${ui.number(visible.length)} / ${ui.number(products.length)} 个商品 · 来源 competitors.json · 本页未发起 Provider 请求`;
    }
    search.addEventListener('input', render);
    toolbar.append(label, filters); panel.append(toolbar, result); body.append(panel, imageSection);
    render();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
