import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { nativeOwnerReceiptHolds } from '../../ui/onehost-menu-bindings.mjs';

// Extract the shipped UI function, not a duplicated synthetic selection algorithm.
const source=readFileSync(new URL('../../ui/menu-pages/menu.js', import.meta.url),'utf8');
const fragment=source.slice(source.indexOf('function liveChat(label){'),source.indexOf('\nfunction openRoute(id){'));
test('model selection is serialized and requires its own exact native ACK', async()=>{
 assert.ok(fragment.startsWith('function liveChat(label){'));
 class Elem{
  constructor(tag,cls,label){this.tag=tag;this.className=cls||'';this.textContent=label??'';this.children=[];this.attrs={};this.isConnected=true;this.listeners={};this.classList={add:(...names)=>{this.className=[this.className,...names].filter(Boolean).join(' ');}};this.disabled=false;this.value='';this.scrollHeight=0;}
  append(...x){this.children.push(...x);}
  replaceChildren(...x){this.children=x;}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(k,fn){this.listeners[k]=fn;}
 }
 const doc={createElement:tag=>new Elem(tag),createElementNS:(_ns,tag)=>new Elem(tag)};
 const nodes=[];
 const el=(tag,cls,label)=>{const x=new Elem(tag,cls,label);nodes.push(x);return x;};
 const button=(label,cls,click)=>{const x=el('button',cls,label);x.onclick=click;return x;};
 const calls=[],pending=[];
 const client={request:(route,payload)=>{
  assert.equal(route,'chat.model');
  if(!payload.model)return Promise.resolve({state:'COMPLETED',result:{models:['qwen:0.6b','mistral:7b'],selectedModel:'qwen:0.6b'}});
  calls.push(payload.model);return new Promise(resolve=>pending.push(resolve));
 }};
 const create=new Function('el','button','client','setDetails','CORE_IDS','PERSONAS','chatInFlight','chatStopPending','selectedCore','selectedPersona','nativeOwnerReceiptHolds','doc',fragment+'\nreturn liveChat;');
 const run=create(el,button,client,()=>{},['CORE','ATLAS'],['KV','AM'],false,false,null,null,nativeOwnerReceiptHolds,doc);
 run({world:'pc',name:'Чат'});
 await Promise.resolve();await Promise.resolve();
 const rows=nodes.filter(x=>x.className==='nox-chat-chips');
 const models=()=>rows[2].children;
 const send=nodes.find(x=>x.className==='nox-chat-send');
 assert.equal(models().length,2);
 assert.equal(send.disabled,false);
 const first=models()[0].onclick();
 assert.equal(calls.length,1);
 assert.equal(send.disabled,true);
 assert.ok(models().every(x=>x.disabled));
 await models()[1].onclick();
 assert.equal(calls.length,1,'competing selection may not reach the native owner');
 pending.shift()({state:'COMPLETED',result:{selectedModel:'qwen:0.6b'}});
 await first;
 assert.equal(send.disabled,false);
 const wrong=models()[1].onclick();
 pending.shift()({state:'COMPLETED',result:{selectedModel:'wrong-tag'}});
 await wrong;
 assert.equal(send.disabled,true,'mismatched ACK must not enable sending');
 const offline=models()[0].onclick();
 pending.shift()({state:'COMPLETED',errorCode:'PROVIDER_OFFLINE_HOLD',result:{selectedModel:'qwen:0.6b'}});
 await offline;
 assert.equal(send.disabled,true,'COMPLETED with native envelope HOLD must not enable SEND');
 const embedded=models()[0].onclick();
 pending.shift()({state:'COMPLETED',result:{selectedModel:'qwen:0.6b',status:'PROVIDER_OFFLINE_HOLD'}});
 await embedded;
 assert.equal(send.disabled,true,'COMPLETED with provider status HOLD must not enable SEND');
 assert.ok(models().every(x=>x.attrs['aria-pressed']!=='true'));
 const denied=models()[0].onclick();
 pending.shift()({state:'HOLD',errorCode:'DENIED'});
 await denied;
 assert.equal(send.disabled,true,'HOLD must not reuse previous model');
 const recovered=models()[1].onclick();
 pending.shift()({state:'COMPLETED',result:{selectedModel:'mistral:7b'}});
 await recovered;
 assert.equal(send.disabled,false);
 assert.equal(models().filter(x=>x.attrs['aria-pressed']==='true').length,1);
});
test('changing CoreID or Persona invalidates model ACK; stale owner replies cannot re-enable SEND', async()=>{
 class Elem {
  constructor(tag,cls,label){this.tag=tag;this.className=cls||'';this.textContent=label??'';this.children=[];this.attrs={};this.isConnected=true;this.disabled=false;this.value='';this.listeners={};this.classList={add:(...names)=>{this.className=[this.className,...names].filter(Boolean).join(' ');}};}
  append(...x){this.children.push(...x);}
  replaceChildren(...x){this.children=x;}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(k,fn){this.listeners[k]=fn;}
 }
 const doc={createElement:tag=>new Elem(tag),createElementNS:(_ns,tag)=>new Elem(tag)};
 const nodes=[];
 const el=(tag,cls,label)=>{const x=new Elem(tag,cls,label);nodes.push(x);return x;};
 const button=(label,cls,click)=>{const x=el('button',cls,label);x.onclick=click;return x;};
 const waits=[];
 const client={request:(route,payload)=>{
  assert.equal(route,'chat.model');
  if(!payload.model)return Promise.resolve({state:'COMPLETED',result:{models:['qwen:0.6b','mistral:7b'],selectedModel:'qwen:0.6b'}});
  return new Promise(resolve=>waits.push(resolve));
 }};
 const live=new Function('el','button','client','setDetails','CORE_IDS','PERSONAS','chatInFlight','chatStopPending','selectedCore','selectedPersona','nativeOwnerReceiptHolds','doc',fragment+'\nreturn liveChat;')(
  el,button,client,()=>{},['CORE','ATLAS'],['KV','AM'],false,false,null,null,nativeOwnerReceiptHolds,doc);
 live({world:'pc',name:'Чат'});
 await Promise.resolve();await Promise.resolve();
 const rows=nodes.filter(x=>x.className==='nox-chat-chips');
 const send=nodes.find(x=>x.className==='nox-chat-send');
 const models=()=>rows[2].children;
 assert.equal(send.disabled,false,'initial selectedModel belongs to current scope');
 rows[0].children[1].onclick(); // Change CoreID before sending.
 assert.equal(send.disabled,true,'previous model is not confirmed in new CoreID');
 assert.equal(models().filter(b=>b.attrs['aria-pressed']==='true').length,0);
 const pending=models()[0].onclick();
 assert.equal(waits.length,1);
 rows[1].children[1].onclick(); // Invalidate request during native ACK.
 waits.shift()({state:'COMPLETED',result:{selectedModel:'qwen:0.6b'}});
 await pending;
 assert.equal(send.disabled,true,'stale ACK after Persona switch must not authorize SEND');
 assert.equal(models().filter(b=>b.attrs['aria-pressed']==='true').length,0);
 const confirmed=models()[1].onclick();
 waits.shift()({state:'COMPLETED',result:{selectedModel:'mistral:7b'}});
 await confirmed;
 assert.equal(send.disabled,false,'fresh explicit model ACK restores CHAT');
 rows[0].children[0].onclick();
 assert.equal(send.disabled,true,'subsequent CoreID change immediately revokes ACK');
});
