import test from 'node:test';
import assert from 'node:assert/strict';
import {P01_READINESS_ACTIONS,p01ReadinessResult} from '../../../ui/selfbuilder-menu-v2.mjs';

test('readiness uses five existing read-only native actions and no new updater/trainer',()=>{
 assert.deepEqual(P01_READINESS_ACTIONS.map(x=>x.action),[
  'selfbuilder.capabilities','selfbuilder.coding.models',
  'selfbuilder.sources.inspect','selfbuilder.worker.status',
  'selfbuilder.learning.proofs']);
 assert.equal(P01_READINESS_ACTIONS.every(x=>!x.action.includes('start')&&!x.action.includes('pull')),true);
});
test('missing/forged ACK never claims AI or GPU accepted',()=>{
 for(const check of P01_READINESS_ACTIONS){
  assert.equal(p01ReadinessResult(check.action,{ack:false,status:'COMPLETED'}).state,'HOLD');
  assert.equal(p01ReadinessResult(check.action,{status:'SOURCE_SERVICE',models:['fake']}).state,'HOLD');
 }
 assert.equal(p01ReadinessResult('unsafe.download',{ack:true}).state,'HOLD');
});
test('native capabilities report clean Git HEAD requirement, not fictitious readiness',()=>{
 const a='selfbuilder.capabilities';
 assert.equal(p01ReadinessResult(a,{ack:true,actions:{x:{available:true}},source_head:null}).state,'HOLD');
 assert.equal(p01ReadinessResult(a,{ack:true,actions:{x:{available:true}},
    source_head:'a'.repeat(40)}).state,'AVAILABLE');
});
test('real local model inventory 0 is HOLD and 1 is discovery only',()=>{
 const a='selfbuilder.coding.models';
 assert.equal(p01ReadinessResult(a,{ack:true,models:[]}).state,'HOLD');
 const ready=p01ReadinessResult(a,{ack:true,models:['real-installed']});
 assert.equal(ready.state,'AVAILABLE');
 assert.match(ready.message,/наличие модели не равно обучению/);
});
test('source discovery does not claim S03 import or weights',()=>{
 const a='selfbuilder.sources.inspect';
 assert.equal(p01ReadinessResult(a,{ack:true,status:'HOLD',owner_admitted_total:999}).state,'HOLD');
 assert.equal(p01ReadinessResult(a,{ack:true,status:'SOURCE_INVENTORY_READ_ONLY',
    owner_admitted_total:3}).state,'AVAILABLE');
});
test('worker READY_FOR_OWNER_TASK is not running autonomously',()=>{
 const a='selfbuilder.worker.status';
 assert.match(p01ReadinessResult(a,{ack:true,status:'READY_FOR_OWNER_TASK',tasks:[]}).message,/автозапуск не выполнялся/);
 assert.equal(p01ReadinessResult(a,{ack:true,status:'STOPPED',tasks:[]}).state,'HOLD');
});
test('learning only accepts genuine S03 proof rows, never equates to weight training',()=>{
 const a='selfbuilder.learning.proofs';
 assert.equal(p01ReadinessResult(a,{ack:true,status:'S03_READ',tasks:[]}).state,'HOLD');
 const x=p01ReadinessResult(a,{ack:true,status:'S03_READ',tasks:[{result:'hash'}]});
 assert.equal(x.state,'AVAILABLE');
 assert.match(x.message,/веса не изменялись/);
});
