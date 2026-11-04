import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {nativeModelReady,nativeModelSelectionAck} from '../../ui/onehost-menu-bindings.mjs';
const ack=(model,state='COMPLETED',routeId='chat.model')=>({routeId,state,result:{selectedModel:model}});
test('native model ACK requires exact route, completed state and model tag',()=>{
 assert.equal(nativeModelSelectionAck(ack('qwen:7b'),'qwen:7b'),true);
 for(const [reply,tag] of [
  [ack('wrong'),'qwen:7b'],[ack('qwen:7b','HOLD'),'qwen:7b'],
  [ack('qwen:7b','COMPLETED','helion.chat'),'qwen:7b'],
  [{state:'COMPLETED',result:{selectedModel:'qwen:7b'}},'qwen:7b'],
  [{routeId:'chat.model',state:'COMPLETED',result:{}},'qwen:7b'],
  [null,'qwen:7b'],[ack(''),'']
 ])assert.equal(nativeModelSelectionAck(reply,tag),false);
});
test('pending and mismatch never advertise ready model',()=>{
 assert.equal(nativeModelReady('qwen:7b','qwen:7b',false),true);
 for(const args of [['qwen:7b','qwen:7b',true],['qwen:7b','other',false],
  ['qwen:7b','',false],['','',false],['qwen:7b','qwen:7b',undefined]])
  assert.equal(nativeModelReady(...args),false);
});
test('shipped binding uses ACK guard for catalog, change, Send and late replies',()=>{
 const src=readFileSync(new URL('../../ui/onehost-menu-bindings.mjs',import.meta.url),'utf8');
 const send=src.slice(src.indexOf('async function sendChat(){'),src.indexOf('async function models(){'));
 const models=src.slice(src.indexOf('async function models(){'),src.indexOf('async function click(event){'));
 const change=src.slice(src.indexOf('async function change(event){'),src.indexOf("doc.addEventListener('click',click,true);"));
 assert.ok(send.includes('nativeModelReady(model,modelConfirmed,modelSelectionPending)'));
 assert.ok(send.includes("client.request('helion.chat'"));
 assert.ok(models.includes('observedEpoch!==selectionEpoch'));
 assert.ok(models.includes('nativeModelSelectionAck(reply,selected)'));
 assert.ok(change.includes("modelConfirmed=''"));
 assert.ok(change.includes('if(modelSelectionPending)'));
 assert.ok(change.includes('nativeModelSelectionAck(chosen,requested)'));
 assert.ok(change.includes("client.request('chat.history'"));
});
