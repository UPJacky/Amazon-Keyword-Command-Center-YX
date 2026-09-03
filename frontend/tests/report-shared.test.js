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
function fixture({allowed = true, mode = 'demo', local = false, ok = true} = {}) {
  const nodes = new Map(['main', '.report-sidebar', '#module-body', '#module-metrics', '#module-status'].map(k => [k, new Element('section')]));
  const base = `https://workbench.invalid/project/${local ? 'frontend/' : ''}report/`;
  const calls = [];
  const context = { Node: Element, URL, location: {href: base + 'rank.html?task=t-123&ignored=secret'},
    document: {currentScript: {src: base + 'shared.js'}, body: {dataset: {module: 'rank'}}, createElement: tag => new Element(tag), querySelector: key => nodes.get(key)},
    KWCC: {ready: Promise.resolve(allowed), mode},
    fetch: async url => { calls.push(String(url)); return {ok, json: async () => ({rows: []})}; },
  };
  vm.runInNewContext(source, context);
  return {ui: context.ReportUI, nodes, calls};
}
test('denied identity and live mode never fetch demo artifacts', async () => {
  for (const input of [{allowed:false}, {mode:'live'}, {mode:'blocked'}]) {
    const f = fixture(input);
    assert.equal(await f.ui.ready, false);
    await assert.rejects(f.ui.load('rank-benchmark.json'));
    assert.deepEqual(f.calls, []);
    if (input.mode) assert.match(f.nodes.get('main').children[0].textContent, /不显示演示数据/);
  }
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
test('six independent navigation URLs preserve task but not unrelated query values', async () => {
  const f = fixture(); await f.ui.ready;
  const nav = f.nodes.get('.report-sidebar').children.at(-1);
  assert.equal(nav.children.length, 6);
  const urls = nav.children.map(link => new URL(link.href));
  assert.equal(new Set(urls.map(url => url.pathname)).size, 6);
  assert.ok(urls.every(url => url.search === '?task=t-123'));
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
