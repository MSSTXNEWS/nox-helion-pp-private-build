import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
const script=readFileSync(new URL('./express-wow-v3.mjs',import.meta.url),'utf8');
const css=readFileSync(new URL('./express-wow-v3.css',import.meta.url),'utf8');
test('WOW V3 loads as additive layer after main menu and V2',()=>{
 assert.ok(html.indexOf('menu.js')<html.indexOf('express-wow-v3.mjs'));
 assert.ok(html.indexOf('express-wow-v2.mjs')<html.indexOf('express-wow-v3.mjs'));
 assert.match(html,/express-wow-v3\.css/);
});
test('No network, duplicate OneHost, selfbuilder, fake graphics metrics or privileged actions',()=>{
 assert.doesNotMatch(script,/\bfetch\s*\(|XMLHttpRequest|WebSocket|chrome\.webview|selfbuilder\.propose|Math\.random|eval\s*\(/);
 assert.match(script,/aria-hidden/);
 assert.match(script,/stage\.dataset\.wowV3==='1'/);
 assert.match(script,/stage\.dataset\.wowV3='1'/);
});
test('Capped paint loop, ECO, system reduced motion, visibility and teardown',()=>{
 for(const token of ['requestAnimationFrame','cancelAnimationFrame','devicePixelRatio','data-fx','visibilitychange','prefers-reduced-motion','pagehide','MutationObserver'])
 assert.ok(script.includes(token),token);
 assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
 assert.match(css,/body\[data-fx="ECO"\]/);
 assert.match(css,/body\[data-fx="MAX"\]/);
});
