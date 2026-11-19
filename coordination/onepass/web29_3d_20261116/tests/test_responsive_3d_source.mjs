import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const css=readFileSync(new URL('../site/nox-cinematic-accessibility-3d.css',import.meta.url),'utf8');
const stage=readFileSync(new URL('../integration/stage_original_3d.py',import.meta.url),'utf8');
test('tablet Resonance keeps a nonzero message track and bounded telemetry row',()=>{
 assert.match(css,/@media \(min-width:761px\) and \(max-width:1199px\)/);
 assert.match(css,/grid-template-rows:minmax\(260px,1fr\) minmax\(80px,135px\)!important/);
 assert.match(css,/grid-column:2!important;grid-row:1!important/);
 assert.match(css,/grid-column:1\/-1!important;grid-row:2!important/);
 assert.match(css,/max-height:135px!important;overflow:auto!important/);
});
test('compact desktop telemetry stays in the original third column',()=>{
 assert.match(css,/@media \(min-width:1200px\) and \(max-width:1399px\)/);
 assert.match(css,/grid-column:3!important;grid-row:1!important/);
});
test('preserve earlier reduced-motion and original D02 source locks',()=>{
 assert.match(css,/prefers-reduced-motion: reduce/);
 for(const sha of ['124a5d341059eb1070adcf58640657aa471ea4888e4409101503ecaa9337f952',
 '3aced1774354b6212b665ef40514e78fb7660a3319fd346c4b12bbf277a39d38'])assert.ok(stage.includes(sha));
});
test('stage asset pin tracks the CURRENT Git-reviewed CSS and refuses stale responsive source',()=>{
 const bytes=Buffer.from(css);
 const blob=createHash('sha1').update('blob '+bytes.length+'\0').update(bytes).digest('hex');
 assert.equal(blob,'3c60c6f4499cb0095291297f3e5fb628de6e1fc8');
 assert.ok(stage.includes(blob));
});

test('compact mobile composer fits short viewport without losing the three panels',()=>{
 assert.match(css,/@media \(max-width:760px\) and \(max-height:860px\)/);
 assert.match(css,/height:max\(220px,calc\(100dvh - 126px\)\)!important/);
 assert.match(css,/min-height:220px!important/);
});

test('short desktop keeps all three original panels and a scrollable conversation',()=>{
 assert.match(css,/@media \(min-width:1200px\) and \(max-height:600px\)/);
 assert.match(css,/height:max\(260px,calc\(100dvh - 175px\)\)!important/);
 assert.match(css,/grid-template-rows:minmax\(0,1fr\)!important/);
 assert.match(css,/\.chat-layout > \.chat-conversation\s*\{\s*grid-column:2!important;grid-row:1!important;/);
 assert.match(css,/\.chat-layout > \.chat-telemetry-panel\s*\{\s*grid-column:3!important;grid-row:1!important;/);
 assert.match(css,/flex:1 1 0!important;min-height:0!important;overflow:auto!important/);
});

test('short landscape tablet CSS keeps message stream and command dock visible',()=>{
 assert.ok(css.includes('@media (min-width:761px) and (max-width:1199px) and (min-height:420px) and (max-height:540px)'));
 assert.ok(css.includes('height:max(220px,calc(100dvh - 183px))!important'));
 assert.ok(css.includes('grid-template-rows:minmax(0,1fr) 56px!important'));
 assert.ok(css.includes('height:56px!important;min-height:0!important;max-height:56px!important'));
 assert.ok(css.includes('flex:1 1 0!important;min-height:0!important;overflow:auto!important'));
});


test('short 400px landscape tablet keeps all panels and command area on screen',()=>{
 assert.ok(css.includes('@media (min-width:761px) and (max-width:1199px) and (min-height:400px) and (max-height:419px)'));
 assert.ok(css.includes('height:max(230px,calc(100dvh - 170px))!important'));
 assert.ok(css.includes('grid-template-rows:minmax(0,1fr) 40px!important'));
 assert.ok(css.includes('height:40px!important;min-height:0!important;max-height:40px!important'));
 assert.ok(css.includes('@media (min-width:960px) and (max-width:1199px) and (min-height:400px) and (max-height:419px)'));
 assert.ok(css.includes('height:max(220px,calc(100dvh - 180px))!important'));
});

test('1200-1399px compact desktop removes remaining 5-40px overflow',()=>{
 assert.ok(css.includes('@media (min-width:1200px) and (max-width:1399px) and (min-height:400px) and (max-height:600px)'));
 assert.ok(css.includes('height:max(200px,calc(100dvh - 180px))!important'));
 assert.ok(stage.includes('3c60c6f4499cb0095291297f3e5fb628de6e1fc8'));
});
