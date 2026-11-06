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

test('D01 MODELS and LEARN preserve original owner and HOLD on synchronous owner exception',()=>{
 const start=source.indexOf("nav.addEventListener('click',event=>{");
 const end=source.indexOf("\n// Read-only original A1",start);
 assert.ok(start>=0&&end>start);
 const handler=source.slice(start,end);
 for(const name of ['MODELS','LEARN']){
  let callback,invoked=0,active=false,prevented=false;
  const state={textContent:''};
  const button={tagName:'BUTTON',isConnected:true,disabled:false,
   getClientRects(){return [1]},focus(){doc.activeElement=button},
   click(){invoked++;throw Error('original owner transport failed')}};
  const primary={getClientRects(){return [1]},closest(){return primary},
   getAttribute(k){return k==='data-nox-primary'?name:null}};
  const screen={classList:{contains:key=>key==='active'&&active}};
  const navigation={click(){active=true}};
  const selector=name==='MODELS'?'button#model-center':'button#training-diagnostic';
  const doc={activeElement:null,querySelectorAll(s){
   if(s==='.nav button[data-screen="control"]')return [navigation];
   if(s===selector)return [button];return [];
  },getElementById(id){return id==='control'?screen:null}};
  const nav={contains(){return true},addEventListener(kind,fn){
   assert.equal(kind,'click');callback=fn}};
  Function('nav','state','document','originalPrimaryButtons','verifiedOriginalPrimaryDock',
   'originalInstallTransportPresent','originalNavigationAllowed','visibleOriginalOwnerTarget',
   'findOriginalControl','findOriginalScreen',handler)(
   nav,state,doc,[primary],()=>true,()=>true,()=>true,()=>true,()=>null,()=>null);
  assert.doesNotThrow(()=>callback({target:primary,isTrusted:true,
   preventDefault(){prevented=true}}),'original '+name+' throw must not escape D02 HOME');
  assert.equal(invoked,1,'must not retry original owner after failure');
  assert.equal(prevented,true);
  assert.match(state.textContent,/HOLD/,'no optimistic ACK after owner failure');
 }
});


test('D01 original SETTINGS/CHAT WebView2 teardown is HOLD and never repeated',()=>{
 const begin=source.indexOf("nav.addEventListener('click',event=>{");
 const end=source.indexOf("\n// Read-only original A1",begin);
 assert.ok(begin>=0&&end>begin);
 const handler=source.slice(begin,end);
 function run(name,fault){
  let callback,menuActive=false,detailActive=false,chatActive=false,prevented=false;
  const counts={menu:0,tile:0,back:0,chat:0},state={textContent:''};
  const primary={closest(){return primary},getClientRects:()=>[1],
   getAttribute:k=>k==='data-nox-primary'?name:null};
  const nav={contains:()=>true,addEventListener:(_kind,fn)=>callback=fn};
  const menu={tagName:'BUTTON',isConnected:true,disabled:false,click(){
   counts.menu++;if(fault==='menu')throw Error('menu gone');menuActive=true}};
  const tile={tagName:'BUTTON',isConnected:true,disabled:false,getClientRects:()=>[1],
   focus(){if(fault==='tileFocus')throw Error('tile focus gone');document.activeElement=tile},
   click(){counts.tile++;if(fault==='tile')throw Error('tile owner gone');detailActive=true}};
  const back={tagName:'BUTTON',isConnected:true,disabled:false,getClientRects:()=>[1],
   getAttribute:k=>k==='aria-label'?'← Назад в меню':null,
   focus(){counts.back++;if(fault==='backFocus')throw Error('back focus gone');document.activeElement=back}};
  const chat={tagName:'BUTTON',isConnected:true,disabled:false,click(){
   counts.chat++;if(fault==='chat')throw Error('chat gone');chatActive=true}};
  const document={activeElement:null,querySelectorAll:s=>s==='.nav button[data-screen="menu"]'?[menu]:
   s==='button.tile[data-menu-index="7"]'?[tile]:s==='#menu-detail button'?[back]:[],
   getElementById:id=>id==='menu'?{classList:{contains:k=>k==='active'&&menuActive}}:
    id==='menu-detail'?{classList:{contains:k=>k==='active'&&detailActive}}:
    id==='chat'?{classList:{contains:k=>k==='active'&&chatActive}}:null};
  Function('nav','state','document','originalPrimaryButtons','verifiedOriginalPrimaryDock',
   'originalInstallTransportPresent','originalNavigationAllowed','visibleOriginalOwnerTarget',
   'findOriginalControl','findOriginalScreen',handler)(
   nav,state,document,[primary],()=>true,()=>true,()=>true,()=>true,
   n=>n==='CHAT'?chat:null,()=>null);
  let error=null;
  try{callback({target:primary,isTrusted:true,preventDefault(){prevented=true}})}
  catch(err){error=err}
  return {error,counts,state:state.textContent,prevented,menuActive,detailActive,chatActive,focused:document.activeElement===back};
 }
 for(const fault of ['menu','tileFocus','tile','backFocus']){
  const result=run('SETTINGS',fault);
  assert.equal(result.error,null,'no uncaught original R11 navigation '+fault);
  assert.equal(result.prevented,true);
  assert.match(result.state,/HOLD/);
  assert.ok(result.counts.menu<=1&&result.counts.tile<=1&&result.counts.back<=1);
 }
 const ok=run('SETTINGS','');
 assert.equal(ok.error,null);assert.equal(ok.focused,true);
 assert.equal(ok.menuActive,true);assert.equal(ok.detailActive,true);
 assert.equal(ok.counts.menu,1);assert.equal(ok.counts.tile,1);assert.equal(ok.counts.back,1);
 const chatBad=run('CHAT','chat');
 assert.equal(chatBad.error,null);assert.equal(chatBad.counts.chat,1);
 assert.equal(chatBad.prevented,true);assert.match(chatBad.state,/HOLD/);
 const chatOk=run('CHAT','');
 assert.equal(chatOk.error,null);assert.equal(chatOk.counts.chat,1);
 assert.equal(chatOk.chatActive,true);assert.doesNotMatch(chatOk.state,/HOLD/);
});
