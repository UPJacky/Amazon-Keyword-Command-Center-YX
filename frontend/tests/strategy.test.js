'use strict';
// Offline VM + tiny DOM: execute the page's real event handlers, never network.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { validate } = require('../strategy.js');
const script = fs.readFileSync(path.join(__dirname, '../strategy.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../strategy.html'), 'utf8');
const defaults = JSON.parse(fs.readFileSync(path.join(__dirname, '../../rules/defaults/stable.json'), 'utf8'));
const copy = value => JSON.parse(JSON.stringify(value));
const store = '11111111-1111-4111-8111-111111111111';
const otherStore = '22222222-2222-4222-8222-222222222222';
const firstId = '33333333-3333-4333-8333-333333333333';
const secondId = '44444444-4444-4444-8444-444444444444';
const user = '55555555-5555-4555-8555-555555555555';
function row(overrides = {}) {
  const config = copy(defaults);
  return { config_id: firstId, store_id: store, asin: null, product_stage: 'stable',
    config_version: config.config_version, rule_version: 'rule-v0.1', config,
    created_by: user, created_at: '2026-09-03T00:00:00.000001+00:00', ...overrides };
}
function history() {
  const old = row(), current = row({ config_id: secondId, config_version: 'stable-current', created_at: '2026-09-03T00:00:00.000002+00:00' });
  current.config.config_version = current.config_version;
  current.config.stop_loss.zero_order_spend = 72;
  return [old, current]; // Intentionally unsorted, same JS millisecond.
}
class Element {
  constructor(tag, id = '') { this.tagName = tag; this.id = id; this.children = []; this.listeners = {}; this.value = ''; this.textContent = ''; this.disabled = false; this.hidden = false; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  async dispatch(name) { return this.listeners[name]?.({ target: this, preventDefault() {} }); }
  set innerHTML(_) { throw new Error('UNSAFE_HTML'); }
}
async function mount(options = {}) {
  const nodes = new Map([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element('div', m[1])]));
  nodes.get('strategy-live-panel').hidden = true;
  for (const id of ['strategy-save-version', 'strategy-rollback-version', 'strategy-refresh-versions', 'strategy-version-select']) nodes.get(id).disabled = true;
  function find(id) {
    const walk = element => element.id === id ? element : element.children.map(walk).find(Boolean);
    return nodes.get(id) || [...nodes.values()].map(walk).find(Boolean);
  }
  const rows = options.rows || [row()], permissions = options.permissions || [{ store_id: store, role: 'admin' }];
  const calls = [], errors = [], listeners = []; let serial = 0;
  const strategies = {
    canWrite: options.canWrite ?? true,
    async list() { calls.push(['list']); return options.list ? options.list() : copy(rows); },
    async permissions() { calls.push(['permissions']); return options.getPermissions ? options.getPermissions() : copy(permissions); },
    async save(input) {
      calls.push(['save', copy(input)]);
      if (options.save) return options.save(input);
      return { ...copy(input), asin: null, created_by: user, created_at: '2026-09-04T00:00:00Z' };
    },
    async rollback(input) {
      calls.push(['rollback', copy(input)]);
      if (options.rollback) return options.rollback(input);
      const source = copy(rows.find(r => r.config_id === input.config_id));
      source.config.config_version = input.config_version;
      return { ...source, config_id: input.new_config_id, config_version: input.config_version, created_by: user, created_at: '2026-09-04T00:00:00Z' };
    },
  };
  const context = vm.createContext({
    KWCC: { ready: Promise.resolve(options.ready ?? true), mode: options.mode || 'live', strategies,
      auth: { subscribe: cb => listeners.push(cb) }, showError: error => errors.push(error.message) },
    document: { querySelector: selector => find(selector.slice(1)), createElement: tag => new Element(tag) },
    crypto: { randomUUID: () => `aaaaaaaa-aaaa-4aaa-8aaa-${String(++serial).padStart(12, '0')}` },
    fetch: async url => { if (options.mode !== 'demo') throw new Error('NETWORK_FORBIDDEN'); calls.push(['fetch', url]); return { ok: true, json: async () => copy(defaults) }; },
  });
  vm.runInContext(script, context, { filename: 'strategy.js' });
  await context.KWCCStrategyReady;
  return { find, calls, errors, strategies, emit: state => listeners.forEach(cb => cb(state)),
    async choose(id) { find('strategy-version-select').value = id; await find('strategy-version-select').dispatch('change'); } };
}
const saves = app => app.calls.filter(c => c[0] === 'save');
const rollbacks = app => app.calls.filter(c => c[0] === 'rollback');

test('all shipped defaults validate; every numeric path rejects bool/null/string/nonfinite/out-of-range', () => {
  const files = fs.readdirSync(path.join(__dirname, '../../rules/defaults')).filter(name => name.endsWith('.json'));
  for (const name of files) validate(JSON.parse(fs.readFileSync(path.join(__dirname, '../../rules/defaults', name), 'utf8')));
  let numericPaths = 0;
  for (const [section, fields] of Object.entries(defaults)) {
    if (typeof fields !== 'object') continue;
    for (const key of Object.keys(fields)) {
      numericPaths++;
      for (const invalid of [true, false, null, '1', NaN, Infinity, -Infinity, -1, 1e20]) {
        const config = copy(defaults); config[section][key] = invalid;
        assert.throws(() => validate(config), undefined, `${section}.${key}=${invalid}`);
      }
      const missing = copy(defaults); delete missing[section][key]; assert.throws(() => validate(missing));
    }
  }
  assert.equal(numericPaths, 16);
});

test('unknown formulas, missing sections, wrong schema/stage, fractional counts and boundary reversals fail', () => {
  const mutations = [
    c => { c.formula = 'acos * 2'; }, c => { c.acos.formula = 2; }, c => { delete c.market; },
    c => { c.schema_version = 'config-1.0'; }, c => { c.product_stage = 'invented'; },
    c => { c.config_version = 'bad version'; }, c => { c.acos.target = 0.5; },
    c => { c.acos.tolerance = 0.5; }, c => { c.evidence.insufficient_clicks_max = 10; },
    c => { c.evidence.preliminary_clicks_min = 21; }, c => { c.evidence.preliminary_orders_min = 3; },
    c => { c.evidence.sufficient_clicks_min = 20.5; }, c => { c.stop_loss.zero_order_clicks = 20.5; },
    c => { c.organic_defense.core_max_rank = 0; }, c => { c.organic_defense.core_max_rank = 1.5; },
  ];
  for (const mutate of mutations) { const config = copy(defaults); mutate(config); assert.throws(() => validate(config)); }
});

test('version list sorts microsecond timestamps and derives field values from selected API row', async () => {
  const app = await mount({ rows: history() });
  assert.equal(app.find('strategy-version-select').value, secondId);
  assert.equal(app.find('strategy-value-stop_loss-zero_order_spend').value, '72');
  assert.equal(app.find('strategy-save-version').disabled, false);
  assert.equal(app.find('strategy-rollback-version').disabled, true);
  await app.choose(firstId);
  assert.equal(app.find('strategy-value-stop_loss-zero_order_spend').value, String(defaults.stop_loss.zero_order_spend));
  assert.equal(app.find('strategy-rollback-version').disabled, false);
});

test('store admin cannot write another store where role is user; canWrite alone never authorizes', async () => {
  const rows = [row(), row({ config_id: secondId, store_id: otherStore })];
  const app = await mount({ rows, permissions: [{ store_id: store, role: 'admin' }, { store_id: otherStore, role: 'user' }] });
  await app.choose(secondId);
  assert.equal(app.find('strategy-save-version').disabled, true);
  assert.equal(app.find('strategy-value-acos-target').disabled, true);
  // Force handler dispatch even though disabled to verify the handler guard.
  await app.find('strategy-save-version').dispatch('click');
  await app.find('strategy-rollback-version').dispatch('click');
  assert.equal(saves(app).length + rollbacks(app).length, 0);
  await app.choose(firstId);
  assert.equal(app.find('strategy-save-version').disabled, false);
});

test('missing gateway, no membership or failed permissions leave no write path', async () => {
  for (const options of [{ canWrite: false }, { permissions: [] }, { getPermissions: async () => { throw new Error('403'); } }]) {
    const app = await mount(options);
    assert.equal(app.find('strategy-save-version').disabled, true);
    await app.find('strategy-save-version').dispatch('click');
    assert.equal(saves(app).length, 0);
  }
});

test('save contract includes only approved parameters and new version, source row stays unchanged', async () => {
  const source = row(), before = copy(source), app = await mount({ rows: [source] });
  app.find('strategy-value-stop_loss-zero_order_spend').value = '123.45';
  await app.find('strategy-save-version').dispatch('click');
  const input = saves(app)[0][1];
  assert.deepEqual(Object.keys(input).sort(), ['store_id', 'product_stage', 'config', 'config_version', 'rule_version', 'config_id'].sort());
  assert.equal(input.store_id, store); assert.equal(input.product_stage, 'stable');
  assert.equal(input.rule_version, source.rule_version);
  assert.equal(input.config_version, input.config.config_version);
  assert.notEqual(input.config_id, source.config_id);
  assert.equal(input.config.stop_loss.zero_order_spend, 123.45);
  assert.deepEqual(source, before);
  assert.match(app.find('strategy-operation-status').textContent, /已保存新版本/);
  assert.equal(app.find('strategy-version-select').children.length, 2);
});

test('save timeout then same-content retry reuses exact request UUID and version', async () => {
  let count = 0;
  const app = await mount({ save: async input => {
    if (++count === 1) throw new Error('timeout');
    return { ...copy(input), asin: null, created_by: user, created_at: '2026-09-04T00:00:00Z' };
  } });
  await app.find('strategy-save-version').dispatch('click');
  assert.match(app.find('strategy-operation-status').textContent, /未确认保存成功/);
  await app.find('strategy-save-version').dispatch('click');
  assert.deepEqual(saves(app)[0][1], saves(app)[1][1]);
  assert.match(app.find('strategy-operation-status').textContent, /已保存新版本/);
});

test('changed content after failure gets a new idempotency key', async () => {
  const app = await mount({ save: async () => { throw new Error('timeout'); } });
  await app.find('strategy-save-version').dispatch('click');
  app.find('strategy-value-stop_loss-zero_order_spend').value = '99';
  await app.find('strategy-save-version').dispatch('click');
  assert.notEqual(saves(app)[0][1].config_id, saves(app)[1][1].config_id);
});

test('blank and invalid numeric entries make no save call', async () => {
  for (const value of ['', 'NaN', 'Infinity', '-1', '1.5']) {
    const app = await mount(); app.find('strategy-value-stop_loss-zero_order_clicks').value = value;
    await app.find('strategy-save-version').dispatch('click');
    assert.equal(saves(app).length, 0, value);
    assert.match(app.find('strategy-operation-status').textContent, /未确认/);
  }
});

test('rollback contract copies historical config and ignores edited form, source immutable', async () => {
  const rows = history(), before = copy(rows), app = await mount({ rows });
  await app.choose(firstId);
  app.find('strategy-value-stop_loss-zero_order_spend').value = '999';
  await app.find('strategy-rollback-version').dispatch('click');
  const input = rollbacks(app)[0][1];
  assert.deepEqual(Object.keys(input).sort(), ['config_id', 'new_config_id', 'config_version'].sort());
  assert.equal(input.config_id, firstId); assert.notEqual(input.new_config_id, firstId);
  assert.deepEqual(rows, before);
  assert.equal(app.find('strategy-value-stop_loss-zero_order_spend').value, String(defaults.stop_loss.zero_order_spend));
  assert.match(app.find('strategy-operation-status').textContent, /已创建回滚版本/);
});

test('rollback retry reuses ID and cannot display demo/missing response as persistence', async () => {
  const app = await mount({ rows: history(), rollback: async () => ({ demo: true, persisted: false }) });
  await app.choose(firstId);
  await app.find('strategy-rollback-version').dispatch('click');
  await app.find('strategy-rollback-version').dispatch('click');
  assert.deepEqual(rollbacks(app)[0][1], rollbacks(app)[1][1]);
  assert.equal(app.find('strategy-version-select').children.length, 2);
  assert.match(app.find('strategy-operation-status').textContent, /未确认回滚成功/);
});

test('malformed, mismatched and demo save responses never show saved success', async () => {
  for (const reply of [() => undefined, () => ({ demo: true }), input => ({ ...copy(input), created_at: 'invalid' }),
    input => ({ ...copy(input), created_at: '2026-09-04T00:00:00Z', config: defaults }),
    input => ({ ...copy(input), created_at: '2026-09-04T00:00:00Z', store_id: otherStore })]) {
    const app = await mount({ save: async input => reply(input) });
    await app.find('strategy-save-version').dispatch('click');
    assert.match(app.find('strategy-operation-status').textContent, /未确认保存成功/);
    assert.equal(app.find('strategy-version-select').children.length, 1);
  }
});

test('empty and failed live reads never fetch demo defaults or invent saved data', async () => {
  for (const options of [{ rows: [] }, { list: async () => { throw new Error('offline'); } }]) {
    const app = await mount(options);
    assert.equal(app.calls.some(c => c[0] === 'fetch'), false);
    assert.equal(app.find('strategy-save-version').disabled, true);
    assert.equal(app.find('strategy-version-select').children.length, 0);
    assert.match(app.find('strategy-local-values').textContent, /没有可读策略|读取失败/);
  }
});

test('unknown config field/rule and mismatched row metadata are not editable', async () => {
  const cases = [row({ rule_version: 'attacker-rule' }), row({ product_stage: 'growth' }), row({ config_version: 'different' })];
  const unknown = row(); unknown.config.formula = 10; cases.push(unknown);
  for (const source of cases) {
    const app = await mount({ rows: [source] });
    assert.equal(app.find('strategy-save-version').disabled, true);
    assert.equal(app.find('strategy-numeric-fields').children.length, 0);
  }
});

test('a non-stable row edits its actual stage without loading stable template', async () => {
  const source = row({ product_stage: 'growth' }); source.config.product_stage = 'growth'; source.config.acos.target = 0.12;
  const app = await mount({ rows: [source] });
  assert.equal(app.find('strategy-value-acos-target').value, '0.12');
  await app.find('strategy-save-version').dispatch('click');
  assert.equal(saves(app)[0][1].product_stage, 'growth');
  assert.equal(saves(app)[0][1].config.product_stage, 'growth');
  assert.equal(app.calls.some(c => c[0] === 'fetch'), false);
});

test('ASIN scoped existing row never silently becomes a store-wide save', async () => {
  const app = await mount({ rows: [row({ asin: 'B012345678' })] });
  assert.equal(app.find('strategy-save-version').disabled, true);
  await app.find('strategy-save-version').dispatch('click');
  assert.equal(saves(app).length, 0);
});

test('pending requests prevent double submission; expired session ignores late response', async () => {
  let resolve;
  const app = await mount({ save: input => new Promise(done => { resolve = () => done({ ...copy(input), asin: null, created_by: user, created_at: '2026-09-04T00:00:00Z' }); }) });
  const first = app.find('strategy-save-version').dispatch('click');
  assert.equal(app.find('strategy-save-version').disabled, true);
  await app.find('strategy-save-version').dispatch('click'); assert.equal(saves(app).length, 1);
  app.emit('expired'); resolve(); await first;
  assert.equal(app.find('strategy-version-select').children.length, 0);
  assert.equal(app.find('strategy-save-version').disabled, true);
  assert.equal(app.find('strategy-operation-status').textContent, '');
});

test('demo path stays an explicit unsaved preview; new buttons have independent IDs', async () => {
  const app = await mount({ mode: 'demo' });
  assert.equal(app.find('strategy-live-panel').hidden, true);
  assert.deepEqual(app.calls, [['fetch', '../rules/defaults/stable.json']]);
  assert.match(app.find('strategy-local-values').textContent, /未保存配置/);
  assert.doesNotMatch(html, /data-static-submit|data-open-drawer|<textarea/);
  assert.equal((await mount({ ready: false })).calls.length, 0);
});
