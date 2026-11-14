/** ACTIVATOR-WORM source gate: one trusted WebView2 menu; no fake downloads. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const src=readFileSync(new URL('./onehost-menu-bindings.mjs',import.meta.url),'utf8');
test('only native owner dispatches activation',()=>{
  assert.match(src,/selfbuilder\.activator\.status/);
  assert.match(src,/selfbuilder\.a1\.boot/);
  assert.match(src,/selfbuilder\.a1\.tick/);
  assert.match(src,/client\.request\('chat\.commands',\{action:'selfbuilder\.activator\.status'\}\)/);
});
test('download shown only after reviewed approval',()=>{
  assert.match(src,/item\.download_eligible===true/);
  assert.match(src,/'models\.pull','modelTag',item\.tag/);
  assert.match(src,/'browser\.open','url',item\.official_page/);
});
test('first patch limited and owner controlled',()=>{
  assert.match(src,/selfbuilder\.propose/);
  assert.match(src,/SourceLock/);
  assert.match(src,/регрессионный тест/);
});
