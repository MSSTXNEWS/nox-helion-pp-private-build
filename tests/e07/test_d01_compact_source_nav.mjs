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

test('D01 MODELS guards original native owner after WebView2 disappears during navigation',()=>{
 const start=source.indexOf("nav.addEventListener('click',event=>{");
 const end=source.indexOf("\n// Read-only original A1",start);
 assert.ok(start>=0&&end>start,'actual source handler available');
 const handlerSource=source.slice(start,end);
 for(const action of ['MODELS','INSTALL']){
  let fn,active=false,online=true,reads=0,invoked=0,prevented=false;
  const state={textContent:''};
  const owner={tagName:'BUTTON',isConnected:true,disabled:false,
   getClientRects(){return [1]},focus(){doc.activeElement=owner},click(){invoked++}};
  const primary={getClientRects(){return [1]},closest(){return primary},
   getAttribute(k){return k==='data-nox-primary'?action:null}};
  const navigation={click(){active=true;online=false}};
  const doc={activeElement:null,querySelectorAll(selector){
   if(selector==='.nav button[data-screen="control"]')return [navigation];
   if(selector==='button#model-center'&&action==='MODELS')return [owner];
   if(selector==='button#pc-install'&&action==='INSTALL')return [owner];
   return [];
  },getElementById(id){return id==='control'?{classList:{contains:key=>key==='active'&&active}}:null}};
  const nav={contains(){return true},addEventListener(kind,callback){
   assert.equal(kind,'click');fn=callback}};
  Function('nav','state','document','originalPrimaryButtons','verifiedOriginalPrimaryDock',
   'originalInstallTransportPresent','originalNavigationAllowed','visibleOriginalOwnerTarget',
   'findOriginalControl','findOriginalScreen',handlerSource)(
   nav,state,doc,[primary],()=>true,()=>{reads++;return online},()=>true,()=>true,()=>null,()=>null);
  fn({target:primary,isTrusted:true,preventDefault(){prevented=true}});
  assert.equal(invoked,0,action+': native owner invoked on disconnected bridge');
  assert.equal(reads,2,action+': WebView2 not rechecked after navigation');
  assert.equal(prevented,true,action+': event default not suppressed');
  assert.match(state.textContent,/HOLD/,action+': unsupported PASS on dead bridge');
 }
});
