import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
const loader=readFileSync(new URL('./express-wow-three.mjs',import.meta.url),'utf8');
const scene=readFileSync(new URL('./nox-wow-scene.js',import.meta.url),'utf8');
const css=readFileSync(new URL('./express-wow-three.css',import.meta.url),'utf8');
test('Three original is mounted into existing menu after navigation',()=>{
 assert.match(html,/express-wow-three\.mjs/);
 assert.match(html,/express-wow-three\.css/);
 assert.ok(html.indexOf('menu.js')<html.indexOf('express-wow-three.mjs'));
 assert.match(loader,/\.universe/);
 assert.match(loader,/three\.min\.js/);
 assert.match(loader,/import\('\.\/nox-wow-scene\.js'\)/);
});
test('MAX-only, local, motion safe, disposes renderer',()=>{
 for(const s of ['data-fx','MAX','prefers-reduced-motion','saveData','visibilitychange','pagehide','MutationObserver','wowThreeState']) assert.ok(loader.includes(s),s);
 for(const s of ['renderer.dispose()','forceContextLoss','geometry.dispose()','material.dispose()','cancelAnimationFrame','ResizeObserver','visibilitychange','data-fx']) assert.ok(scene.includes(s),s);
 assert.match(css,/prefers-reduced-motion/);
 assert.match(css,/pointer-events:none/);
 assert.doesNotMatch(loader,/https?:\/\/|fetch\s*\(|chrome\.webview|selfbuilder\.propose/);
});
test('Scene uses deterministic bounded geometry',()=>{
 assert.match(scene,/count=96/);
 assert.match(scene,/new THREE\.Points\(/);
 assert.match(scene,/new THREE\.WebGLRenderer\(/);
 assert.doesNotMatch(scene,/Math\.random\s*\(/);
});
