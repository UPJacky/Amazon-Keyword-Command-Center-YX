(async function () {
  'use strict';
  const ui = window.ReportUI;
  const body = document.querySelector('#module-body');
  const status = document.querySelector('#module-status');
  try {
    if (!ui || (await ui.ready) !== true) return;
    const lifecycleToken = ui.operationToken();
    const moduleName = 'negative-keywords.json';
    const groups = [
      ['exact_negative', '精准否定候选', 'exact_negative_candidate', 'badge red'],
      ['phrase_negative', '词组否定候选', 'phrase_negative_candidate', 'badge orange'],
      ['cautious', '慎否', 'cautious', 'badge yellow'],
      ['pending_confirmation', '待确认', 'pending_confirmation', 'badge gray'],
      ['low_cvr_high_spend', '低 CVR 高花费复核', 'low_cvr_high_spend', 'badge orange'],
      ['protected_converted', '已有订单保护', 'protected_converted', 'badge green'],
    ];
    const groupKeys = new Set(['exact_negative', 'phrase_negative']);
    const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    const stable = value => {
      if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
      if (typeof value === 'number') {
        if (!Number.isFinite(value)) throw new Error('报告证据包含无效数字');
        return value;
      }
      if (Array.isArray(value)) return value.map(stable);
      if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort()
        .filter(key => value[key] !== undefined).map(key => [key, stable(value[key])]));
      throw new Error('报告结构无法生成稳定版本');
    };
    async function hashJSON(value) {
      if (!globalThis.crypto?.subtle || typeof globalThis.TextEncoder !== 'function') return null;
      const bytes = new TextEncoder().encode(JSON.stringify(stable(value)));
      const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    }
    const normalize = value => typeof value === 'string' ? value.normalize('NFC').trim().toLowerCase().split(/\s+/).filter(Boolean).join(' ') : '';
    const candidateId = (group, keyword) => `${group}\u0000${normalize(keyword)}`;
    function validateReport(input) {
      if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('否词报告结构无效');
      // Older module03 artifacts predate these diagnostic buckets.
      for (const key of ['low_cvr_high_spend', 'protected_converted']) if (input[key] === undefined) input[key] = [];
      if (groups.some(([key]) => !Array.isArray(input[key])
        || input[key].some(row => !row || typeof row !== 'object' || Array.isArray(row))))
        throw new Error('否词报告结构无效：各分类必须为行数组。');
      return input;
    }
    const loadedReport = await ui.load(moduleName);
    ui.assertOperation(lifecycleToken);
    let rawData = loadedReport;
    const missingBuckets = new Set(['low_cvr_high_spend', 'protected_converted']
      .filter(key => !rawData || !Object.hasOwn(rawData, key)));
    let data = validateReport(rawData);
    let entries = groups.flatMap(([key, label, expected, color]) => data[key].map(row => ({ key, label, expected, color, row })));
    const reasons = {
      zero_orders_and_hard_stop_boundary: '零订单，达到配置中的点击与花费止损边界',
      zero_orders_with_preliminary_evidence: '零订单，已有初步点击证据；仍需核查词组影响范围',
      evidence_insufficient: '点击证据不足，慎否并继续观察',
      no_click_evidence: '尚无点击证据，待确认',
      required_ad_fields_missing: '广告必需字段缺失，待补数据',
      required_ad_fields_invalid: '广告字段不是有效的非负有限数值，待修正数据',
      exact_conflicts_with_protected_keyword: '与已有订单或保护关键词冲突，待确认',
      phrase_conflicts_with_protected_keyword: '词组否定会覆盖保护关键词，待确认',
      duplicate_keyword_evidence: '同一关键词存在多条事实，待核对后再操作',
      sales_data_not_judged: '销售额数据质量异常，待核对后再操作',
      invalid_keyword_text: '关键词文本包含无效字符，待修正后再操作',
    };
    const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()) : [];
    const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
    const criticalFields = ['clicks', 'spend', 'orders'];
    const protectiveReasons = new Set([
      'required_ad_fields_missing', 'required_ad_fields_invalid', 'relevance_unknown', 'related_relevance_protection',
      'evidence_insufficient', 'no_click_evidence', 'existing_orders_protected',
      'sales_data_not_judged', 'invalid_keyword_text',
      'exact_conflicts_with_protected_keyword', 'phrase_conflicts_with_protected_keyword', 'duplicate_keyword_evidence',
    ]);
    let negativeRule = data.negative_rule && typeof data.negative_rule === 'object' ? data.negative_rule : {};
    const ruleMetric = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
    const exportThresholdsValid = ruleMetric(negativeRule.zero_order_clicks_threshold)
      && ruleMetric(negativeRule.zero_order_spend_threshold)
      && ruleMetric(negativeRule.preliminary_clicks_threshold)
      && (negativeRule.low_cvr_threshold === null || (ruleMetric(negativeRule.low_cvr_threshold)
        && negativeRule.low_cvr_threshold <= 1))
      && negativeRule.cvr_definition === 'orders_divided_by_clicks; zero_clicks_unknown';
    const missingCriticalEvidence = row => criticalFields.some(field => !finite(row[field]))
      || (row.missing_fields !== undefined && (!Array.isArray(row.missing_fields)
        || row.missing_fields.some(field => criticalFields.includes(field))))
      || (Array.isArray(row.invalid_fields) && row.invalid_fields.includes('sales'))
      || row.data_quality?.status === 'not_judged'
      || (typeof row.sales === 'number' && row.sales < 0);
    let protectedKeywords = new Set(entries.filter(entry => {
      const row = entry.row;
      return entry.key === 'low_cvr_high_spend'
        || row.negative_status !== entry.expected || protectiveReasons.has(row.reason)
        || row.relevance !== 'unrelated' || (finite(row.orders) && row.orders > 0) || missingCriticalEvidence(row);
    }).map(entry => normalize(entry.row.keyword)).filter(Boolean));
    const phraseIsContained = (phrase, protectedTerm) => {
      const needle = normalize(phrase), term = normalize(protectedTerm);
      if (!needle || !term) return false;
      const contains = (candidate, scope) => {
        let start = scope.indexOf(candidate);
        while (start >= 0) {
          const end = start + candidate.length;
          const left = start === 0 || !/[A-Za-z0-9]/.test(scope[start - 1]);
          const right = end === scope.length || !/[A-Za-z0-9]/.test(scope[end]);
          if (left && right) return true;
          start = scope.indexOf(candidate, start + 1);
        }
        return false;
      };
      // A phrase negative can overlap a protected term in either direction:
      // the candidate may contain the protected term, or be contained by it.
      return contains(needle, term) || contains(term, needle);
    };
    let counts = new Map();
    entries.forEach(({ row }) => { const key = normalize(row.keyword); counts.set(key, (counts.get(key) || 0) + 1); });
    let coverageMatchesQualification = true;
    const eligible = entry => groupKeys.has(entry.key)
      && exportThresholdsValid
      && coverageMatchesQualification
      && entry.row.export_eligible === true
      && entry.row.negative_status === entry.expected
      && normalize(entry.row.keyword) && !protectedKeywords.has(normalize(entry.row.keyword))
      && (entry.key !== 'phrase_negative' || ![...protectedKeywords].some(term => phraseIsContained(entry.row.keyword, term)))
      && counts.get(normalize(entry.row.keyword)) === 1
      && !/[\r\n\u0000-\u001f\u007f\u2028\u2029]/.test(entry.row.keyword)
      && (entry.row.conflict_keywords === undefined || (Array.isArray(entry.row.conflict_keywords) && entry.row.conflict_keywords.length === 0))
      && (entry.row.phrase_conflict_keywords === undefined || (Array.isArray(entry.row.phrase_conflict_keywords) && entry.row.phrase_conflict_keywords.length === 0))
      && entry.row.relevance === 'unrelated' && !String(entry.row.reason || '').includes('conflict')
      && entry.row.orders === 0 && finite(entry.row.clicks) && entry.row.clicks > 0 && finite(entry.row.spend)
      && (entry.key === 'exact_negative'
        ? entry.row.clicks >= negativeRule.zero_order_clicks_threshold
          && entry.row.spend >= negativeRule.zero_order_spend_threshold
        : entry.row.clicks >= negativeRule.preliminary_clicks_threshold);

    const params = new URL(window.location.href).searchParams;
    const taskId = (params.get('task') || '').toLowerCase();
    const runId = (params.get('run') || '').toLowerCase();
    const live = globalThis.KWCC?.mode === 'live';
    const taskApi = globalThis.KWCC?.tasks;
    let task = null, operationsReady = false, dataChanged = false;
    let selected = new Set(), confirmedIds = new Set(), confirmation = null;
    let actionRevision = 0;
    let roots = new Map(), rootRows = [], textOutputs = [], search = null, selectedGroup = 'all';
    ui.onInvalidate(() => {
      invalidateActions();
      selected.clear(); confirmedIds.clear(); confirmation = null; task = null;
      operationsReady = false; dataChanged = true; coverageMatchesQualification = false;
      rawData = null; data = null; entries = [];
      protectedKeywords.clear(); counts.clear(); missingBuckets.clear(); roots.clear(); rootRows = [];
      negativeRule = {};
      for (const output of textOutputs) {
        output.area.value = ''; output.heading.textContent = ''; output.copy.disabled = true;
      }
      textOutputs = [];
      if (search) search.value = '';
      search = null;
      selectedGroup = 'all';
    });
    const reportHash = await hashJSON(data);
    ui.assertOperation(lifecycleToken);
    if (live && UUID.test(taskId) && UUID.test(runId) && reportHash
      && typeof taskApi?.get === 'function'
      && typeof taskApi?.listNegativeReviewConfirmations === 'function'
      && typeof taskApi?.confirmNegativeReview === 'function') {
      try {
        const fetchedTask = await taskApi.get(taskId);
        ui.assertOperation(lifecycleToken);
        task = fetchedTask;
        if (task?.task_id === taskId && UUID.test(task.store_id || '') && /^B0[A-Z0-9]{8}$/.test(task.self_asin || '')) {
          operationsReady = true;
          const saved = await taskApi.listNegativeReviewConfirmations(taskId, task.store_id, runId, reportHash, task.self_asin);
          ui.assertOperation(lifecycleToken);
          for (const row of saved) {
            const meta = row.items?.[0];
            if (row.status !== 'confirmed' || row.task_id !== taskId || row.self_asin !== task.self_asin
              || row.input_hash !== reportHash || meta?.kind !== 'negative-review-confirmation'
              || meta.schema_version !== 'negative-review-confirmation-0.1' || meta.run_id !== runId
              || meta.report_sha256 !== reportHash || !Array.isArray(meta.candidates)) continue;
            const ids = new Set(); let valid = true;
            for (const item of meta.candidates) {
              if (!item || typeof item !== 'object' || Array.isArray(item) || Object.keys(item).length !== 2
                || !groupKeys.has(item.group) || typeof item.keyword !== 'string' || item.keyword.length > 200
                || item.keyword !== item.keyword.trim() || /[\r\n\u0000-\u001f\u007f\u2028\u2029]/.test(item.keyword)) { valid = false; break; }
              const entry = entries.find(candidate => candidate.key === item.group && candidate.row.keyword?.trim() === item.keyword);
              const id = candidateId(item.group, item.keyword);
              if (!entry || !eligible(entry) || ids.has(id)) { valid = false; break; }
              ids.add(id);
            }
            if (!valid || ids.size === 0) continue;
            const ordered = [...meta.candidates].sort((a, b) => a.group.localeCompare(b.group) || normalize(a.keyword).localeCompare(normalize(b.keyword)));
            const versionDigest = await hashJSON({ schema_version: 'negative-review-confirmation-0.1', task_id: taskId,
              run_id: runId, report_sha256: reportHash, candidates: ordered });
            ui.assertOperation(lifecycleToken);
            if (versionDigest !== row.version.slice('negative-v1-'.length)) continue;
            confirmation = row; confirmedIds = ids; selected = new Set(ids); break;
          }
        }
      } catch (_) {
        if (!ui.operationIsActive(lifecycleToken)) return;
        // Reports remain readable if the confirmation endpoint is temporarily unavailable.
        operationsReady = false;
      }
    }

    ui.assertOperation(lifecycleToken);
    ui.setMetrics(groups.map(([key, label]) => [label, missingBuckets.has(key) ? '字段未提供' : ui.number(data[key].length)]));
    body.replaceChildren();
    body.append(ui.el('p', '候选仅供人工复核，不会写入 Amazon。相关/未知、慎否、待确认、词组冲突及已有订单保护的关键词不进入候选。低 CVR 高花费是独立复核组，不等于否定词。', 'notice'));
    const coverage = data.module_status?.coverage;
    const hasCompleteCoverage = coverage && Number.isInteger(coverage.classified_rows)
      && Number.isInteger(coverage.total_rows) && Number.isInteger(coverage.actionable_rows)
    const qualifiedCandidateCount = entries.filter(eligible).length;
    const coverageIsValid = hasCompleteCoverage
      && coverage.classified_rows >= 0 && coverage.total_rows >= 0 && coverage.actionable_rows >= 0
      && coverage.classified_rows <= coverage.total_rows
      && coverage.actionable_rows <= coverage.classified_rows
      && coverage.actionable_rows === qualifiedCandidateCount;
    coverageMatchesQualification = Boolean(coverageIsValid);
    const coverageText = coverageIsValid
      ? `分类完整 ${coverage.classified_rows} / ${coverage.total_rows} 条；可进入人工确认的否词候选 ${coverage.actionable_rows} 条。`
      : hasCompleteCoverage ? '报告覆盖统计异常；请重新生成报告并核对源数据。'
        : '旧报告未提供完整分类覆盖与人工确认候选统计。';
    body.append(ui.el('p', coverageText, 'muted'));
    const confirmationStatus = ui.el('p', undefined, 'notice');
    confirmationStatus.id = 'negative-confirmation-status';
    roots = new Map();
    entries.filter(entry => groupKeys.has(entry.key)).forEach(({ row }) => {
      const keyword = normalize(row.keyword);
      if (!/^[a-z\s'-]+$/.test(keyword)) return;
      new Set(keyword.match(/[a-z]+/g) || []).forEach(word => {
        if (!roots.has(word)) roots.set(word, new Set());
        roots.get(word).add(keyword);
      });
    });
    rootRows = [...roots].filter(([, words]) => words.size >= 2).sort(([a], [b]) => a.localeCompare(b)).map(([word, words]) => {
      const conflicts = [...protectedKeywords].filter(keyword => (keyword.match(/[a-z]+/g) || []).includes(word));
      return [word, words.size, [...words].join('、'), conflicts.join('、') || '未见分组保护冲突；仍需业务确认'];
    });
    const rootPanel = ui.el('details', undefined, 'panel');
    const ruleBoundaries = exportThresholdsValid
      ? `CVR=${ui.text(negativeRule.cvr_definition)} · 零订单精准否定：点击 ≥ ${ui.number(negativeRule.zero_order_clicks_threshold)} 且花费 ≥ ${ui.number(negativeRule.zero_order_spend_threshold, 2)} ${ui.text(data.currency_code || '币种未提供')} · 词组初步点击 ≥ ${ui.number(negativeRule.preliminary_clicks_threshold)} · 低 CVR < ${negativeRule.low_cvr_threshold === null ? '未配置' : ui.percent(negativeRule.low_cvr_threshold)}`
      : '规则阈值缺失或无效；本报告的候选不能复制或导出。';
    const ruleInfo = `否词规则 ${ui.text(negativeRule.rule_version || 'legacy/unknown')} · 配置 ${ui.text(data.effective_config_version || 'legacy/unknown')} · ${ruleBoundaries} · 高花费分位 ${ui.number(negativeRule.high_spend_percentile, 2)}（${ui.text(negativeRule.high_spend_percentile_source || '旧报告未记录')}）· 样本范围 ${ui.text(negativeRule.high_spend_sample_scope || '旧报告未记录')} · 算法 ${ui.text(negativeRule.high_spend_threshold_method || '旧报告未记录')} · 币种 ${ui.text(data.currency_code || '未提供')}`;
    rootPanel.append(ui.el('summary', '英文单词统计（只供复核，不直接复制）'), ui.el('p', `按不同候选关键词计数，至少命中两条；仅统计英文单词，不做词干推断。其他语言待专用分词策略。保护冲突来自完整报告分组，统计不赋予导出资格。归一化：${ui.text(negativeRule.normalization_version || 'legacy/unknown')}；分词：${ui.text(negativeRule.tokenization_version || 'legacy/unknown')}。${ruleInfo}`, 'muted'));
    rootPanel.append(rootRows.length ? ui.table(['单词', '不同候选数', '候选关键词', '保护冲突'], rootRows) : ui.el('p', '没有命中至少两条不同候选的英文单词。'));
    body.append(rootPanel);
    const panel = ui.el('section', undefined, 'panel table-panel');
    const toolbar = ui.el('div', undefined, 'toolbar');
    const label = ui.el('label', '搜索关键词 ');
    search = ui.el('input'); search.type = 'search'; search.placeholder = '输入关键词'; label.append(search);
    const filters = ui.el('div', undefined, 'filters'); filters.setAttribute('aria-label', '否词分类筛选');
    const buttons = [['all', '全部'], ...groups.map(([key, title]) => [key, title])].map(([key, title]) => {
      const button = ui.el('button', title, 'filter'); button.type = 'button'; button.dataset.negativeFilter = key;
      button.addEventListener('click', () => {
        if (!ui.operationIsActive(lifecycleToken)) return;
        invalidateActions(); selectedGroup = key; render();
      });
      filters.append(button); return [key, button];
    });
    const confirmButton = ui.el('button', '确认已选候选', 'button primary');
    confirmButton.type = 'button'; confirmButton.id = 'confirm-negative-review';
    const refreshButton = ui.el('button', '重新加载报告', 'button secondary'); refreshButton.type = 'button'; refreshButton.hidden = true;
    const exportButton = ui.el('button', '导出已确认候选 JSON', 'button secondary');
    exportButton.id = 'export-negative'; exportButton.type = 'button';
    const exportStatus = ui.el('p', undefined, 'muted'); exportStatus.setAttribute('role', 'status');
    const result = ui.el('div');
    const textPanel = ui.el('section', undefined, 'panel');
    textPanel.append(ui.el('h2', '当前筛选范围 · 已确认纯文本'));
    textOutputs = ['exact_negative', 'phrase_negative'].map((key, index) => {
      const title = index === 0 ? '精准否定' : '词组否定';
      const section = ui.el('div'), heading = ui.el('h3'), area = ui.el('textarea');
      area.id = `negative-text-${key}`; area.readOnly = true; area.rows = 6;
      area.setAttribute('aria-label', `${title}已确认纯文本，一行一词`); area.style = 'width:100%;max-width:100%;box-sizing:border-box';
      const copy = ui.el('button', `复制${title}`, 'button secondary'); copy.type = 'button'; copy.id = `copy-${key}`;
      copy.addEventListener('click', async () => {
        if (!ui.operationIsActive(lifecycleToken) || copy.disabled) return;
        const snapshot = beginActionSnapshot('copy', { copyKey: key });
        area.value = '';
        let text = '';
        try {
          const serverConfirmedIds = await verifyFreshConfirmation(snapshot);
          if (!serverConfirmedIds || !snapshotIsCurrent(snapshot)) return;
          const lines = snapshot.visibleCopies.filter(item => item.id && serverConfirmedIds.has(item.id)
            && snapshot.candidates.some(candidate => candidate.group === key
              && candidateId(candidate.group, candidate.keyword) === item.id));
          text = lines.map(item => item.text).join('\n');
          if (!text) return;
          assertSnapshot(snapshot);
          await navigator.clipboard.writeText(text);
          assertSnapshot(snapshot);
          exportStatus.textContent = `已复制 ${lines.length} 条已确认${title}候选；未提交 Amazon。`;
        } catch (_) {
          if (!snapshotIsCurrent(snapshot)) return;
          assertSnapshot(snapshot);
          area.value = text;
          exportStatus.textContent = '无法访问剪贴板；本次报告与确认刚已复核，可立即手动复制下方文本。';
        } finally {
          text = '';
        }
      });
      section.append(heading, area, copy); textPanel.append(section);
      return { key, title, heading, area, copy };
    });
    const visibleEntries = () => {
      const query = search.value.trim().toLocaleLowerCase();
      return entries.filter(entry => (selectedGroup === 'all' || entry.key === selectedGroup)
        && (!query || ui.text(entry.row.keyword).toLocaleLowerCase().includes(query)));
    };
    const selectedCandidates = () => entries.filter(entry => eligible(entry) && selected.has(candidateId(entry.key, entry.row.keyword)))
      .map(entry => ({ group: entry.key, keyword: entry.row.keyword.trim() }))
      .sort((a, b) => a.group.localeCompare(b.group) || normalize(a.keyword).localeCompare(normalize(b.keyword)));
    const sameSet = (left, right) => left.size === right.size && [...left].every(item => right.has(item));
    const sortedSet = value => [...value].sort();
    function invalidateActions() { actionRevision += 1; }
    function freezeTree(value) {
      if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
      for (const child of Object.values(value)) freezeTree(child);
      return Object.freeze(value);
    }
    function beginActionSnapshot(kind, extra = {}) {
      const operationToken = ui.operationToken();
      const revision = ++actionRevision;
      const selection = sortedSet(selected);
      const candidates = selectedCandidates().map(item => Object.freeze({ group: item.group, keyword: item.keyword }));
      const query = search?.value || '';
      const visible = visibleEntries();
      const visibleCopies = visible.filter(entry => groupKeys.has(entry.key)
        && selected.has(candidateId(entry.key, entry.row.keyword)) && eligible(entry))
        .map(entry => Object.freeze({ id: candidateId(entry.key, entry.row.keyword), text: entry.row.keyword.trim() }));
      const visibleExports = visible.filter(entry => groupKeys.has(entry.key)
        && selected.has(candidateId(entry.key, entry.row.keyword)) && eligible(entry))
        .map(({ key, row }) => Object.freeze({ id: candidateId(key, row.keyword),
          value: freezeTree(stable({ ...row, candidate_group: key })) }));
      return Object.freeze({
        kind, operationToken, revision, selection: Object.freeze(selection), candidates: Object.freeze(candidates),
        candidateIds: Object.freeze(candidates.map(item => candidateId(item.group, item.keyword)).sort()),
        confirmedIds: Object.freeze(sortedSet(confirmedIds)), filter: selectedGroup, search: query,
        version: confirmation?.version || null, confirmationStatus: confirmation?.status || null,
        reportHash, taskId, runId, storeId: task?.store_id || null, selfAsin: task?.self_asin || null,
        schemaVersion: data?.schema_version || null, currencyCode: data?.currency_code || null,
        operationsReady, dataChanged, visibleCopies: Object.freeze(visibleCopies),
        visibleExports: Object.freeze(visibleExports), ...extra,
      });
    }
    function snapshotIsCurrent(snapshot) {
      if (!snapshot || snapshot.revision !== actionRevision || !ui.operationIsActive(snapshot.operationToken)) return false;
      if (snapshot.filter !== selectedGroup || snapshot.search !== (search?.value || '')
        || snapshot.reportHash !== reportHash || snapshot.taskId !== taskId || snapshot.runId !== runId
        || snapshot.storeId !== (task?.store_id || null) || snapshot.selfAsin !== (task?.self_asin || null)
        || snapshot.version !== (confirmation?.version || null)
        || snapshot.confirmationStatus !== (confirmation?.status || null)
        || snapshot.operationsReady !== operationsReady || snapshot.dataChanged !== dataChanged
        || JSON.stringify(snapshot.selection) !== JSON.stringify(sortedSet(selected))
        || JSON.stringify(snapshot.confirmedIds) !== JSON.stringify(sortedSet(confirmedIds))
        || JSON.stringify(snapshot.candidates) !== JSON.stringify(selectedCandidates())) return false;
      return true;
    }
    function assertSnapshot(snapshot) {
      if (!snapshotIsCurrent(snapshot)) throw new Error('操作已因报告、选择或筛选变化而取消');
      ui.assertOperation(snapshot.operationToken);
    }
    const isConfirmed = () => Boolean(!dataChanged && confirmation && reportHash && sameSet(selected, confirmedIds)
      && confirmation.input_hash === reportHash && confirmation.task_id === taskId && confirmation.status === 'confirmed');
    async function expectedVersion(candidates, context = lifecycleToken) {
      const isSnapshot = Boolean(context?.operationToken && Number.isInteger(context.revision));
      const digest = await hashJSON({ schema_version: 'negative-review-confirmation-0.1',
        task_id: isSnapshot ? context.taskId : taskId,
        run_id: isSnapshot ? context.runId : runId,
        report_sha256: isSnapshot ? context.reportHash : reportHash, candidates });
      if (isSnapshot) assertSnapshot(context); else ui.assertOperation(context);
      return digest ? `negative-v1-${digest}` : null;
    }
    async function verifyFreshConfirmation(snapshot) {
      if (!snapshotIsCurrent(snapshot)) return null;
      if (!operationsReady || !isConfirmed() || !snapshot.version) {
        exportStatus.textContent = '请先勾选候选并提交版本确认；未确认内容不能复制或导出。'; return null;
      }
      try {
        assertSnapshot(snapshot);
        const loaded = await ui.load(moduleName);
        assertSnapshot(snapshot);
        let fresh = validateReport(loaded);
        const freshHash = await hashJSON(fresh);
        fresh = null;
        assertSnapshot(snapshot);
        if (freshHash !== reportHash) {
          invalidateActions();
          dataChanged = true; confirmation = null; selected.clear(); confirmedIds.clear();
          refreshButton.hidden = false; render();
          exportStatus.textContent = '服务器报告已变化，旧确认已失效。重新加载并复核新报告后再确认。';
          return null;
        }
        const version = await expectedVersion(snapshot.candidates, snapshot);
        assertSnapshot(snapshot);
        if (!version || version !== snapshot.version) {
          invalidateActions();
          confirmation = null; confirmedIds.clear(); render();
          exportStatus.textContent = '候选选择与已确认版本不一致，请重新确认。';
          return null;
        }
        assertSnapshot(snapshot);
        const rows = await taskApi.listNegativeReviewConfirmations(snapshot.taskId, snapshot.storeId,
          snapshot.runId, snapshot.reportHash, snapshot.selfAsin);
        assertSnapshot(snapshot);
        const verified = await findSavedConfirmation(rows, snapshot);
        assertSnapshot(snapshot);
        if (!verified || verified.row.version !== version || !sameSet(verified.ids, new Set(snapshot.confirmedIds))) {
          invalidateActions();
          confirmation = null; confirmedIds.clear(); render();
          exportStatus.textContent = '未能从服务器重新确认该版本；复制和导出已锁定。';
          return null;
        }
        confirmation = verified.row;
        confirmedIds = verified.ids;
        return new Set([...verified.ids].filter(id => snapshot.candidateIds.includes(id)));
      } catch (error) {
        if (!snapshotIsCurrent(snapshot)) return null;
        // A failed freshness read must revoke the rendered confirmation too;
        // otherwise a previously populated textarea could bypass the buttons.
        invalidateActions();
        confirmation = null; confirmedIds.clear(); render();
        exportStatus.textContent = '无法刷新报告或确认记录；为避免使用过期版本，复制和导出已锁定。';
        return null;
      }
    }
    async function findSavedConfirmation(rows, context = lifecycleToken, expected = {}) {
      const isSnapshot = Boolean(context?.operationToken && Number.isInteger(context.revision));
      const taskIdentity = isSnapshot ? context.taskId : taskId;
      const runIdentity = isSnapshot ? context.runId : runId;
      const reportIdentity = isSnapshot ? context.reportHash : reportHash;
      const selfAsin = isSnapshot ? context.selfAsin : task?.self_asin;
      for (const row of rows) {
        const meta = row.items?.[0];
        if (row.status !== 'confirmed' || row.task_id !== taskIdentity || row.self_asin !== selfAsin
          || row.input_hash !== reportIdentity || meta?.run_id !== runIdentity || meta?.report_sha256 !== reportIdentity
          || meta?.kind !== 'negative-review-confirmation'
          || meta?.schema_version !== 'negative-review-confirmation-0.1'
          || !Array.isArray(meta.candidates) || meta.candidates.length === 0) continue;
        const ids = new Set(), candidates = [];
        let valid = true;
        for (const item of meta.candidates) {
          if (!item || typeof item !== 'object' || Array.isArray(item) || Object.keys(item).length !== 2
            || !groupKeys.has(item.group) || typeof item.keyword !== 'string' || item.keyword.length > 200
            || item.keyword !== item.keyword.trim() || /[\r\n\u0000-\u001f\u007f\u2028\u2029]/.test(item.keyword)) {
            valid = false; break;
          }
          const entry = entries.find(candidate => candidate.key === item?.group && candidate.row.keyword?.trim() === item?.keyword);
          const id = candidateId(item?.group, item?.keyword);
          const frozenMatch = !isSnapshot || context.candidates.some(candidate => candidate.group === item.group
            && candidate.keyword === item.keyword);
          if (!entry || !eligible(entry) || !frozenMatch || ids.has(id)) { valid = false; break; }
          ids.add(id); candidates.push({ group: item.group, keyword: item.keyword });
        }
        if (!valid) continue;
        candidates.sort((a, b) => a.group.localeCompare(b.group) || normalize(a.keyword).localeCompare(normalize(b.keyword)));
        const version = await expectedVersion(candidates, context);
        if (isSnapshot) assertSnapshot(context); else ui.assertOperation(context);
        const expectedVersionValue = expected.version || context.version;
        const expectedIds = expected.ids || (context.kind === 'confirm' ? context.candidateIds : context.confirmedIds);
        if (version !== row.version || (isSnapshot && (version !== expectedVersionValue
          || !sameSet(ids, new Set(expectedIds))))) continue;
        return { row, ids };
      }
      return null;
    }
    confirmButton.addEventListener('click', async () => {
      if (!ui.operationIsActive(lifecycleToken) || confirmButton.disabled || selected.size === 0) return;
      const snapshot = beginActionSnapshot('confirm');
      confirmButton.disabled = true; exportStatus.textContent = '正在刷新报告并保存确认版本…';
      try {
        assertSnapshot(snapshot);
        const loaded = await ui.load(moduleName);
        assertSnapshot(snapshot);
        const fresh = validateReport(loaded);
        const freshHash = await hashJSON(fresh);
        assertSnapshot(snapshot);
        if (freshHash !== snapshot.reportHash) {
          invalidateActions();
          dataChanged = true; selected.clear(); confirmation = null; confirmedIds.clear(); refreshButton.hidden = false; render();
          exportStatus.textContent = '报告数据已变化，未保存确认。请重新加载报告并复核。'; return;
        }
        const candidates = Object.freeze(snapshot.candidates.map(item => Object.freeze({
          group: item.group, keyword: item.keyword,
        })));
        const version = await expectedVersion(snapshot.candidates, snapshot);
        assertSnapshot(snapshot);
        if (!version || candidates.length !== snapshot.selection.length) throw new Error('所选候选不再符合导出资格');
        assertSnapshot(snapshot);
        const saved = await taskApi.confirmNegativeReview({ taskId: snapshot.taskId, runId: snapshot.runId, version,
          selfAsin: snapshot.selfAsin, reportHash: snapshot.reportHash, candidates });
        assertSnapshot(snapshot);
        const persisted = await taskApi.listNegativeReviewConfirmations(snapshot.taskId, snapshot.storeId,
          snapshot.runId, snapshot.reportHash, snapshot.selfAsin);
        assertSnapshot(snapshot);
        const verified = await findSavedConfirmation(persisted, snapshot,
          { version, ids: snapshot.candidateIds });
        assertSnapshot(snapshot);
        if (!verified || verified.row.version !== saved.version) throw new Error('服务器确认版本无法回读校验');
        confirmation = verified.row; confirmedIds = verified.ids;
        invalidateActions();
        render(); exportStatus.textContent = `已保存并回读确认版本 ${version}（${candidates.length} 条）；仅供手动运营复核，未写入 Amazon。`;
      } catch (error) {
        if (!snapshotIsCurrent(snapshot)) return;
        exportStatus.textContent = error?.message || '确认未完成；未允许复制或导出。';
      } finally { if (snapshotIsCurrent(snapshot)) render(); }
    });
    refreshButton.addEventListener('click', () => { invalidateActions(); window.location.reload(); });
    exportButton.addEventListener('click', async () => {
      if (!ui.operationIsActive(lifecycleToken) || exportButton.disabled) return;
      const snapshot = beginActionSnapshot('export');
      const serverConfirmedIds = await verifyFreshConfirmation(snapshot);
      if (!serverConfirmedIds || !snapshotIsCurrent(snapshot)) return;
      let candidates = snapshot.visibleExports.filter(item => serverConfirmedIds.has(item.id))
        .map(item => item.value);
      if (!candidates.length) return;
      let link = null, url = null, releaseUrl = null, payload = null;
      const release = ui.onInvalidate(() => {
        candidates = []; payload = null; link?.remove(); link = null;
        releaseUrl?.(); releaseUrl = null; url = null;
      });
      try {
        assertSnapshot(snapshot);
        payload = { schema_version: snapshot.schemaVersion, source: moduleName, write_back: false,
          review_required: true, manual_confirmation_version: snapshot.version,
          task_id: snapshot.taskId, run_id: snapshot.runId, report_sha256: snapshot.reportHash,
          currency_code: snapshot.currencyCode, candidates };
        assertSnapshot(snapshot);
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
        assertSnapshot(snapshot);
        url = URL.createObjectURL(blob);
        assertSnapshot(snapshot);
        releaseUrl = ui.trackExportObjectURL(url, snapshot.operationToken);
        link = ui.el('a'); link.href = url; link.download = 'negative-candidates-for-manual-review.json';
        assertSnapshot(snapshot);
        document.body.append(link);
        assertSnapshot(snapshot);
        link.click();
        assertSnapshot(snapshot);
        exportStatus.textContent = `已导出当前筛选下 ${candidates.length} 条已确认候选；未写入 Amazon。`;
      } catch (_) { if (snapshotIsCurrent(snapshot)) exportStatus.textContent = '导出失败；报告及确认记录未改变。'; }
      finally {
        if (link) link.remove();
        if (releaseUrl) { setTimeout(releaseUrl, 1000); releaseUrl = null; }
        else if (url) { try { URL.revokeObjectURL(url); } catch (_) { /* unsupported URL implementation */ } }
        candidates = []; payload = null; release();
      }
    });
    search.addEventListener('input', () => {
      if (!ui.operationIsActive(lifecycleToken)) return;
      invalidateActions(); render();
    });
    toolbar.append(label, filters, confirmButton, refreshButton, exportButton);
    panel.append(toolbar, confirmationStatus, exportStatus, textPanel, result); body.append(panel);
    function trace(row) {
      const block = ui.el('div');
      block.append(ui.el('strong', Object.hasOwn(reasons, row.reason) ? reasons[row.reason] : ui.text(row.reason)));
      block.append(ui.el('small', `候选依据：${ui.text(row.reason)} · 原动作规则：${strings(row.rule_hits).join('、') || '—'}`));
      block.append(ui.el('small', `相关性：${ui.text(row.relevance)} · 来源：${ui.text(row.relevance_source)} · 规则版本：${ui.text(row.rule_version)} · 生效配置：${ui.text(row.effective_config_version)}`));
      const thresholdText = row.high_spend_threshold === null || row.high_spend_threshold === undefined
        ? '未计算' : `${ui.number(row.high_spend_threshold, 2)} ${ui.text(data.currency_code || '币种未提供')}`;
      block.append(ui.el('small', `CVR：${ui.percent(row.cvr_observed)} · 高花费线：${thresholdText} · 证据：${ui.text(row.evidence_level)}`));
      block.append(ui.el('small', `原动作：${ui.text(row.action_group)} · ${ui.text(row.next_action_text)}`));
      block.append(ui.el('small', `缺失字段：${strings(row.missing_fields).join('、') || '—'}`));
      block.append(ui.el('small', `保护/重复冲突：${strings(row.conflict_keywords || row.phrase_conflict_keywords).join('、') || '—'}`));
      return block;
    }
    function render() {
      if (!ui.operationIsActive(lifecycleToken)) return;
      const visible = visibleEntries();
      const authorized = isConfirmed();
      textOutputs.forEach(({ key, title, heading, area, copy }) => {
        const rows = visible.filter(entry => entry.key === key && eligible(entry) && selected.has(candidateId(entry.key, entry.row.keyword)));
        heading.textContent = `${title} · ${authorized ? rows.length : 0} 条已确认`;
        // Never leave manually copyable text on screen before the copy action
        // has freshly re-read both the private report and persisted confirmation.
        area.value = '';
        copy.disabled = !authorized || rows.length === 0;
      });
      buttons.forEach(([key, button]) => { button.className = key === selectedGroup ? 'filter active' : 'filter'; button.setAttribute('aria-pressed', String(key === selectedGroup)); });
      const visibleSelected = visible.filter(entry => eligible(entry) && selected.has(candidateId(entry.key, entry.row.keyword))).length;
      confirmButton.disabled = !operationsReady || dataChanged || selected.size === 0 || authorized;
      exportButton.disabled = !authorized || visibleSelected === 0;
      refreshButton.hidden = !dataChanged;
      confirmationStatus.textContent = dataChanged ? '报告版本变化：原确认失效，重新加载后必须重新复核。'
        : authorized ? `已确认 ${confirmedIds.size} 条候选；绑定当前 task/run 与报告 SHA-256。刷新页面可恢复此确认。`
        : operationsReady ? `尚未确认。先逐条勾选允许导出的候选，再提交确认；复制/导出前会再次从服务器刷新报告与确认记录。当前选择 ${selected.size} 条。`
        : '未建立可验证的持久确认（演示模式、确认接口不可用或任务绑定缺失）；复制和导出保持锁定。';
      exportStatus.textContent = authorized ? `已确认候选 ${visibleSelected} 条（当前筛选）；仅人工复核，不会写入 Amazon。`
        : '尚无当前报告版本的持久确认；纯文本不显示，复制和导出已锁定。';
      const selectedBucketMissing = selectedGroup !== 'all' && missingBuckets.has(selectedGroup);
      result.replaceChildren(visible.length ? ui.table(
        ['选择', '关键词', '候选分类', '点击', '花费（原币）', '订单', '销售额（原币）', 'ACOS', '证据与追溯'],
        visible.map(entry => {
          const { row, label, color, expected } = entry;
          let selectionCell = ui.el('span', '—');
          if (eligible(entry)) {
            selectionCell = ui.el('input'); selectionCell.type = 'checkbox';
            selectionCell.checked = selected.has(candidateId(entry.key, row.keyword));
            selectionCell.disabled = !operationsReady || dataChanged;
            selectionCell.setAttribute('aria-label', `选择候选 ${ui.text(row.keyword)}`);
            selectionCell.addEventListener('change', () => {
              if (!ui.operationIsActive(lifecycleToken)) return;
              invalidateActions();
              const id = candidateId(entry.key, row.keyword);
              if (selectionCell.checked) selected.add(id); else selected.delete(id);
              render();
            });
          }
          return [selectionCell, ui.text(row.keyword), ui.el('span', row.negative_status === expected ? label : '状态冲突 · 待确认', row.negative_status === expected ? color : 'badge gray'),
            ui.number(row.clicks), ui.number(row.spend, 2), ui.number(row.orders), ui.number(row.sales, 2), ui.percent(row.acos), trace(row)];
        }),
      ) : ui.el('p', selectedBucketMissing
        ? '旧版报告未提供该分类字段，不能等同于 0 条候选。'
        : entries.length ? '当前分类或关键词下没有候选。' : '暂无否词候选；不据此判断全部关键词都应保留。', 'table-empty'));
      const missingBucketLabels = groups.filter(([key]) => missingBuckets.has(key)).map(([, label]) => label);
      status.textContent = `${ui.statusPrefix(data)} · ${live ? '私有报告' : 'Demo'} · ${ui.number(visible.length)} / ${ui.number(entries.length)} 条 · ${ui.text(data.schema_version)} · 来源 negative-keywords.json${missingBucketLabels.length ? ` · 旧版字段未提供：${missingBucketLabels.join('、')}` : ''}`;
    }
    ui.assertOperation(lifecycleToken);
    render();
  } catch (error) {
    if (ui) ui.showError(error);
    else { status.textContent = '报告公共组件加载失败，请刷新重试。'; body.replaceChildren(); }
  } finally { body.setAttribute('aria-busy', 'false'); }
})();
