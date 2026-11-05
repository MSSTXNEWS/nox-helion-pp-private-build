// D01: run with node --test tests/e07/test_d01_compact_source_nav.mjs
// Actual source-derived V8 contracts; not a Windows/UIA/NSIS acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve, dirname} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const source=readFileSync(resolve(root,'coordination/express/stage_original_five_primary.py'),'utf8');
const builder=readFileSync(resolve(root,'coordination/e06/build_onehost_installer.ps1'),'utf8');
const matches=source.match(/function originalNavigationAllowed\(button\)\{[\s\S]*?\n\}/);
assert.ok(matches,'original navigation helper is part of the immutable stage source');
const originalNavigationAllowed=Function(matches[0]+';return originalNavigationAllowed;')();
const candidate=(changes={})=>({tagName:'BUTTON',isConnected:true,disabled:false,
 matches:()=>false,getAttribute:()=>null,closest:()=>null,
 getClientRects:()=>[],...changes});
test('compact 320/390: collapsed CSS-only R11 navigation still works',()=>{
 assert.equal(originalNavigationAllowed(candidate()),true);
});
test('no synthetic privileged action from disabled or hidden authority',()=>{
 assert.equal(originalNavigationAllowed(candidate({disabled:true})),false);
 assert.equal(originalNavigationAllowed(candidate({matches:()=>true})),false);
 assert.equal(originalNavigationAllowed(candidate({getAttribute:k=>k==='aria-disabled'?'true':null})),false);
 assert.equal(originalNavigationAllowed(candidate({closest:()=>({})})),false);
 assert.equal(originalNavigationAllowed(candidate({isConnected:false})),false);
 assert.equal(originalNavigationAllowed(candidate({tagName:'DIV'})),false);
 assert.equal(originalNavigationAllowed(null),false);
});
test('original five routes retain exact nav/owner gate separation',()=>{
 assert.match(source,/if\(!originalNavigationAllowed\(navControl\)\|\|matches\.length!==1\|\|/);
 assert.match(source,/!originalNavigationAllowed\(menuEntries\[0\]\)/);
 assert.match(source,/if\(original\.tagName==='BUTTON'&&!originalNavigationAllowed\(original\)\)/);
 assert.match(source,/!visibleOriginalOwnerTarget\(invokeMatches\[0\]\)/);
 assert.match(source,/!event\.isTrusted\)return;/);
});
test('NSIS builder pins this exact reviewed D02 source blob',()=>{
 const bytes=Buffer.from(source,'utf8');
 const gitBlob=createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex');
 assert.ok(builder.includes("@{path=$primaryOwner;sha='"+gitBlob+"'}"));
});
