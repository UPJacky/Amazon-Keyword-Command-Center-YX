(async function () {
  if (!await globalThis.KWCC?.ready) return;
  const form = document.querySelector('#tool-form');
  if (!form) return;
  const asin = document.querySelector('#tool-asin');
  const file = document.querySelector('#tool-file');
  const stage = document.querySelector('#tool-stage');
  const confirm = document.querySelector('#tool-confirm');
  const button = document.querySelector('#tool-submit');
  const status = document.querySelector('#tool-form-status');
  const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
  const PHASE3_ORDER = Object.freeze(['ingestion', 'reconciliation', 'config/provider', 'report']);
  let submitting = false;
  function setStatus(message, success = false) {
    status.textContent = message;
    status.className = `form-status${success ? ' success-text' : ''}`;
  }
  function validateFile(value) {
    if (!value) throw new Error('请选择 .xlsx 或 .csv 文件');
    const lower = value.name.toLowerCase();
    if (!lower.endsWith('.xlsx') && !lower.endsWith('.csv')) throw new Error('文件格式不支持，仅允许 .xlsx 或 .csv');
    if (value.size > MAX_UPLOAD_BYTES) throw new Error('文件超过 10 MB 大小限制');
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    const value = String(asin.value || '').trim().toUpperCase();
    try {
      if (!/^B0[A-Z0-9]{8}$/.test(value)) throw new Error('ASIN 必须是以 B0 开头的 10 位字母数字组合');
      if (!stage.value) throw new Error('请选择产品阶段');
      validateFile(file.files?.[0]);
      if (!confirm.checked) throw new Error('请确认输入文件属于当前分析任务');
      if (PHASE3_ORDER.join(' → ') !== 'ingestion → reconciliation → config/provider → report') throw new Error('阶段顺序配置无效');
      submitting = true; button.disabled = true; button.textContent = '提交中…';
      const result = await globalThis.KWCC.tasks.create({ self_asin: value, product_stage: stage.value, file: file.files[0] });
      setStatus(result?.demo ? '本地校验通过；演示模式未上传、未创建真实任务。' : `任务 ${result.task_id} 已提交。`, true);
    } catch (error) {
      setStatus(error.message || '提交失败');
    } finally {
      submitting = false; button.disabled = false; button.textContent = '提交分析任务';
    }
  });
  file.addEventListener('change', () => {
    try { validateFile(file.files?.[0]); setStatus(`${file.files[0].name} · 格式与大小校验通过`, true); }
    catch (error) { setStatus(error.message); }
  });
})();
