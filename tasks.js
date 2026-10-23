(async function () {
  if (!await globalThis.KWCC?.ready) return;
  const body = document.querySelector('#task-rows');
  if (!body) return;
  const count = document.querySelector('#task-count');
  const refreshButton = document.querySelector('#refresh-tasks');
  const display = value => value === null || value === undefined || value === '' ? '—' : String(value);
  const normaliseMissingFields = value => Array.isArray(value) ? [...new Set(value.filter(item => typeof item === 'string' && item.trim()).map(item => item.trim()))].sort() : [];
  const dataPath = name => `${window.location.pathname.includes('/frontend/') ? '../../' : '../'}data/golden/market-demo-report/${name}`;
  // Fixed backend order; labels are display-only.
  const MODULES = [
    ['rank-benchmark.json', '排名对标'],
    ['negative-keywords.json', '否定关键词'],
    ['competitors.json', '竞品分析'],
    ['category-features.json', '品类特征'],
    ['buyer-checklist.json', '买家关注清单'],
    ['text-evidence.json', '文本证据'],
    ['listing-diagnostics.json', 'Listing 诊断'],
    ['optimization-plan.json', '优化方案'],
  ];
  const LABELS = new Map(MODULES);
  // UI preview only: client.js and the database recompute the authoritative closure.
  const DEPENDENCIES = {
    'rank-benchmark.json': [],
    'negative-keywords.json': [],
    'competitors.json': [],
    'category-features.json': [],
    'buyer-checklist.json': ['category-features.json'],
    'text-evidence.json': ['competitors.json', 'buyer-checklist.json'],
    'listing-diagnostics.json': ['competitors.json', 'buyer-checklist.json'],
    'optimization-plan.json': [],
  };
  function dependencyClosure(selected) {
    const chosen = new Set(selected);
    const pending = [...selected];
    while (pending.length) {
      for (const dependency of DEPENDENCIES[pending.pop()] || []) {
        if (chosen.has(dependency)) continue;
        chosen.add(dependency);
        pending.push(dependency);
      }
    }
    return MODULES.map(([name]) => name).filter(name => chosen.has(name));
  }
  let loading = false;

  function closeElement(element) {
    if (typeof element.remove === 'function') { element.remove(); return; }
    if (element.parentNode && typeof element.parentNode.removeChild === 'function') {
      element.parentNode.removeChild(element);
      return;
    }
    element.hidden = true;
  }

  function openSelectiveRerun(task, run, onClose) {
    const dialog = document.createElement('div');
    dialog.className = 'modal';
    dialog.dataset.selectiveRerun = 'true';
    if (typeof dialog.setAttribute === 'function') {
      dialog.setAttribute('role', 'dialog');
      dialog.setAttribute('aria-modal', 'true');
      dialog.setAttribute('aria-hidden', 'false');
    }
    const panel = document.createElement('div');
    panel.className = 'modal__content';
    const title = document.createElement('h2');
    title.textContent = '选择性重跑';
    const description = document.createElement('p');
    description.className = 'muted';
    description.textContent = '仅重跑所选模块，其余模块复用当前已完成运行的结果；依赖模块会自动补齐。';
    const options = document.createElement('div');
    options.className = 'form-stack';
    const checkboxes = new Map();
    for (const [name, label] of MODULES) {
      const row = document.createElement('label');
      row.className = 'form-row';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = name;
      checkbox.checked = false;
      const text = document.createElement('span');
      text.textContent = label;
      row.append(checkbox, text);
      options.append(row);
      checkboxes.set(name, checkbox);
    }
    const hint = document.createElement('p');
    hint.className = 'form-status';
    hint.dataset.dependencyHint = 'true';
    const actions = document.createElement('div');
    actions.className = 'form-row form-row--end';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'button button--secondary';
    cancel.textContent = '取消';
    cancel.dataset.action = 'cancel';
    const confirm = document.createElement('button');
    confirm.type = 'button';
    confirm.className = 'button button--primary';
    confirm.textContent = '确认重跑';
    confirm.disabled = true;
    confirm.dataset.action = 'confirm';
    actions.append(cancel, confirm);
    panel.append(title, description, options, hint, actions);
    dialog.append(panel);
    document.body.append(dialog);

    let operation = null;
    let submitting = false;
    let closed = false;
    const selectedModules = () => MODULES.map(([name]) => name).filter(name => checkboxes.get(name).checked);
    const renderHint = () => {
      if (submitting || operation) return;
      const selected = selectedModules();
      confirm.disabled = selected.length === 0;
      if (!selected.length) { hint.textContent = '请至少选择一个模块。'; return; }
      const added = dependencyClosure(selected).filter(name => !selected.includes(name));
      hint.textContent = added.length
        ? `将自动补齐依赖：${added.map(name => LABELS.get(name)).join('、')}`
        : '所选模块无需额外依赖。';
    };
    const close = () => {
      if (closed) return;
      closed = true;
      closeElement(dialog);
      onClose();
    };
    for (const checkbox of checkboxes.values()) checkbox.addEventListener('change', renderHint);
    cancel.addEventListener('click', close);
    confirm.addEventListener('click', async () => {
      if (submitting || closed) return;
      try {
        if (!operation) {
          const requestedModules = selectedModules();
          if (!requestedModules.length) return;
          // The first confirmation owns the entire operation. A lost response
          // must retry its original identity and module plan, even if the DOM changes.
          operation = Object.freeze({
            taskId: task.task_id,
            previousRunId: run.run_id,
            runId: crypto.randomUUID(),
            requestedModules: Object.freeze([...requestedModules]),
          });
        }
        submitting = true;
        confirm.disabled = true;
        confirm.textContent = '提交中…';
        for (const checkbox of checkboxes.values()) checkbox.disabled = true;
        await globalThis.KWCC.tasks.rerunSelectedModules(operation);
      } catch (error) {
        globalThis.KWCC.showError?.(error);
        for (const checkbox of checkboxes.values()) checkbox.disabled = true;
        hint.textContent = operation === null
          ? '未能生成本次运行编号；请取消后重新发起选择性重跑。'
          : `本次运行编号已固定（${operation.runId}），重试将复用同一运行，不会创建第二个。`;
        confirm.textContent = '重试确认';
        submitting = false;
        confirm.disabled = false;
        return;
      }
      submitting = false;
      close();
      await refresh();
    });
    renderHint();
  }

  function renderRow(values) {
    const row = document.createElement('tr');
    values.forEach(value => { const cell = document.createElement('td'); cell.textContent = display(value); row.append(cell); });
    return row;
  }

  async function refresh() {
    if (loading) return;
    loading = true;
    if (refreshButton) { refreshButton.disabled = true; refreshButton.textContent = '刷新中…'; }
    try {
      body.replaceChildren();
      if (globalThis.KWCC.mode === 'live') {
        const tasks = await globalThis.KWCC.tasks.list();
        tasks.forEach(task => {
          const row = renderRow([
          task.task_id, task.input_file_path, task.status, task.created_at,
          task.current_stage, task.failure_reason?.message || task.failure_reason?.code || task.failure_reason || '—',
          '',
          ]);
          const actions = row.lastElementChild;
          if (['completed', 'failed'].includes(task.status)) {
            const failed = task.status === 'failed';
            const report = document.createElement('button'); report.type = 'button'; report.className = 'button button--small';
            report.textContent = failed ? '查看失败证据' : '查看报告';
            report.addEventListener('click', async () => {
              report.disabled = true;
              try {
                const run = await globalThis.KWCC.tasks.latestRun(task.task_id);
                if (!run || run.status !== task.status) throw new Error('最新运行状态已改变，请刷新任务列表');
                const target = new URL(document.body.dataset.reportUrl || 'report.html', window.location.href);
                target.searchParams.set('task', task.task_id); target.searchParams.set('run', run.run_id);
                window.location.href = target.href;
              } catch (error) { globalThis.KWCC.showError?.(error); report.disabled = false; }
            });
            actions.append(report);
          }
          if (['completed', 'failed'].includes(task.status) && globalThis.KWCC.tasks.canUpload) {
            const rerun = document.createElement('button'); rerun.type = 'button'; rerun.className = 'button button--secondary button--small'; rerun.textContent = '重新分析';
            let nextRunId = null;
            rerun.addEventListener('click', async () => {
              rerun.disabled = true;
              try {
                const run = await globalThis.KWCC.tasks.latestRun(task.task_id);
                if (!run || !['completed', 'failed'].includes(run.status)) throw new Error('任务正在执行，请刷新列表');
                nextRunId ||= crypto.randomUUID();
                await globalThis.KWCC.tasks.rerun(task.task_id, run.run_id, nextRunId);
                await refresh();
              } catch (error) { globalThis.KWCC.showError?.(error); rerun.disabled = false; }
            });
            actions.append(rerun);
            const selective = document.createElement('button'); selective.type = 'button';
            selective.className = 'button button--secondary button--small';
            selective.textContent = '选择性重跑';
            selective.addEventListener('click', async () => {
              selective.disabled = true;
              try {
                const run = await globalThis.KWCC.tasks.latestRun(task.task_id);
                if (!run || !['completed', 'failed'].includes(run.status)) throw new Error('任务正在执行，请刷新列表');
                openSelectiveRerun(task, run, () => { selective.disabled = false; });
              } catch (error) { globalThis.KWCC.showError?.(error); selective.disabled = false; }
            });
            actions.append(selective);
          }
          body.append(row);
        });
        if (count) count.textContent = `共 ${tasks.length} 项`;
      } else {
        const response = await fetch(dataPath('report-meta.json'));
        if (!response.ok) throw new Error(`task artifact HTTP ${response.status}`);
        const meta = await response.json();
        const row = document.createElement('tr');
        const values = [
          ['演示任务 · market-demo', `${display(meta.schema_version)} · ${meta.reconciliation_passed === true ? '对账通过' : '对账失败'}`],
          [display(meta.input_file), `${display(meta.currency_code)} · 输入 SHA-256 ${display(meta.input_sha256).slice(0, 12)}${meta.input_sha256 ? '…' : ''}`],
          ['已完成', display(meta.rule_version)],
          ['本地 artifact', `${display(meta.config_version)} · ${display(meta.provider_snapshot_version)} · 缺失字段 ${normaliseMissingFields(meta.missing_fields).join(' · ') || '—'}`],
          ['已生成', 'run artifact'],
          ['—', '无失败原因'],
          ['查看报告', '在线 fetch 渲染'],
        ];
        values.forEach(([primary, secondary]) => {
          const cell = document.createElement('td');
          const strong = document.createElement('strong'); strong.textContent = primary;
          const small = document.createElement('small'); small.textContent = secondary;
          cell.append(strong, small); row.append(cell);
        });
        body.appendChild(row);
        if (count) count.textContent = '共 1 项';
      }
    } catch (error) {
      body.replaceChildren();
      if (count) count.textContent = '读取失败 · 不显示演示任务';
      globalThis.KWCC.showError?.(error);
    } finally {
      loading = false;
      if (refreshButton) { refreshButton.disabled = false; refreshButton.textContent = '手动刷新'; }
    }
  }

  if (refreshButton && typeof refreshButton.addEventListener === 'function') refreshButton.addEventListener('click', refresh);
  await refresh();
  if (typeof window !== 'undefined' && typeof window.setInterval === 'function') {
    const timer = window.setInterval(refresh, 30_000);
    if (typeof window.addEventListener === 'function') window.addEventListener('pagehide', () => window.clearInterval(timer), { once: true });
  }
})();
