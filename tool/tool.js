(async function () {
  if (!await globalThis.KWCC?.ready) return;
  const form = document.querySelector('#tool-form');
  if (!form) return;
  const asin = document.querySelector('#tool-asin');
  const file = document.querySelector('#tool-file');
  const stage = document.querySelector('#tool-stage');
  const primaryKeyword = document.querySelector('#tool-primary-keyword');
  const coreKeywordInput = document.querySelector('#tool-core-keywords');
  const competitorInput = document.querySelector('#tool-competitors');
  const confirm = document.querySelector('#tool-confirm');
  const button = document.querySelector('#tool-submit');
  const status = document.querySelector('#tool-form-status');
  const store = document.querySelector('#tool-store');
  const live = globalThis.KWCC.mode === 'live';
  let authRevision = 0;
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
  function parseCoreKeywords() {
    const values = String(coreKeywordInput?.value || '')
      .split(/[\r\n,，;；]+/).map(item => item.trim()).filter(Boolean);
    const seen = new Set();
    return values.filter(item => {
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
  function refreshPrimaryKeywordOptions() {
    if (!primaryKeyword) return;
    const selected = primaryKeyword.value;
    const keywords = parseCoreKeywords();
    primaryKeyword.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = keywords.length ? '请选择主要核心关键词' : '请先填写核心关键词';
    primaryKeyword.append(placeholder);
    for (const keyword of keywords) {
      const option = document.createElement('option');
      option.value = keyword;
      option.textContent = keyword;
      primaryKeyword.append(option);
    }
    primaryKeyword.value = keywords.includes(selected) ? selected : '';
  }
  refreshPrimaryKeywordOptions();
  coreKeywordInput?.addEventListener('input', () => {
    refreshPrimaryKeywordOptions();
  });
  if (live) {
    document.querySelector('#tool-store-field').hidden = false;
    button.disabled = true;
    try {
      if (!globalThis.KWCC.auth || typeof globalThis.KWCC.auth.checkSession !== 'function'
        || typeof globalThis.KWCC.auth.subscribe !== 'function')
        throw new Error('Live session adapter is unavailable');
      globalThis.KWCC.auth.subscribe(state => {
        authRevision += 1;
        if (['signed_out', 'expired', 'forbidden'].includes(state)) {
          serviceReady = false;
          button.disabled = true;
          setStatus('Live session ended; sign in again before submitting.');
        }
      });
      const stores = await globalThis.KWCC.stores.list();
      globalThis.KWCC.auth.checkSession();
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
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting || !serviceReady) return;
    const value = String(asin.value || '').trim().toUpperCase();
    let requestAuthRevision = authRevision;
    try {
      if (!/^B0[A-Z0-9]{8}$/.test(value)) throw new Error('ASIN 必须是以 B0 开头的 10 位字母数字组合');
      if (!stage.value) throw new Error('请选择产品阶段');
      validateFile(file.files?.[0]);
      if (live && !store.value) throw new Error('请选择已授权店铺');
      if (!confirm.checked) throw new Error('请确认输入文件属于当前分析任务');
      const competitors = String(competitorInput?.value || '').split(/[\s,，;；]+/).map(item => item.trim().toUpperCase()).filter(Boolean);
      if (competitors.some(item => !/^B0[A-Z0-9]{8}$/.test(item))) throw new Error('指定竞对必须全部是 B0 开头的 10 位 ASIN');
      if (competitors.length > 5) throw new Error('指定竞对最多填写 5 个 ASIN');
      if (new Set(competitors).size !== competitors.length || competitors.includes(value)) throw new Error('指定竞对 ASIN 不能重复，也不能包含自己的 ASIN');
      const coreKeywords = parseCoreKeywords();
      const invalidKeyword = keyword => Array.from(keyword).length > 200 || /[\u0000-\u001f\u007f-\u009f]/u.test(keyword);
      if (coreKeywords.length > 200 || coreKeywords.some(invalidKeyword))
        throw new Error('核心关键词最多 200 个，每个不得超过 200 个字符');
      const keyword = String(primaryKeyword?.value || '').trim();
      if (keyword && !coreKeywords.includes(keyword))
        throw new Error('主要核心关键词必须从上方列表中选择');
      if (coreKeywords.length && !keyword)
        throw new Error('请从核心关键词列表中选择主要关键词');
      if (PHASE3_ORDER.join(' → ') !== 'ingestion → reconciliation → config/provider → report') throw new Error('阶段顺序配置无效');
      const submittedSnapshot = {
        asin: String(asin.value || ''), stage: String(stage.value || ''),
        primaryKeyword: String(primaryKeyword?.value || ''),
        coreKeywords: String(coreKeywordInput?.value || ''),
        competitors: String(competitorInput?.value || ''),
        confirmed: Boolean(confirm.checked), store: String(store?.value || ''),
        file: file.files[0],
      };
      const formStillMatchesSnapshot = () => String(asin.value || '') === submittedSnapshot.asin
        && String(stage.value || '') === submittedSnapshot.stage
        && String(primaryKeyword?.value || '') === submittedSnapshot.primaryKeyword
        && String(coreKeywordInput?.value || '') === submittedSnapshot.coreKeywords
        && String(competitorInput?.value || '') === submittedSnapshot.competitors
        && Boolean(confirm.checked) === submittedSnapshot.confirmed
        && String(store?.value || '') === submittedSnapshot.store
        && file.files?.[0] === submittedSnapshot.file;
      submitting = true; button.disabled = true; button.textContent = '提交中…';
      requestAuthRevision = authRevision;
      if (live) globalThis.KWCC.auth.checkSession();
      const result = await globalThis.KWCC.tasks.create({ store_id: store?.value,
        self_asin: value, product_stage: stage.value, file: file.files[0],
        primary_core_keyword: keyword || null, competitor_asins: competitors,
        core_keywords: coreKeywords });
      if (live && authRevision !== requestAuthRevision) return;
      if (live) globalThis.KWCC.auth.checkSession();
      if (live && authRevision !== requestAuthRevision) return;
      if (live) {
        if (!result || result.demo === true || result.persisted === false
          || !/^[0-9a-f-]{36}$/i.test(result.task_id || '')
          || !/^[0-9a-f-]{36}$/i.test(result.run_id || '')
          || !['pending', 'processing', 'completed', 'failed'].includes(result.status))
          throw new Error('Task creation was not confirmed; refresh the task list to verify it');
        const labels = { pending: 'pending (not yet run)', processing: 'processing',
          completed: 'completed', failed: 'failed' };
        setStatus(`Task ${result.task_id} confirmed (${labels[result.status]})`, result.status === 'pending');
        if (formStillMatchesSnapshot()) file.value = '';
        document.querySelector('#refresh-tasks')?.click();
        return;
      }
      if (result?.demo !== true || result.persisted !== false)
        throw new Error('Demo result was not confirmed');
      setStatus(result?.demo ? '本地校验通过；演示模式未上传、未创建真实任务。' : `任务 ${result.task_id} 已提交。`, true);
      if (live) { file.value = ''; document.querySelector('#refresh-tasks')?.click(); }
    } catch (error) {
      if (live && authRevision !== requestAuthRevision) return;
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
