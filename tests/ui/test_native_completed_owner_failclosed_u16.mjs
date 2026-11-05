import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeReadVerified,nativeCompletedOwnerReply,nativeOwnerReceiptHolds,nativeAutostartPersistenceAck,nativeOwnerActionReceipt} from '../../ui/onehost-menu-bindings.mjs';

test('real original OneHost COMPLETED with envelope ack:false cannot unlock functional read',()=>{
  const good={routeId:'models.catalog',state:'COMPLETED',result:{models:[]}};
  assert.equal(nativeReadVerified(good,'models.catalog'),true);
  for(const rejected of [
    {...good,ack:false},
    {...good,errorCode:'PROVIDER_OFFLINE_HOLD'},
    {...good,result:{status:'CONSENT_REQUIRED'}},
    {...good,result:null},
    {...good,routeId:'chat.history'},
    {...good,state:'HOLD'}
  ])assert.equal(nativeReadVerified(rejected,'models.catalog'),false);
  assert.equal(nativeCompletedOwnerReply({...good,ack:false}),false);
  assert.equal(nativeOwnerReceiptHolds({...good,ack:false}),true);
});

// The original native C# handler returns {enabled} after HKCU readback.
// No arbitrary COMPLETED message can advertise SETTINGS persistence.
test('SETTINGS must match the persisted native Boolean and owner consent',()=>{
  const good={routeId:'system.autostart',state:'COMPLETED',result:{enabled:true}};
  assert.equal(nativeAutostartPersistenceAck(good,true),true);
  assert.equal(nativeAutostartPersistenceAck({...good,result:{enabled:false}},false),true);
  for(const bad of [
    {...good,result:{enabled:false}},
    {...good,result:{enabled:'true'}},
    {...good,result:{}},
    {...good,result:null},
    {...good,routeId:'models.catalog'},
    {...good,state:'HOLD'},
    {...good,ack:false},
    {...good,result:{enabled:true,errorMessage:'CONSENT_REQUIRED'}},
    {...good,result:{enabled:true,status:'SID_MISMATCH'}},
    {...good,errorCode:'ACL_MISMATCH'}
  ])assert.equal(nativeAutostartPersistenceAck(bad,true),false);
  assert.equal(nativeAutostartPersistenceAck(good,null),false);
  assert.equal(nativeAutostartPersistenceAck(good,'true'),false);
});

// GPU training ACK must bind to the selected existing FORGE job: no synthetic success.
test('LEARN training.start native ACK is scoped to exact approved job',()=>{
  const job='FORGE-job-12';
  const good={routeId:'training.start',state:'COMPLETED',result:{ack:true,job_id:job,status:'QUEUED'}};
  assert.equal(nativeOwnerActionReceipt(good,'training.start','selfbuilder.train.request',job).ack,true);
  for(const bad of [
    {...good,result:{ack:true,job_id:'different'}},
    {...good,result:{ack:true}},
    {...good,result:{ack:true,job_id:job,status:'CONSENT_REQUIRED'}},
    {...good,result:{ack:false,job_id:job}},
    {...good,errorCode:'SID_MISMATCH'},
    {...good,routeId:'chat.commands'}
  ])assert.equal(nativeOwnerActionReceipt(bad,'training.start','selfbuilder.train.request',job).ack,false);
  for(const id of ['',null,'../bad'])
    assert.equal(nativeOwnerActionReceipt(good,'training.start','selfbuilder.train.request',id).ack,false);
});

// B05: read the original shipped owner guard, not a reconstructed native
// success response. A completed transport with nested consent HOLD must not
// advertise LEARN actions or SETTINGS HKCU persistence.
test('LEARN/SETTINGS reject nested original native owner denials',()=>{
  const good={routeId:'system.autostart',state:'COMPLETED',
    result:{enabled:true,ownerResult:{success:true,approved:true,authorized:true}}};
  assert.equal(nativeAutostartPersistenceAck(good,true),true);
  for(const nested of [
    {ownerResult:{success:false}},
    {ownerResult:{approved:false}},
    {ownerResult:{authorized:false}},
    {ownerResult:{status:'CONSENT_REQUIRED'}},
    {receipt:{error_code:'ACL_MISMATCH'}},
    {nativeResult:{ack:false}},
    {result:{ownerResult:{status:'SID_MISMATCH'}}}
  ]){
    const response={...good,result:{enabled:true,...nested}};
    assert.equal(nativeAutostartPersistenceAck(response,true),false);
    assert.equal(nativeCompletedOwnerReply(response),false);
  }
  const denied={routeId:'chat.commands',state:'COMPLETED',
    result:{actions:{'selfbuilder.learning.proofs':{available:true}},
      ownerResult:{authorized:false}}};
  assert.equal(nativeReadVerified(denied,'chat.commands'),false);
  assert.equal(nativeOwnerReceiptHolds({success:false}),true);
});
