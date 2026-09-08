(function (root) {
  'use strict';
  // Labels and validation bounds only. Editable values always come from API rows.
  const groups = {
    evidence: ['广告证据', {
      insufficient_clicks_max: ['证据不足的点击上限', 0, 1e9, true],
      preliminary_clicks_min: ['初步证据的点击下限', 0, 1e9, true],
      sufficient_clicks_min: ['充分证据的点击下限', 0, 1e9, true],
      preliminary_orders_min: ['初步证据的订单下限', 0, 1e9, true],
      sufficient_orders_min: ['充分证据的订单下限', 0, 1e9, true],
    }],
    acos: ['成本与利润（比例：0.20 表示 20%）', {
      target: ['ACOS 目标', 0, 1], tolerance: ['ACOS 容忍', 0, 1], break_even: ['盈亏平衡 ACOS', 0, 1],
    }],
    stop_loss: ['止损', {
      zero_order_clicks: ['零订单点击止损', 0, 1e9, true], zero_order_spend: ['零订单花费止损（店铺币种）', 0, 1e12],
    }],
    market: ['市场（比例：0 至 1）', {
      high_search_volume: ['高搜索量边界', 0, 1], high_opportunity_min: ['高机会下限', 0, 1],
    }],
    organic_defense: ['自然排名防守', {
      core_max_rank: ['核心自然排名上限', 1, 1e9, true], max_defense_acos: ['防守 ACOS 上限（比例）', 0, 1],
    }],
    diagnostics: ['诊断（比例：0.05 表示 5%）', {
      low_ctr: ['低点击率边界', 0, 1], low_cvr: ['低转化率边界', 0, 1],
    }],
  };
  const stages = { new: '新品', growth: '成长', stable: '稳定', clearance: '清仓', seasonal_restart: '季节重启' };
  const ruleVersions = ['rule-v0.1', 'rules-1.0'];
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const clone = value => JSON.parse(JSON.stringify(value));
  const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  const exactKeys = (value, keys) => object(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
  function validate(config) {
    if (!exactKeys(config, ['schema_version', 'config_version', 'product_stage', ...Object.keys(groups)])
      || config.schema_version !== 'config-0.1' || !Object.hasOwn(stages, config.product_stage)
      || typeof config.config_version !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(config.config_version))
      throw new Error('配置结构或版本不受支持；请联系管理员核对，不能编辑公式或未知字段。');
    for (const [section, [, fields]] of Object.entries(groups)) {
      if (!exactKeys(config[section], Object.keys(fields))) throw new Error('配置字段缺失或包含未知字段。');
      for (const [key, [label, min, max, integer]] of Object.entries(fields)) {
        const value = config[section][key];
        if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value)))
          throw new Error(`${label}须为 ${min} 至 ${max} 的${integer ? '整数' : '数值'}。`);
      }
    }
    const a = config.acos, e = config.evidence;
    if (a.target > a.tolerance || a.tolerance > a.break_even) throw new Error('ACOS 需满足：目标 ≤ 容忍 ≤ 盈亏平衡。');
    if (e.insufficient_clicks_max >= e.preliminary_clicks_min || e.preliminary_clicks_min > e.sufficient_clicks_min
      || e.preliminary_orders_min > e.sufficient_orders_min) throw new Error('证据边界需满足：不足点击上限 < 初步点击 ≤ 充分点击，初步订单 ≤ 充分订单。');
    return config;
  }
  function compatible(row) {
    validate(row.config);
    if (row.config.config_version !== row.config_version || row.config.product_stage !== row.product_stage || !ruleVersions.includes(row.rule_version))
      throw new Error('行版本、产品阶段或规则版本不匹配，不能发布此配置。');
  }
  const scope = row => JSON.stringify([row.store_id, row.product_stage, row.asin ?? null]);
  function equal(a, b) {
    if (a === b) return true;
    return object(a) && object(b) && exactKeys(a, Object.keys(b)) && Object.keys(a).every(key => equal(a[key], b[key]));
  }
  async function boot() {
    const client = root.KWCC;
    if (!client || !await client.ready) return;
    const doc = root.document, get = id => doc.querySelector(`#${id}`);
    const version = get('strategy-config-version');
    if (!version) return;
    const message = get('strategy-local-values'), heading = get('strategy-mode-label');
    if (client.mode !== 'live') {
      heading.textContent = 'Demo · 本地默认配置预览';
      try {
        const response = await root.fetch('../rules/defaults/stable.json');
        if (!response.ok) throw new Error('默认配置读取失败');
        const config = validate(await response.json());
        version.textContent = `config_version · ${config.config_version}`;
        message.textContent = `稳定期演示：ACOS 目标 ${(config.acos.target * 100).toFixed(0)}%，零订单点击止损 ${config.stop_loss.zero_order_clicks}；仅预览，未保存配置。`;
      } catch (_) { message.textContent = '本地默认配置不可用；未保存配置。'; }
      return;
    }
    heading.textContent = 'Live · 已授权策略版本';
    const panel = get('strategy-live-panel'), select = get('strategy-version-select');
    const fieldsNode = get('strategy-numeric-fields'), save = get('strategy-save-version'), rollback = get('strategy-rollback-version');
    const refresh = get('strategy-refresh-versions'), access = get('strategy-access'), status = get('strategy-operation-status');
    panel.hidden = false;
    let rows = [], memberships = [], selected = null, fields = [], busy = false, locked = false, pending = null, generation = 0;
    function admin(row) { return memberships.some(m => m.store_id === row?.store_id && m.role === 'admin'); }
    function latest(row) { return rows.find(item => scope(item) === scope(row)); }
    function writable(row) {
      if (!row || locked || client.strategies.canWrite !== true || !admin(row)) return false;
      try { compatible(row); return true; } catch (_) { return false; }
    }
    function controls() {
      select.disabled = busy || locked || !rows.length;
      refresh.disabled = busy || locked;
      save.disabled = busy || !writable(selected) || selected.asin != null;
      rollback.disabled = busy || !writable(selected) || latest(selected)?.config_id === selected.config_id;
      for (const { input } of fields) input.disabled = busy || !writable(selected) || selected.asin != null;
    }
    function clear() {
      rows = []; memberships = []; selected = null; fields = []; pending = null;
      fieldsNode.replaceChildren(); select.replaceChildren(); version.textContent = 'config_version · —';
    }
    function render() {
      fieldsNode.replaceChildren(); fields = [];
      if (!selected) { controls(); return; }
      version.textContent = `config_version · ${selected.config_version}`;
      message.textContent = `店铺 ${selected.store_id} · ${stages[selected.product_stage] || selected.product_stage} · 规则 ${selected.rule_version} · ${latest(selected)?.config_id === selected.config_id ? '当前生效版本' : '历史版本'}${selected.asin ? ` · ASIN ${selected.asin}` : ''}`;
      access.textContent = admin(selected) ? (client.strategies.canWrite === true ? '本店管理员：保存和回滚均创建新版本，历史不变。' : '本店管理员：写入网关尚未配置，只读。') : '本店普通成员：只读。';
      if (selected.asin != null) access.textContent += ' ASIN 专属配置可查看或回滚；此页保存仅支持店铺/阶段配置。';
      try { compatible(selected); } catch (error) { access.textContent += ` ${error.message}`; controls(); return; }
      for (const [section, [title, labels]] of Object.entries(groups)) {
        const group = doc.createElement('fieldset'), legend = doc.createElement('legend');
        legend.textContent = title; group.append(legend);
        for (const [key, value] of Object.entries(selected.config[section])) {
          const [labelText, min, max, integer] = labels[key];
          const label = doc.createElement('label'), input = doc.createElement('input');
          label.textContent = labelText;
          input.type = 'number'; input.id = `strategy-value-${section}-${key}`;
          input.min = String(min); input.max = String(max); input.step = integer ? '1' : 'any';
          input.required = true; input.value = String(value); label.htmlFor = input.id;
          label.append(input); group.append(label); fields.push({ section, key, input });
        }
        fieldsNode.append(group);
      }
      controls();
    }
    function options(preferred) {
      select.replaceChildren();
      for (const row of rows) {
        const option = doc.createElement('option'); option.value = row.config_id;
        option.textContent = `${row.store_id} / ${stages[row.product_stage] || row.product_stage}${row.asin ? ` / ${row.asin}` : ''} / ${row.config_version}${latest(row)?.config_id === row.config_id ? '（生效）' : '（历史）'}`;
        select.append(option);
      }
      selected = rows.find(row => row.config_id === preferred) || rows[0] || null;
      select.value = selected?.config_id || ''; render();
    }
    async function load() {
      if (busy || locked) return;
      busy = true; controls(); const epoch = ++generation;
      status.textContent = ''; message.textContent = '正在读取已授权配置和本店角色…';
      try {
        const [configs, permissions] = await Promise.all([client.strategies.list(), client.strategies.permissions()]);
        if (locked || epoch !== generation) return;
        if (!Array.isArray(configs) || !Array.isArray(permissions)
          || permissions.some(m => !uuid(m?.store_id) || !['admin', 'user'].includes(m.role))
          || configs.some(row => !object(row) || !uuid(row.config_id) || !uuid(row.store_id) || !Number.isFinite(Date.parse(row.created_at))))
          throw new Error('策略或权限响应无效');
        memberships = permissions;
        rows = configs.filter(row => memberships.some(m => m.store_id === row.store_id)).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.created_at.localeCompare(a.created_at));
        options(selected?.config_id);
        if (!rows.length) {
          version.textContent = 'config_version · —'; access.textContent = '暂无可编辑的已有策略。';
          message.textContent = '没有可读策略；请先由管理员初始化对应店铺和产品阶段的策略。未保存任何配置。';
        }
      } catch (error) {
        if (locked || epoch !== generation) return;
        clear(); access.textContent = '无法确认授权，已关闭编辑。';
        message.textContent = '策略或权限读取失败；请重试，不显示演示配置。'; client.showError?.(error);
      } finally { busy = false; controls(); }
    }
    async function commit(kind) {
      if (busy || !writable(selected) || (kind === 'save' && selected.asin != null)
        || (kind === 'rollback' && latest(selected)?.config_id === selected.config_id)) return;
      const source = selected;
      let config = clone(source.config);
      try {
        if (kind === 'save') {
          for (const { section, key, input } of fields) {
            if (!input.value.trim()) throw new Error('所有配置数值均必填。');
            config[section][key] = Number(input.value);
          }
          validate(config);
        }
        const signature = JSON.stringify([kind, source.config_id, config]);
        if (!pending || pending.signature !== signature) {
          const id = root.crypto.randomUUID();
          if (!uuid(id)) throw new Error('无法创建配置版本编号。');
          const newVersion = `${source.product_stage}-${id}`;
          config.config_version = newVersion;
          pending = { signature, expected: config, input: kind === 'save'
            ? { store_id: source.store_id, product_stage: source.product_stage, config, config_version: newVersion, rule_version: source.rule_version, config_id: id }
            : { config_id: source.config_id, new_config_id: id, config_version: newVersion } };
        }
        busy = true; controls(); status.textContent = kind === 'save' ? '正在提交新版本…' : '正在创建回滚版本…';
        const request = pending, epoch = generation;
        const result = await client.strategies[kind](clone(request.input));
        if (locked || epoch !== generation) return;
        const id = kind === 'save' ? request.input.config_id : request.input.new_config_id;
        if (!object(result) || result.demo === true || result.persisted === false || result.config_id !== id
          || result.store_id !== source.store_id || result.product_stage !== source.product_stage
          || (result.asin ?? null) !== (source.asin ?? null) || result.config_version !== request.input.config_version
          || result.rule_version !== source.rule_version || !Number.isFinite(Date.parse(result.created_at))
          || !equal(result.config, request.expected)) throw new Error('服务器未返回匹配的持久化配置行。');
        compatible(result);
        rows = [result, ...rows.filter(row => row.config_id !== result.config_id)]
          .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.created_at.localeCompare(a.created_at));
        pending = null; options(result.config_id);
        status.textContent = `${kind === 'save' ? '已保存新版本' : '已创建回滚版本'} ${result.config_version}；后续新任务使用生效版本，历史任务不变。`;
      } catch (error) {
        if (locked) return;
        status.textContent = `未确认${kind === 'save' ? '保存' : '回滚'}成功：${error.message} 保持相同参数重试可复用请求编号，也可刷新核对。`;
        client.showError?.(error);
      } finally { busy = false; controls(); }
    }
    select.addEventListener('change', () => {
      if (busy || locked) return;
      selected = rows.find(row => row.config_id === select.value) || null;
      pending = null; status.textContent = ''; render();
    });
    save.addEventListener('click', () => commit('save'));
    rollback.addEventListener('click', () => commit('rollback'));
    refresh.addEventListener('click', load);
    client.auth?.subscribe(state => {
      if (!['signed_out', 'expired', 'forbidden'].includes(state)) return;
      locked = true; generation++; clear(); controls();
      message.textContent = '会话已失效，请重新登录。'; access.textContent = ''; status.textContent = '';
    });
    await load();
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { validate, boot };
  else root.KWCCStrategyReady = boot();
})(globalThis);
