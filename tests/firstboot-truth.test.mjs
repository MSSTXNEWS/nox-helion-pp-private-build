import assert from 'node:assert/strict';
import {firstBootTruth} from '../ui/firstboot-truth.mjs';
const blank=firstBootTruth(null,null,null);
assert.equal(blank.verified.a1,false);
assert.equal(blank.weights_updated,false);
assert.match(blank.items[0][1],/HOLD/);
const ok=firstBootTruth({routeId:'chat.commands',state:'COMPLETED',result:{schema:'NOX-A1-NATIVE-COMMAND-STATUS-v1',state:'ACTIVE_NATIVE_BOOT_RECEIPT',native_bound:true}},{routeId:'chat.commands',state:'COMPLETED',result:{status:'SOURCE_SERVICE',actions:{'selfbuilder.propose':{available:true,status:'AVAILABLE'}}}},{routeId:'chat.model',state:'COMPLETED',result:{models:[{name:'qwen'}]}});
assert.equal(ok.verified.a1,true);
assert.equal(ok.verified.selfbuildRequest,true);
assert.match(ok.items[1][1],/^1 /);
assert.equal(ok.training_started,false);
const forged=firstBootTruth({routeId:'chat.commands',state:'COMPLETED',errorCode:'HOLD',result:{schema:'NOX-A1-NATIVE-COMMAND-STATUS-v1',state:'ACTIVE_NATIVE_BOOT_RECEIPT',native_bound:true}},null,null);
assert.equal(forged.verified.a1,false);
const late=firstBootTruth({routeId:'chat.commands',state:'HOLD',result:{schema:'NOX-A1-NATIVE-COMMAND-STATUS-v1',state:'ACTIVE_NATIVE_BOOT_RECEIPT',native_bound:true}},null,null);
assert.equal(late.verified.a1,false);
console.log('FIRSTBOOT_TRUTH_PASS 9 ASSERTIONS');

const providerHold=firstBootTruth(null,null,{routeId:'chat.model',state:'COMPLETED',result:{status:'HOLD',models:[{name:'fake'}]}});
assert.equal(providerHold.verified.modelInventory,false);
assert.equal(firstBootTruth(null,{routeId:'chat.commands',state:'COMPLETED',result:{status:'SOURCE_SERVICE',ack:false,actions:{'selfbuilder.propose':{available:true,status:'AVAILABLE'}}}},null).verified.selfbuildRequest,false);

const verifiedBoot={routeId:'chat.commands',state:'COMPLETED',result:{
  schema:'NOX-A1-NATIVE-COMMAND-STATUS-v1',state:'ACTIVE_NATIVE_BOOT_RECEIPT',native_bound:true}};
for(const status of ['CONSENT REQUIRED','SID MISMATCH','AUTH REQUIRED','NOT AUTHORIZED']){
  assert.equal(firstBootTruth({...verifiedBoot,result:{...verifiedBoot.result,status}},null,null).verified.a1,false,
    'native spaced denial must not report A1 READY: '+status);
}
const confirmedPropose={routeId:'chat.commands',state:'COMPLETED',result:{
  status:'SOURCE_SERVICE',actions:{'selfbuilder.propose':{available:true,status:'AVAILABLE'}}}};
for(const status of ['OWNER DENIED','PERMISSION REQUIRED']){
  assert.equal(firstBootTruth(null,{...confirmedPropose,result:{
    ...confirmedPropose.result,actions:{'selfbuilder.propose':{
      ...confirmedPropose.result.actions['selfbuilder.propose'],owner:{status}
    }}}},null).verified.selfbuildRequest,false,'denied owner action must be HOLD: '+status);
}
assert.equal(firstBootTruth(null,null,{routeId:'chat.model',state:'COMPLETED',
 result:{status:'PROVIDER OFFLINE',models:['qwen']}}).verified.modelInventory,false);
assert.equal(firstBootTruth(verifiedBoot,confirmedPropose,
 {routeId:'chat.model',state:'COMPLETED',result:{models:['qwen']}})
 .verified.a1,true);
