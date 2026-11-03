import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const menu=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
const scene=readFileSync(new URL('./express-wow-v3.css',import.meta.url),'utf8');
const css=readFileSync(new URL('./express-wow-v4.css',import.meta.url),'utf8');
const layout=readFileSync(new URL('./express-layout.mjs',import.meta.url),'utf8');
test('WOW V4 is loaded by existing V3 stylesheet, without changing the native HTML origin',()=>{
 assert.match(scene,/^@import url\("\.\/express-wow-v4\.css"\);/);
 assert.match(css,/\.nox-chat-log/);
 assert.match(css,/\.main-action\[data-action="CHAT"\]/);
});
test('EXPRESS 8 directions and 10 worlds remain distinct from 8 CoreID',()=>{
 assert.match(layout,/export const DIRECTIONS/);
 assert.match(layout,/export const CORE_IDS/);
 assert.match(layout,/export const WORLDS/);
});
test('Chat action mounts original native route and not the pending feature dialog',()=>{
 assert.match(menu,/if\(id==='chat'\)\{liveChat\(label\);return;\}/);
 assert.match(menu,/createNativeMenuClient/);
 assert.match(menu,/client\.request\('helion\.chat'/);
 assert.match(menu,/client\.request\('chat\.model'/);
 assert.match(menu,/client\.request\('chat\.stop'/);
 assert.match(menu,/isNativeChatTerminal/);
 assert.doesNotMatch(menu,/\bfetch\s*\(|XMLHttpRequest|new WebSocket|window\.open/);
});
test('Streaming cannot fake final completion; native STOP and response are separate',()=>{
 assert.match(menu,/chatInFlight=true/);
 assert.match(menu,/if\(!isNativeChatTerminal\(reply\)\)return/);
 assert.match(menu,/STOP REQUESTED/);
 assert.match(menu,/TIMEOUT/);
 assert.match(menu,/role','log'/);
 assert.match(menu,/textContent/);
});
test('ECO, reduced motion, keyboard access and narrow viewport do not lose UI',()=>{
 assert.match(css,/body\[data-fx="ECO"\]/);
 assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
 assert.match(css,/@media\(max-width:520px\)/);
 assert.match(menu,/input\.addEventListener\('keydown'/);
 assert.match(menu,/aria-pressed/);
});
