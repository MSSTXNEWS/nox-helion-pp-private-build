import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
const adapter=readFileSync(new URL('./nox-holo-motion-v7.mjs',import.meta.url),'utf8');
const css=readFileSync(new URL('../nox-holo-motion-v7.css',import.meta.url),'utf8');
test('Original OneHost actions remain owned by the existing menu',()=>{
 assert.match(html,/src="menu.js"/);assert.match(html,/src="nox-holo-motion-v7.mjs"/);
 assert.match(html,/href="\.\.\/nox-holo-motion-v7.css"/);
 assert.doesNotMatch(adapter,/fetch\(|XMLHttpRequest|postMessage|invoke\(|send\(/);
});
test('D02 isolated: HUD mounted only in original MENU shell',()=>{
 assert.match(adapter,/querySelector\('\.shell'\)/);
 assert.match(adapter,/data-nox-owner-verified/);
 assert.doesNotMatch(adapter,/textContent\s*=/);
});
test('Motion respects reduced motion and mode',()=>{
 assert.match(adapter,/data-fx/);assert.match(adapter,/visibilitychange/);
 assert.match(css,/prefers-reduced-motion:reduce/);
 assert.match(css,/data-nox-motion="off"/);
});
test('No synthetic learning values or model-side changes',()=>{
 assert.doesNotMatch(adapter,/Math\.random|setInterval|localStorage|checkpoint|loss\s*=/i);
});
