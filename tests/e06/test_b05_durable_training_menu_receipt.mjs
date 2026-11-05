/** B05: real SQLite S03 CLAIM, not transport completion, is the LEARN boundary.
 * Run: node tests/e06/test_b05_durable_training_menu_receipt.mjs
 * SOURCE_ONLY: this test does not train weights or emulate installed Windows.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {nativeOwnerActionReceipt} from '../../ui/onehost-menu-bindings.mjs';
const good={ack:true,job_id:'forge-job-7',status:'QUEUED',task_id:42,
  durable_s03:true,execution_completed:false,training_completed:false,
  weights_updated:false,activation_allowed:false};
const wire=(result,routeId='training.start',state='COMPLETED')=>({routeId,state,result});
const owner=(result,routeId='training.start',state='COMPLETED',selected='forge-job-7')=>
  nativeOwnerActionReceipt(wire(result,routeId,state),routeId,'selfbuilder.train.request',selected);
assert.equal(owner(good).ack,true);
assert.equal(owner(good).queueVerified,true);
assert.equal(owner(good).training_completed,false);
for(const [key,value] of [
  ['ack',false],['job_id','other'],['status','COMPLETED'],
  ['task_id',true],['task_id',0],['task_id',0.5],['task_id',Number.MAX_SAFE_INTEGER+1],
  ['durable_s03',false],['execution_completed',true],['training_completed',true],
  ['weights_updated',true],['activation_allowed',true]
])assert.equal(owner({...good,[key]:value}).ack,false,'forged '+key);
assert.equal(owner(good,'chat.commands').ack,false);
assert.equal(owner(good,'training.start','HOLD').ack,false);
assert.equal(owner({...good,errorCode:'OWNER_DENIED'}).ack,false);
assert.equal(owner({...good,status:'CONSENT REQUIRED'}).ack,false);
assert.equal(nativeOwnerActionReceipt(wire(good),'training.start','selfbuilder.train.request','other').ack,false);
const menu=readFileSync(new URL('../../ui/selfbuilder-menu-v2.mjs',import.meta.url),'utf8');
assert.match(menu,/receipt\.queueVerified===true/);
assert.match(menu,/обучение НЕ завершено/);
console.log('B05 S03 QUEUE OWNER RECEIPT: SOURCE_ONLY PASS');
