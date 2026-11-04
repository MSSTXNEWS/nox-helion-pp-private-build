'use strict';
// ORIGINAL ModelCenter source regression; synthetic host is not native Windows proof.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,
  '../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js'),'utf8');
function mount(){
  const sent=[],timers=[],nodes=new Map();
  const node=(tag='div')=>({tagName:tag.toUpperCase(),children:[],handlers:{},attrs:{},
    dataset:{},textContent:'',value:'',checked:false,disabled:false,hidden:false,
    style:{setProperty(){}},classList:{add(){},remove(){},toggle(){}},
    append(...items){this.children.push(...items);},
    appendChild(item){this.children.push(item);},
    replaceChildren(...items){this.children=items;},
    setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
    focus(){},addEventListener(k,fn){this.handlers[k]=fn;}});
  const document={getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},
    createElement:node,querySelector(s){return s==='.topbar'?this.getElementById('_topbar'):null;},
    querySelectorAll(){return [];},addEventListener(){},activeElement:{tagName:'BODY'}};
  const window={chrome:{webview:{postMessage(data){sent.push(data);},addEventListener(){}}}};
  const app=new Function('document','window','URL','Date','setInterval','setTimeout',
    'clearTimeout',source+'\nreturn {state,sendAction,processMessage,renderHero};')(
    document,window,URL,Date,()=>0,(fn,ms)=>{timers.push({fn,ms});return timers.length;},()=>{});
  // Positive reviewed fixture only; a test fixture is NEVER a downloaded model.
  const model={id:'llama3',name:'Llama 3',officialUrl:'https://ollama.com/library/llama3',
    artifactVerified:true,exactTag:'llama3:8b',immutableRevision:'a'.repeat(64),
    license:'Apache-2.0',licenseEvidenceUrl:'https://ollama.com/library/llama3',
    artifactBytes:123456789,sha256:'b'.repeat(64),manifestSha256:'c'.repeat(64),
    requiredVramGiB:8,recommendedRamGiB:16,compatibilityReviewed:true};
  app.state.models=[model];app.state.activeId=model.id;app.state.hostReady=true;
  app.state.capabilities={pull:true,importGguf:true};
  const element=id=>document.getElementById(id),commands=()=>sent.filter(x=>x.type==='p03.command.v1');
  element('licenseAck').checked=true;app.renderHero();
  return {app,element,commands,timers};
}
test('pull locks both reviewed download routes until its authentic ACK',()=>{
  const x=mount();assert.equal(x.element('pullBtn').disabled,false);
  assert.equal(x.element('importBtn').disabled,false);
  x.app.sendAction('pull');assert.deepEqual(x.commands().map(c=>c.action),['pull']);
  assert.equal(x.element('pullBtn').disabled,true);
  assert.equal(x.element('importBtn').disabled,true,'second transfer button must be disabled');
  x.app.sendAction('importGguf');
  assert.deepEqual(x.commands().map(c=>c.action),['pull'],'no concurrent native import');
  x.app.processMessage({type:'p03.command.ack.v1',action:'pull',
    commandId:x.commands()[0].commandId,accepted:true});
  assert.equal(x.element('importBtn').disabled,false,'valid ACK releases mutex, not install claim');
  assert.equal(x.app.state.activeJob,null,'ACK is never an installed model');
});
test('GGUF import likewise prevents concurrent pull and preserves explicit consent',()=>{
  const x=mount();x.app.sendAction('importGguf');
  assert.equal(x.element('pullBtn').disabled,true);
  x.app.sendAction('pull');assert.deepEqual(x.commands().map(c=>c.action),['importGguf']);
  x.app.processMessage({type:'p03.command.ack.v1',action:'importGguf',
    commandId:x.commands()[0].commandId,accepted:false,reason:'CONSENT_REQUIRED'});
  assert.equal(x.element('pullBtn').disabled,false);
  assert.equal(x.app.state.activeJob,null);
});
test('unmatched native ACK cannot release a pending transfer',()=>{
  const x=mount();x.app.sendAction('pull');
  x.app.processMessage({type:'p03.command.ack.v1',action:'pull',commandId:'wrong',accepted:true});
  assert.equal(x.app.state.pending.has('pull'),true);
  assert.equal(x.element('importBtn').disabled,true);
  x.app.sendAction('importGguf');assert.equal(x.commands().length,1);
});
test('ACK timeout unlocks only the UI; it never retries or invents installation',()=>{
  const x=mount();x.app.sendAction('pull');
  const timeout=x.timers.find(t=>t.ms===45000);assert.ok(timeout);
  timeout.fn();assert.equal(x.app.state.pending.has('pull'),false);
  assert.equal(x.element('importBtn').disabled,false);
  assert.equal(x.commands().length,1,'no automatic second action or download');
  assert.equal(x.app.state.activeJob,null);
});
test('both transfer routes require the explicit license checkbox',()=>{
  const x=mount();x.element('licenseAck').checked=false;
  x.app.sendAction('pull');x.app.sendAction('importGguf');
  assert.equal(x.commands().length,0,'neither command may bypass consent');
});
