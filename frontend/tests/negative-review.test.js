'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.events = {}; this.value = ''; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute() {}
  addEventListener(name, fn) { this.events[name] = fn; }
  click() { return this.events.click?.(); }
  remove() {}
}
const walk = node => [node, ...node.children.flatMap(walk)];
const row = (keyword, extra = {}) => ({ keyword, negative_status: 'exact_negative_candidate', export_eligible: true, relevance: 'unrelated', orders: 0, clicks: 30, spend: 60, ...extra });
const fixture = extra => ({ exact_negative: [], phrase_negative: [], cautious: [], pending_confirmation: [], protected_converted: [], low_cvr_high_spend: [], ...extra });
async function run(data, allowed = true, clipboardFails = false) {
  const body = new Element('main'), status = new Element('p');
  const copies = [], blobs = []; let loads = 0;
  const ui = { ready: Promise.resolve(allowed), load: async () => { loads++; return data; },
    el: (tag, text) => { const el = new Element(tag); if (text !== undefined) el.textContent = String(text); return el; },
    text: value => String(value ?? '—'), number: String, percent: String, setMetrics() {}, statusPrefix: () => 'partial',
    table: (headers, rows) => { const el = new Element('table'); el.rows = rows; return el; }, showError: () => { body.replaceChildren(); status.textContent = 'error'; } };
  const context = { window: { ReportUI: ui }, document: { querySelector: key => key === '#module-body' ? body : status, body: new Element('body') },
    navigator: { clipboard: { writeText: async text => { if (clipboardFails) throw Error(); copies.push(text); } } },
    Blob, URL: { createObjectURL: blob => { blobs.push(blob); return 'blob:test'; }, revokeObjectURL() {} }, setTimeout: fn => fn() };
  await vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../report/negative.js'), 'utf8'), context);
  return { body, status, copies, blobs, loads, find: id => walk(body).find(el => el.id === id) };
}
test('JSON, exact and phrase text share eligibility and filter scope', async () => {
  const f = await run(fixture({ exact_negative: [row('red light')], phrase_negative: [row('blue light', { negative_status: 'phrase_negative_candidate' })] }));
  await f.find('copy-exact_negative').click(); await f.find('copy-phrase_negative').click();
  assert.deepEqual(f.copies, ['red light', 'blue light']);
  f.find('export-negative').click();
  const payload = JSON.parse(await f.blobs[0].text());
  assert.equal(payload.candidates.length, 2); assert.equal(payload.write_back, false);
  const search = walk(f.body).find(el => el.type === 'search'); search.value = 'blue'; search.events.input();
  assert.equal(f.find('copy-exact_negative').disabled, true);
  assert.equal(f.find('negative-text-phrase_negative').value, 'blue light');
});
test('unsafe, duplicate, old and malformed rows never enter any output', async () => {
  const f = await run(fixture({ exact_negative: [row('safe'), row('duplicate'), row('DUPLICATE'), row('converted', { orders: 1 }), row('old', { export_eligible: undefined }), row('conflict', { phrase_conflict_keywords: ['protected'] }), row('bad conflict', { phrase_conflict_keywords: 'bad' }), row('two\nlines'), row('pending'), row('related', { relevance: 'related' }), row('false', { export_eligible: 'true' })], pending_confirmation: [row('pending', { negative_status: 'pending_confirmation' })] }));
  assert.equal(f.find('negative-text-exact_negative').value, 'safe');
  f.find('export-negative').click(); assert.equal(JSON.parse(await f.blobs[0].text()).candidates.length, 1);
  assert.equal(walk(f.body).some(el => el.type === 'checkbox'), false);
});
test('denied access, null data, malformed optional bucket and empty reports fail closed', async () => {
  const denied = await run(fixture(), false); assert.equal(denied.loads, 0); assert.equal(denied.find('export-negative'), undefined);
  for (const data of [null, fixture({ protected_converted: 'bad' })]) assert.equal((await run(data)).status.textContent, 'error');
  assert.equal((await run(fixture())).find('export-negative').disabled, true);
});
test('clipboard rejection keeps readonly text available for manual copying', async () => {
  const f = await run(fixture({ exact_negative: [row('safe')] }), true, true);
  await f.find('copy-exact_negative').click();
  assert.equal(f.find('negative-text-exact_negative').value, 'safe');
  assert.ok(walk(f.body).some(el => el.textContent.includes('手动选择复制')));
});
