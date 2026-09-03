(async function () {
  if (!await globalThis.KWCC?.ready) return;
  const version = document.querySelector('#strategy-config-version');
  if (!version) return;
  if (globalThis.KWCC.mode === 'live') {
    const target = document.querySelector('#strategy-local-values');
    version.textContent = 'Live · 只读';
    target.textContent = '正在读取授权策略；当前 RLS 未允许写入。';
    try {
      const configs = await globalThis.KWCC.strategies.list();
      target.textContent = configs.length ? configs.map(item => `config_version · ${item.config_version} / rule_version · ${item.rule_version}`).join('；') : '没有可读策略；未保存任何配置。';
    } catch(error) { target.textContent = '策略读取失败；不显示演示配置。'; globalThis.KWCC.showError(error); }
    return;
  }
  fetch('../rules/defaults/stable.json').then(response => {
    if (!response.ok) throw new Error(`config HTTP ${response.status}`);
    return response.json();
  }).then(config => {
    version.textContent = `config_version · ${config.config_version}`;
    const values = {
      'ACOS 目标': `${(config.acos.target * 100).toFixed(0)}%`,
      'ACOS 容忍': `${(config.acos.tolerance * 100).toFixed(0)}%`,
      '0 单点击止损': `${config.stop_loss.zero_order_clicks} 点击`,
      '自然位防守': `Top ${config.organic_defense.core_max_rank}`,
    };
    const target = document.querySelector('#strategy-local-values');
    if (target) target.textContent = Object.entries(values).map(([key, value]) => `${key}: ${value}`).join(' · ');
  }).catch(() => {
    version.textContent = 'config_version · 本地配置不可用';
  });
})();
