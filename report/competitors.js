(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const lifecycleToken = ui.operationToken();
    let data = null, categoryResult = null, buyerChecklistResult = null, textEvidenceResult = null;
    let category = null, buyerChecklist = null, textEvidence = null, task = null;
    let selfFields = null, own = null, ownAsin = null, products = [], comparisonChoices = [], seenComparisonAsins = new Set();
    let selected = 'all', search = null, comparisonSelect = null;
    let checklistControls = [], checklistButton = null, checklistResult = null, checklistRevision = 0;
    let taskId = null, runId = null;
    ui.onInvalidate(() => {
      checklistRevision++;
      data = null; categoryResult = null; buyerChecklistResult = null; textEvidenceResult = null;
      category = null; buyerChecklist = null; textEvidence = null; task = null;
      selfFields = null; own = null; ownAsin = null; products = []; comparisonChoices = []; seenComparisonAsins.clear();
      taskId = null; runId = null; selected = 'all';
      if (search) search.value = '';
      if (comparisonSelect) comparisonSelect.replaceChildren();
      search = null; comparisonSelect = null;
      for (const control of checklistControls) {
        control.input.checked = false; control.input.value = ''; control.input.disabled = true;
        control.reason.value = 'not_relevant'; control.reason.disabled = true;
        control.note.value = ''; control.note.disabled = true;
      }
      checklistControls = [];
      if (checklistButton) checklistButton.disabled = true;
      if (checklistResult) checklistResult.textContent = '';
      checklistButton = null; checklistResult = null;
    });
    const loadedData = await ui.load('competitors.json');
    ui.assertOperation(lifecycleToken);
    data = loadedData;
    const live = globalThis.KWCC?.mode === 'live';
    // These are independent private artifacts. Only an explicit not-generated
    // or module-failed result is an expected data state. Auth, session,
    // authorization, transport, and schema errors must reach showError rather
    // than being disguised as an empty report.
    async function readOptional(name) {
      if (!live) return { data: null, state: 'not_applicable' };
      try {
        const artifact = await ui.load(name);
        ui.assertOperation(lifecycleToken);
        return { data: artifact, state: null, reason: null };
      }
      catch (error) {
        ui.assertOperation(lifecycleToken);
        if (!['REPORT_NOT_GENERATED', 'REPORT_MODULE_FAILED'].includes(error?.code)) throw error;
        const state = error.code === 'REPORT_MODULE_FAILED' ? 'failed' : 'not_generated';
        const reason = error.details?.module_state?.reason;
        return { data: null, state, reason: typeof reason === 'string' && /^[a-z0-9_]{1,80}$/i.test(reason) ? reason : null };
      }
    }
    const loadedCategoryResult = await readOptional('category-features.json');
    ui.assertOperation(lifecycleToken);
    categoryResult = loadedCategoryResult;
    const loadedBuyerChecklistResult = await readOptional('buyer-checklist.json');
    ui.assertOperation(lifecycleToken);
    buyerChecklistResult = loadedBuyerChecklistResult;
    const loadedTextEvidenceResult = await readOptional('text-evidence.json');
    ui.assertOperation(lifecycleToken);
    textEvidenceResult = loadedTextEvidenceResult;
    category = categoryResult.data;
    buyerChecklist = buyerChecklistResult.data;
    textEvidence = textEvidenceResult.data;
    const reportParams = new URL(location.href).searchParams;
    taskId = reportParams.get('task');
    runId = reportParams.get('run');
    // Task lookup is required for a trustworthy checklist confirmation. Never
    // turn an authorization/session/API failure into a vague “task missing”.
    const fetchedTask = live && category ? await globalThis.KWCC.tasks.get(taskId) : null;
    ui.assertOperation(lifecycleToken);
    task = fetchedTask;
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
    selfFields = data.self_product && typeof data.self_product === 'object' && !Array.isArray(data.self_product) ? data.self_product : {};
    own = { ...selfFields, asin: data.self_asin, role: 'self' };
    products = [...(data.self_asin ? [own] : []), ...data.competitors.map(row => ({ ...row, role: 'competitor' }))];
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
    function optionalState(result, artifact) {
      if (result.state) return { state: result.state, reason: result.reason };
      const declared = artifact?._module_state?.status || artifact?.module_status?.status || artifact?.status;
      const knownStates = ['ready', 'partial', 'failed', 'not_generated', 'not_applicable'];
      return { state: knownStates.includes(declared) ? declared : 'unknown', reason: artifact?._module_state?.reason || artifact?.module_status?.reason || null };
    }
    function optionalStateText(result, artifact) {
      const { state, reason } = optionalState(result, artifact);
      const labels = { ready: '已生成', partial: '部分数据', failed: '生成失败', not_generated: '尚未生成', unknown: '已返回但状态未确认', not_applicable: '不适用' };
      const safeReason = typeof reason === 'string' && /^[a-z0-9_]{1,80}$/i.test(reason) ? ` · 原因：${reason}` : '';
      return `${labels[state] || labels.unknown}${safeReason}`;
    }
    const featurePanel = ui.el('section', undefined, 'panel');
    featurePanel.append(ui.el('h2', '类目特征表达'), ui.el('p', category ? `主核心词：${ui.text(category.primary_core_keyword)} · 站点：${ui.text(category.marketplace)} · 来源：${ui.text(category.source)} · ${optionalStateText(categoryResult, category)}` : `类目特征报告${optionalStateText(categoryResult, null)}；没有 Provider 证据时不编造维度或占比。`, category ? 'muted' : 'notice'));
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
    if (live && category && Array.isArray(category.features) && category.features.length) {
      const featureId = feature => typeof feature?.feature_id === 'string' ? feature.feature_id.trim()
        : typeof feature?.element_id === 'string' ? feature.element_id.trim() : '';
      const reviewItems = [];
      const seenFeatureIds = new Set();
      for (const feature of category.features) {
        const id = featureId(feature);
        const rawName = typeof feature?.name === 'string' ? feature.name
          : typeof feature?.element_name === 'string' ? feature.element_name : '';
        const name = rawName.trim();
        if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(id) || !name || seenFeatureIds.has(id)) continue;
        seenFeatureIds.add(id);
        reviewItems.push({ id, name });
        if (reviewItems.length === 7) break;
      }
      const review = ui.el('section', undefined, 'panel');
      review.append(ui.el('h2', '确认买家决策清单并重跑'), ui.el('p', '首次真实报告先生成草稿；请核对系统按顺序选出的特征。只有确认后，Worker 才会把买家清单和文字证据标记为正式证据。', 'notice'));
      const isUuid = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
      if (!reviewItems.length || !task || !task.input_file_hash || !isUuid(taskId) || !isUuid(runId)) {
        review.append(ui.el('p', '当前报告缺少可确认的类目特征或任务绑定，暂不能确认；请先生成类目特征报告。', 'table-empty'));
      } else {
        const list = ui.el('div', undefined, 'checklist-review');
        const controls = reviewItems.map(item => {
          const label = ui.el('label', undefined, 'check-row');
          const input = document.createElement('input'); input.type = 'checkbox'; input.value = item.id; input.checked = true;
          label.append(input, ui.el('span', item.name + ' · ' + item.id)); list.append(label);
          const exclusion = ui.el('div', undefined, 'check-row-exclusion');
          exclusion.hidden = true;
          const reason = document.createElement('select');
          for (const [value, text] of [['not_relevant', '与本商品无关'], ['not_applicable', '本商品不适用'], ['already_covered', '已由其他特征覆盖'], ['unverified', '证据不足，暂不确认'], ['other', '其他原因']]) {
            const option = document.createElement('option'); option.value = value; option.textContent = text; reason.append(option);
          }
          const note = ui.el('input'); note.type = 'text'; note.maxLength = 300; note.placeholder = '排除说明（可选；选择“其他原因”时必填）';
          input.addEventListener('change', () => {
            if (ui.operationIsActive(lifecycleToken)) exclusion.hidden = input.checked;
          });
          exclusion.append(reason, note); list.append(exclusion);
          return { input, reason, note };
        });
        checklistControls = controls;
        const action = ui.el('div', undefined, 'toolbar');
        const button = ui.el('button', '确认清单并重新分析', 'button primary'); button.type = 'button';
        const result = ui.el('p', '确认后会创建新的 run，旧报告保持不变。', 'muted'); result.setAttribute('role', 'status');
        checklistButton = button; checklistResult = result;
        button.addEventListener('click', async () => {
          if (!ui.operationIsActive(lifecycleToken) || button.disabled) return;
          const operationToken = ui.operationToken();
          const attempt = ++checklistRevision;
          const isCurrentAttempt = () => attempt === checklistRevision
            && ui.operationIsActive(lifecycleToken) && ui.operationIsActive(operationToken);
          const selected = controls.filter(control => control.input.checked).map(control => control.input.value);
          const excludedItems = controls.filter(control => !control.input.checked).map(control => ({
            feature_id: control.input.value, reason_code: control.reason.value, ...(control.note.value.trim() ? { note: control.note.value.trim() } : {}),
          }));
          if (!selected.length) { result.textContent = '至少保留 1 个已确认特征；其余项目需逐项说明排除原因。'; return; }
          if (excludedItems.some(item => item.reason_code === 'other' && !item.note)) { result.textContent = '选择“其他原因”时必须填写说明。'; return; }
          button.disabled = true; result.textContent = '正在保存确认并创建新 run…';
          try {
            const version = 'checklist-v2-' + Date.now() + '-' + crypto.randomUUID().slice(0, 8);
            const nextRunId = crypto.randomUUID();
            if (!isCurrentAttempt()) return;
            const saved = await globalThis.KWCC.tasks.confirmChecklistAndRerun({
              taskId, previousRunId: runId, runId: nextRunId, version,
              selfAsin: task.self_asin, items: selected, inputHash: task.input_file_hash,
              candidateSnapshot: category, sourceRunId: runId, excludedItems,
            });
            if (!isCurrentAttempt()) return;
            result.textContent = `已确认版本 ${saved.confirmation_version}，新 run ${saved.run_id} 已进入队列；请到任务列表查看进度。`;
          } catch (error) {
            if (!isCurrentAttempt()) return;
            result.textContent = error.message || '确认失败；未确认重跑结果，请刷新任务列表。'; button.disabled = false;
          }
        });
        action.append(button); review.append(list, action, result);
      }
      body.append(review);
    }
    if (live || buyerChecklist) {
      const panel = ui.el('section', undefined, 'panel');
      panel.append(ui.el('h2', '买家下单前决策清单'));
      if (buyerChecklist) {
        panel.append(ui.el('p', `状态：${ui.text(buyerChecklist.status)} · 版本：${ui.text(buyerChecklist.confirmation_version, '未确认')} · ${optionalStateText(buyerChecklistResult, buyerChecklist)}`, buyerChecklist.status === 'ready' ? 'success-text' : 'notice'));
        const items = Array.isArray(buyerChecklist.items) ? buyerChecklist.items : [];
        panel.append(items.length ? ui.table(['要素', '买家关心点', '证据状态', '来源'], items.map(item => [ui.text(item.name), ui.text(item.why_buyer_cares), ui.text(item.evidence_status), ui.text(item.source_refs)])) : ui.el('p', '暂无有证据的清单项。', 'table-empty'));
        const excluded = Array.isArray(buyerChecklist.excluded_items) ? buyerChecklist.excluded_items : [];
        if (excluded.length) panel.append(ui.el('h3', '已排除项目与原因'), ui.table(['特征 ID', '排除原因', '补充说明'], excluded.map(item => [ui.text(item.feature_id), ui.text(item.reason_code), ui.text(item.note)])));
      } else panel.append(ui.el('p', `买家清单${optionalStateText(buyerChecklistResult, null)}；不会把缺少的数据解释成“无买家需求”。`, 'notice'));
      body.append(panel);
    }
    if (live || textEvidence) {
      const panel = ui.el('section', undefined, 'panel');
      panel.append(ui.el('h2', '标题 / 五点文字证据'));
      if (textEvidence) {
        const cells = Array.isArray(textEvidence.cells) ? textEvidence.cells : [];
        const mentioned = cells.filter(cell => cell.status === 'mentioned').length;
        panel.append(ui.el('p', `状态：${ui.text(textEvidence.status)} · ${optionalStateText(textEvidenceResult, textEvidence)} · 已提及 ${ui.number(mentioned)} / ${ui.number(cells.length)} 个特征-商品单元`, textEvidence.status === 'ready' ? 'success-text' : 'notice'));
        panel.append(cells.length ? ui.table(['特征', 'ASIN', '结果', '原文证据'], cells.map(cell => [ui.text(cell.feature_id), ui.text(cell.asin), ui.text(cell.status), ui.text((cell.quotes || []).map(quote => quote.quote).join('；'))])) : ui.el('p', '暂无文字证据。', 'table-empty'));
      } else panel.append(ui.el('p', `标题 / 五点文字证据${optionalStateText(textEvidenceResult, null)}；不会把缺少的数据解释成“商品没有写到该特征”。`, 'notice'));
      body.append(panel);
    }
    const display = value => Array.isArray(value) ? strings(value).join('、') || '—' : ui.text(value);
    const monetary = (row, key) => typeof row[key] !== 'number' || !Number.isFinite(row[key]) ? '—' : /^[A-Z]{3}$/.test(row.currency_code || '') ? ui.money(row[key], row.currency_code) : `${ui.number(row[key], 2)}（币种待补）`;
    const validAsin = value => typeof value === 'string' && /^[A-Z0-9]{10}$/i.test(value.trim());
    const normalizedAsin = value => validAsin(value) ? value.trim().toUpperCase() : '';
    ownAsin = normalizedAsin(data.self_asin);
    for (const row of data.competitors) {
      const asin = normalizedAsin(row.asin);
      if (!asin || asin === ownAsin || seenComparisonAsins.has(asin)) continue;
      seenComparisonAsins.add(asin);
      comparisonChoices.push({ asin, row });
    }
    const comparisonPanel = ui.el('section', undefined, 'panel competitor-comparison');
    comparisonPanel.append(ui.el('h2', '自己与单个竞品并排比较'), ui.el('p', '只使用当前报告和已生成的类目、文字证据。缺失或不可比的字段保留为未提供，不推算商品属性或差距。', 'muted'));
    const comparisonLabel = ui.el('label', '选择一个竞品 ');
    comparisonSelect = document.createElement('select');
    comparisonSelect.setAttribute('aria-label', '选择一个竞品进行并排比较');
    const comparisonBody = ui.el('div', undefined, 'competitor-comparison-body');
    if (comparisonChoices.length) {
      comparisonChoices.forEach(({ asin }) => {
        const option = document.createElement('option'); option.value = asin; option.textContent = asin;
        comparisonSelect.append(option);
      });
      comparisonSelect.value = comparisonChoices[0].asin;
      comparisonLabel.append(comparisonSelect);
      comparisonPanel.append(comparisonLabel, comparisonBody);
    } else {
      comparisonSelect.disabled = true;
      comparisonLabel.append(comparisonSelect);
      comparisonPanel.append(comparisonLabel, ui.el('p', '没有有效的竞品 ASIN，当前无法选择并排比较对象。', 'table-empty'));
    }
    const productFact = (row, key) => {
      if (!row) return '—';
      if (key === 'category' || key === 'core_keywords' || key === 'bullet_points') return display(row[key]);
      if (['price', 'monthly_sales', 'rating', 'review_count', 'bsr'].includes(key)) {
        if (typeof row[key] !== 'number' || !Number.isFinite(row[key])) return '—';
        if (key === 'price') return monetary(row, key);
        if (key === 'rating') return row[key] >= 0 && row[key] <= 5 ? ui.number(row[key], 1) : '—';
        if (key === 'monthly_sales' || key === 'review_count') return Number.isInteger(row[key]) && row[key] >= 0 ? ui.number(row[key]) : '—';
        return Number.isInteger(row[key]) && row[key] > 0 ? ui.number(row[key]) : '—';
      }
      return typeof row[key] === 'string' && row[key].trim() ? ui.text(row[key]) : '—';
    };
    const safeMetric = (comparison, metricKey, selfKey, competitor, expectedUnit) => {
      const metric = comparison?.[metricKey];
      const selfValue = selfFields[selfKey];
      const competitorValue = competitor?.[selfKey];
      if (!metric || metric.status !== 'valid' || metric.unit !== expectedUnit
          || typeof metric.value !== 'number' || !Number.isFinite(metric.value)
          || typeof selfValue !== 'number' || !Number.isFinite(selfValue)
          || typeof competitorValue !== 'number' || !Number.isFinite(competitorValue)
          || metric.self_value !== selfValue || metric.competitor_value !== competitorValue) return null;
      if (metricKey === 'price_relative_difference') {
        if (metric.currency_code !== selfFields.currency_code || metric.currency_code !== competitor.currency_code
            || !/^[A-Z]{3}$/.test(metric.currency_code || '')
            || metric.price_type !== selfFields.price_type || metric.price_type !== competitor.price_type
            || !metric.price_type || competitorValue <= 0
            || metric.denominator !== competitorValue
            || metric.value !== (selfValue - competitorValue) / competitorValue) return null;
      } else if (metricKey === 'rating_absolute_difference') {
        if (metric.value !== Math.abs(selfValue - competitorValue) || metric.value < 0 || metric.value > 5
            || !['self_higher', 'competitor_higher', 'equal'].includes(metric.direction)) return null;
      } else if (metricKey === 'review_count_relative_difference') {
        if (!Number.isInteger(selfValue) || selfValue < 0 || !Number.isInteger(competitorValue) || competitorValue <= 0
            || metric.denominator !== competitorValue
            || metric.value !== (selfValue - competitorValue) / competitorValue) return null;
      } else if (metricKey === 'bsr_difference') {
        if (!Number.isInteger(selfValue) || selfValue <= 0 || !Number.isInteger(competitorValue) || competitorValue <= 0
            || metric.value !== selfValue - competitorValue || metric.ordering !== 'lower_is_better') return null;
      }
      return metric;
    };
    const unavailableMetric = metric => {
      const reason = typeof metric?.reason === 'string' && /^[a-z0-9_]{1,80}$/i.test(metric.reason) ? metric.reason : '';
      return `不可比较${reason ? ` · ${ui.text(reason)}` : ' · 缺少可核对证据'}`;
    };
    const comparisonGap = (comparison, key, selfKey, competitor, unit) => {
      const metric = safeMetric(comparison, key, selfKey, competitor, unit);
      if (!metric) return unavailableMetric(comparison?.[key]);
      if (unit === 'ratio') return `${metric.value > 0 ? '+' : ''}${ui.number(metric.value * 100, 1)}%`;
      if (unit === 'rating_points') {
        const direction = metric.direction === 'self_higher' ? '自己较高' : metric.direction === 'competitor_higher' ? '竞品较高' : '相同';
        return `${ui.number(metric.value, 1)} 分 · ${direction}`;
      }
      return `${metric.value > 0 ? '+' : ''}${ui.number(metric.value)} · 自然类目排名越小越靠前`;
    };
    const evidenceCell = (featureId, asin) => {
      const cells = Array.isArray(textEvidence?.cells) ? textEvidence.cells : [];
      const matches = cells.filter(cell => normalizedAsin(cell?.asin) === asin && cell?.feature_id === featureId);
      if (!matches.length) return '文字证据未返回';
      const cell = matches[0];
      const statusLabel = ({ mentioned: '已提及', not_mentioned: '未提及', unknown: '未知', source_missing: '来源缺失' })[cell.status] || '状态未确认';
      const quotes = Array.isArray(cell.quotes) ? cell.quotes.map(item => item?.quote).filter(value => typeof value === 'string' && value.trim()) : [];
      return quotes.length ? `${statusLabel} · ${ui.text(quotes.join('；'))}` : statusLabel;
    };
    function renderComparison() {
      if (!ui.operationIsActive(lifecycleToken)) return;
      const selectedAsin = normalizedAsin(comparisonSelect.value);
      const selectedChoice = comparisonChoices.find(choice => choice.asin === selectedAsin);
      if (!selectedChoice) {
        comparisonBody.replaceChildren(ui.el('p', '请选择一个有效竞品；当前没有可呈现的比较对象。', 'table-empty'));
        return;
      }
      const competitor = selectedChoice.row;
      const comparison = (Array.isArray(data.product_comparisons) ? data.product_comparisons : [])
        .find(item => normalizedAsin(item?.competitor_asin) === selectedAsin);
      const factRows = [
        ['品牌', 'brand'], ['标题', 'title'], ['价格', 'price'], ['月销量', 'monthly_sales'],
        ['评分', 'rating'], ['评论数', 'review_count'], ['类目', 'category'], ['BSR', 'bsr'],
        ['核心关键词', 'core_keywords'], ['卖点', 'bullet_points'],
      ];
      const gapRows = [
        ['价格差距（相对竞品）', 'price_relative_difference', 'price', 'ratio'],
        ['评分差距', 'rating_absolute_difference', 'rating', 'rating_points'],
        ['评论数差距（相对竞品）', 'review_count_relative_difference', 'review_count', 'ratio'],
        ['BSR 差距', 'bsr_difference', 'bsr', 'rank_positions'],
      ];
      comparisonBody.replaceChildren(
        ui.el('p', `比较对象：${ui.text(selectedAsin)} · 仅比较同一份报告中已返回的字段。`, 'muted'),
        ui.table(['商品事实', `自己 · ${ownAsin || 'ASIN 未提供'}`, `竞品 · ${selectedAsin}`], factRows.map(([label, key]) => [label, productFact(selfFields, key), productFact(competitor, key)])),
        ui.el('h3', '报告中的差距结论'),
        ui.table(['指标', '差距（仅可比时显示）'], gapRows.map(([label, key, field, unit]) => [label, comparisonGap(comparison, key, field, competitor, unit)])),
      );
      const featureRows = [];
      const features = Array.isArray(category?.features) ? category.features : [];
      const seenFeatureIds = new Set();
      for (const feature of features) {
        const rawId = typeof feature?.feature_id === 'string' ? feature.feature_id.trim()
          : typeof feature?.element_id === 'string' ? feature.element_id.trim() : '';
        const name = typeof feature?.name === 'string' ? feature.name.trim()
          : typeof feature?.element_name === 'string' ? feature.element_name.trim() : '';
        if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(rawId) || !name || seenFeatureIds.has(rawId)) continue;
        seenFeatureIds.add(rawId);
        featureRows.push([ui.text(name), ownAsin ? evidenceCell(rawId, ownAsin) : '自己的 ASIN 未提供', evidenceCell(rawId, selectedAsin)]);
      }
      comparisonBody.append(ui.el('h3', '同维度标题 / 五点表达'), featureRows.length
        ? ui.table(['买家决策特征', `自己 · ${ownAsin || 'ASIN 未提供'}`, `竞品 · ${selectedAsin}`], featureRows)
        : ui.el('p', '类目特征维度未提供；无法建立同维度表达对照。', 'table-empty'));
    }
    if (comparisonChoices.length) {
      comparisonSelect.addEventListener('change', renderComparison);
      renderComparison();
    }
    body.append(comparisonPanel);
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar');
    const label = ui.el('label', '搜索 ASIN / 品牌 / 标题 ');
    search = ui.el('input'); search.type = 'search'; search.placeholder = '输入 ASIN、品牌或标题'; label.append(search);
    const filters = ui.el('div', undefined, 'filters');
    filters.setAttribute('aria-label', '商品角色筛选');
    const buttons = [['all', '全部'], ['self', '自己'], ['competitor', '竞品']].map(([key, title]) => {
      const button = ui.el('button', title, 'filter'); button.type = 'button'; button.dataset.competitorFilter = key;
      button.addEventListener('click', () => {
        if (!ui.operationIsActive(lifecycleToken)) return;
        selected = key; render();
      });
      filters.append(button); return [key, button];
    });
    const result = ui.el('div');
    const imageSection = ui.el('section', undefined, 'panel');
    const imageBody = ui.el('div', undefined, 'image-grid');
    imageSection.append(ui.el('h2', '主图与图片资料'), imageBody);
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
        if (!ui.operationIsActive(lifecycleToken)) return;
        const img = ui.el('img'); img.alt = `${ui.text(row.asin)} 的留底图片 ${index + 1}`; img.width = 240; img.height = 180;
        img.loading = 'lazy'; img.referrerPolicy = 'no-referrer'; img.decoding = 'async';
        img.addEventListener('error', () => {
          if (ui.operationIsActive(lifecycleToken)) img.replaceWith(ui.el('p', '图片加载失败；URL 元数据仍保留。', 'muted'));
        }, { once: true });
        img.src = safe; load.replaceWith(img);
      }, { once: true });
      card.append(load, link); return card;
    }
    function render() {
      if (!ui.operationIsActive(lifecycleToken)) return;
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
      const auxiliary = live ? [
        ['类目特征', categoryResult, category], ['买家清单', buyerChecklistResult, buyerChecklist], ['文字证据', textEvidenceResult, textEvidence],
      ] : [];
      const incomplete = auxiliary.filter(([, result, artifact]) => optionalState(result, artifact).state !== 'ready');
      const reportState = incomplete.length
        ? `部分数据 · ${incomplete.map(([label, result, artifact]) => `${label}${optionalStateText(result, artifact)}`).join('；')}`
        : `${ui.statusPrefix(data)}${live ? ' · 3 项附属报告完整' : ''}`;
      status.textContent = `${reportState} · ${live ? '私有报告' : 'Demo'} · 显示 ${ui.number(visible.length)} / ${ui.number(products.length)} 个商品 · 来源 competitors.json · 本页未发起 Provider 请求`;
    }
    search.addEventListener('input', () => {
      if (ui.operationIsActive(lifecycleToken)) render();
    });
    toolbar.append(label, filters); panel.append(toolbar, result); body.append(panel, imageSection);
    render();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
