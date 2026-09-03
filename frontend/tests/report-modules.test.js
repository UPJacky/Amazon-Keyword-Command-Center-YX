'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const artifacts = { rank: 'rank-benchmark.json', negative: 'negative-keywords.json', competitors: 'competitors.json', listing: 'listing-diagnostics.json', optimization: 'optimization-plan.json' };
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.value = ''; this.textContent = ''; this.events = {}; }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, fn) { this.events[key] = fn; }
  get childNodes() { return this.children; }
  remove() {}
}
function descendants(node) { return [node, ...node.children.flatMap(descendants)]; }
async function run(name, data, allowed = true) {
  const nodes = new Map(['main', '.report-sidebar', '#module-body', '#module-metrics', '#module-status'].map(k => [k, new Element('section')]));
  const calls = [];
  const document = {currentScript: {src: 'https://workbench.invalid/report/shared.js'}, body: new Element('body'), createElement: tag => new Element(tag), querySelector: key => nodes.get(key)};
  document.body.dataset.module = name;
  const context = {document, Node:Element, URL, Blob, setTimeout, location:{href:`https://workbench.invalid/report/${name}.html`}, KWCC:{ready:Promise.resolve(allowed), mode:'demo'}, fetch:async url => {calls.push(String(url));return {ok:true,json:async()=>data};}};
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root,'frontend/report/shared.js'),'utf8'), context);
  await vm.runInContext(fs.readFileSync(path.join(root,`frontend/report/${name}.js`),'utf8'), context);
  return {nodes, calls, body:nodes.get('#module-body'), status:nodes.get('#module-status')};
}
for (const [name, artifact] of Object.entries(artifacts)) {
  const data = JSON.parse(fs.readFileSync(path.join(root,'data/golden/market-demo-modules',artifact),'utf8'));
  test(`${name}: real golden fixture renders data and a working filter`, async () => {
    const f = await run(name, data);
    assert.equal(f.calls.length,1);
    assert.match(f.calls[0],new RegExp(artifact.replace('.', '\\.')+'$'));
    assert.doesNotMatch(f.status.textContent,/失败/);
    assert.ok(descendants(f.body).some(el=>el.tagName==='table'), 'must render actual data, not only a summary');
    const buttons=descendants(f.body).filter(el=>el.tagName==='button' && Object.keys(el.dataset).some(k=>k.endsWith('Filter')));
    assert.ok(buttons.length>=3);
    buttons[1].events.click();
    assert.equal(buttons[1].attributes['aria-pressed'],'true');
    assert.equal(buttons[0].attributes['aria-pressed'],'false');
    if(name==='negative') {
      const cautious=buttons.find(el=>el.dataset.negativeFilter==='cautious'); cautious.events.click();
      assert.equal(descendants(f.body).find(el=>el.id==='export-negative').disabled,true);
    }
    if(name==='listing') {
      const pass=buttons.find(el=>el.dataset.listingFilter==='pass'); pass.events.click();
      assert.ok(f.status.textContent.includes(`0 / ${data.checklist.items.length} 项检查`));
    }
    if(name==='competitors') assert.equal(descendants(f.body).filter(el=>el.tagName==='img').length,0,'demo must not load placeholder images');
  });
  test(`${name}: malformed artifact fails clearly; denied identity performs no fetch`, async () => {
    const failed=await run(name, {});
    assert.match(failed.status.textContent,/加载失败/);
    const denied=await run(name,data,false);
    assert.equal(denied.calls.length,0);
    assert.equal(descendants(denied.body).filter(el=>el.tagName==='table').length,0);
  });
}
