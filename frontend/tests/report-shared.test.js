'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../report/shared.js'), 'utf8');
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attributes = {}; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
}
function fixture({allowed = true, mode = 'demo', local = false, ok = true, moduleData} = {}) {
  const nodes = new Map(['main', '.report-sidebar', '#module-body', '#module-metrics', '#module-status'].map(k => [k, new Element('section')]));
  const base = `https://workbench.invalid/project/${local ? 'frontend/' : ''}report/`;
  const calls = [];
  const reportCalls = [];
  const context = { Node: Element, URL, location: {href: base + 'rank.html?task=t-123&run=r-456&ignored=secret'},
    document: {currentScript: {src: base + 'shared.js'}, body: {dataset: {module: 'rank'}}, createElement: tag => new Element(tag), querySelector: key => nodes.get(key)},
    KWCC: {ready: Promise.resolve(allowed), mode, reports: {async readModule(...args) {
      reportCalls.push(args);
      if (moduleData) return moduleData;
      const error = new Error('unbound artifact'); error.code = 'REPORT_NOT_GENERATED'; throw error;
    }}},
    fetch: async url => { calls.push(String(url)); return {ok, json: async () => ({rows: []})}; },
  };
  vm.runInNewContext(source, context);
  return {ui: context.ReportUI, nodes, calls, reportCalls};
}
test('denied identity and blocked mode never fetch artifacts', async () => {
  for (const input of [{allowed:false}, {mode:'blocked'}]) {
    const f = fixture(input);
    assert.equal(await f.ui.ready, false);
    await assert.rejects(f.ui.load('rank-benchmark.json'));
    assert.deepEqual(f.calls, []);
    if (input.mode) assert.match(f.nodes.get('main').children[0].textContent, /不显示演示数据/);
  }
});
test('live modules call only the bound client and explicitly show not generated without demo data', async () => {
  const f = fixture({mode:'live'});
  assert.equal(await f.ui.ready, true);
  for (const name of ['rank-benchmark.json', 'negative-keywords.json', 'competitors.json', 'listing-diagnostics.json', 'optimization-plan.json']) {
    await assert.rejects(f.ui.load(name), error => { f.ui.showError(error); return error.code === 'REPORT_NOT_GENERATED'; });
    assert.match(f.nodes.get('#module-status').textContent, /真实报告尚未生成/);
    assert.match(f.nodes.get('#module-body').children[0].textContent, /尚未生成可读取的真实报告/);
    assert.equal(f.nodes.get('#module-metrics').children.length, 0);
  }
  assert.deepEqual(f.calls, []);
  assert.deepEqual(f.reportCalls[0], ['t-123', 'r-456', 'rank-benchmark.json']);
  await assert.rejects(f.ui.load('../../private.json'));
  assert.equal(f.reportCalls.length, 5);
});

test('live module passes through authorized bundle content without a fixture fetch', async () => {
  const moduleData = { rows: [{ keyword: 'private bundle', my_organic_rank: null }] };
  const f = fixture({mode:'live', moduleData});
  assert.deepEqual(await f.ui.load('rank-benchmark.json'), moduleData);
  assert.deepEqual(f.calls, []);
  assert.deepEqual(f.reportCalls, [['t-123', 'r-456', 'rank-benchmark.json']]);
});

test('canonical and local source resolve the same reviewed fixture root', async () => {
  for (const local of [true, false]) {
    const f = fixture({local});
    await f.ui.load('rank-benchmark.json');
    assert.equal(f.calls[0], 'https://workbench.invalid/project/data/golden/market-demo-modules/rank-benchmark.json');
    await assert.rejects(f.ui.load('../../private.json'));
    assert.equal(f.calls.length, 1);
  }
});
test('six independent navigation URLs preserve task and run but not unrelated query values', async () => {
  const f = fixture(); await f.ui.ready;
  const nav = f.nodes.get('.report-sidebar').children.at(-1);
  assert.equal(nav.children.length, 6);
  const urls = nav.children.map(link => new URL(link.href));
  assert.equal(new Set(urls.map(url => url.pathname)).size, 6);
  assert.ok(urls.every(url => url.search === '?task=t-123&run=r-456'));
  assert.equal(nav.children[1].attributes['aria-current'], 'page');
});
test('null is not zero; tables keep empty state and render untrusted text as text', () => {
  const f = fixture();
  assert.equal(f.ui.number(null), '—'); assert.equal(f.ui.number(0), '0');
  assert.equal(f.ui.percent(null), '—'); assert.equal(f.ui.percent(0), '0.0%');
  assert.equal(f.ui.money(null), '—'); assert.equal(f.ui.number(false), '—');
  const payload = '<img src=x onerror=alert(1)>';
  const table = f.ui.table(['搜索词'], [[payload]]).children[0];
  const cell = table.children[1].children[0].children[0];
  assert.equal(cell.textContent, payload); assert.equal(cell.children.length, 0);
  assert.equal(f.ui.table(['a', 'b'], []).children[0].children[1].children[0].children[0].colSpan, 2);
});
test('HTTP failure rejects; explicit failure display replaces stale data', async () => {
  const f = fixture({ok:false});
  await assert.rejects(f.ui.load('competitors.json'));
  f.ui.showError(new Error('private detail never shown'));
  assert.equal(f.nodes.get('#module-status').attributes.role, 'alert');
  assert.doesNotMatch(f.nodes.get('#module-body').children[0].textContent, /private detail/);
});
