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
test('stage asset pin tracks the exact reviewed CSS source',()=>{
 const bytes=Buffer.from(css);
 const blob=createHash('sha1').update('blob '+bytes.length+'\0').update(bytes).digest('hex');
 assert.equal(blob,'d65629a3e35894899a4a3cd983f2499918919030');
 assert.ok(stage.includes(blob));
});

test('compact mobile composer fits short viewport without losing the three panels',()=>{
 assert.match(css,/@media \(max-width:760px\) and \(max-height:860px\)/);
 assert.match(css,/height:max\(220px,calc\(100dvh - 126px\)\)!important/);
 assert.match(css,/min-height:220px!important/);
});
