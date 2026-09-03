(async function () {
  if (!await globalThis.KWCC?.ready) return;
  const body = document.querySelector('#task-rows');
  if (!body) return;
  const count = document.querySelector('#task-count');
  const refreshButton = document.querySelector('#refresh-tasks');
  const display = value => value === null || value === undefined || value === '' ? '—' : String(value);
  const normaliseMissingFields = value => Array.isArray(value) ? [...new Set(value.filter(item => typeof item === 'string' && item.trim()).map(item => item.trim()))].sort() : [];
  const dataPath = name => `${window.location.pathname.includes('/frontend/') ? '../../' : '../'}data/golden/market-demo-report/${name}`;
  let loading = false;

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
        tasks.forEach(task => body.append(renderRow([
          task.task_id, task.input_file_path, task.status, task.created_at,
          task.current_stage, task.failure_reason?.message || task.failure_reason?.code || task.failure_reason || '—',
          '查看详情',
        ])));
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
