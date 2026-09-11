(async function () {
  if (!await globalThis.KWCC?.ready) return;
  const form = document.querySelector('#tool-form');
  if (!form) return;
  const asin = document.querySelector('#tool-asin');
  const file = document.querySelector('#tool-file');
  const stage = document.querySelector('#tool-stage');
  const primaryKeyword = document.querySelector('#tool-primary-keyword');
  const competitorInput = document.querySelector('#tool-competitors');
  const confirm = document.querySelector('#tool-confirm');
  const button = document.querySelector('#tool-submit');
  const status = document.querySelector('#tool-form-status');
  const store = document.querySelector('#tool-store');
  const live = globalThis.KWCC.mode === 'live';
  let submissionIds = null;
  const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
  const PHASE3_ORDER = Object.freeze(['ingestion', 'reconciliation', 'config/provider', 'report']);
  let submitting = false;
  let serviceReady = !live;
  function setStatus(message, success = false) {
    status.textContent = message;
    status.className = `form-status${success ? ' success-text' : ''}`;
  }
  function validateFile(value) {
    if (!value) throw new Error('请选择 .xlsx 或 .csv 文件');
    const lower = value.name.toLowerCase();
    if (!lower.endsWith('.xlsx') && !lower.endsWith('.csv')) throw new Error('文件格式不支持，仅允许 .xlsx 或 .csv');
    if (value.size > MAX_UPLOAD_BYTES) throw new Error('文件超过 10 MB 大小限制');
    if (value.size === 0) throw new Error('文件为空，请选择有效报表');
  }
  if (live) {
    document.querySelector('#tool-store-field').hidden = false;
    button.disabled = true;
    try {
      const stores = await globalThis.KWCC.stores.list();
      store.replaceChildren();
      stores.forEach(value => {
        const option = document.createElement('option'); option.value = value.store_id;
        option.textContent = `${value.name || '店铺'} · ${value.marketplace || '—'}`; store.append(option);
      });
      if (!stores.length) throw new Error('当前账号没有已授权店铺，请联系管理员添加店铺权限');
      if (!globalThis.KWCC.tasks.canUpload) throw new Error('上传服务尚未部署，请稍后再试');
      serviceReady = true;
      button.disabled = false;
    } catch (error) { setStatus(error.message || '店铺读取失败'); }
  }
  [asin, stage, primaryKeyword, competitorInput, file, store].filter(Boolean).forEach(input => input.addEventListener('change', () => { submissionIds = null; }));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting || !serviceReady) return;
    const value = String(asin.value || '').trim().toUpperCase();
    try {
      if (!/^B0[A-Z0-9]{8}$/.test(value)) throw new Error('ASIN 必须是以 B0 开头的 10 位字母数字组合');
      if (!stage.value) throw new Error('请选择产品阶段');
      validateFile(file.files?.[0]);
      if (live && !store.value) throw new Error('请选择已授权店铺');
      if (!confirm.checked) throw new Error('请确认输入文件属于当前分析任务');
      const competitors = String(competitorInput?.value || '').split(/[\s,，;；]+/).map(item => item.trim().toUpperCase()).filter(Boolean);
      if (competitors.some(item => !/^B0[A-Z0-9]{8}$/.test(item))) throw new Error('指定竞对必须全部是 B0 开头的 10 位 ASIN');
      if (new Set(competitors).size !== competitors.length || competitors.includes(value)) throw new Error('指定竞对 ASIN 不能重复，也不能包含自己的 ASIN');
      if (PHASE3_ORDER.join(' → ') !== 'ingestion → reconciliation → config/provider → report') throw new Error('阶段顺序配置无效');
      submitting = true; button.disabled = true; button.textContent = '提交中…';
      if (live && !submissionIds) submissionIds = { task_id: crypto.randomUUID(), run_id: crypto.randomUUID() };
      const result = await globalThis.KWCC.tasks.create({ ...submissionIds, store_id: store?.value,
        self_asin: value, product_stage: stage.value, file: file.files[0],
        primary_core_keyword: String(primaryKeyword?.value || '').trim(), competitor_asins: competitors,
        core_keywords: String(primaryKeyword?.value || '').trim() ? [String(primaryKeyword.value).trim()] : [] });
      setStatus(result?.demo ? '本地校验通过；演示模式未上传、未创建真实任务。' : `任务 ${result.task_id} 已提交。`, true);
      if (live) { submissionIds = null; file.value = ''; document.querySelector('#refresh-tasks')?.click(); }
    } catch (error) {
      setStatus(error.message || '提交失败');
    } finally {
      submitting = false; button.disabled = !serviceReady; button.textContent = '提交分析任务';
    }
  });
  file.addEventListener('change', () => {
    try { validateFile(file.files?.[0]); setStatus(`${file.files[0].name} · 格式与大小校验通过`, true); }
    catch (error) { setStatus(error.message); }
  });
})();
