import assert from 'node:assert/strict';
import {test} from 'node:test';
import {nativeModelCancelAck,nativeOwnerReceiptHolds,nativeCompletedOwnerReply,nativeOwnerActionReceipt} from '../../ui/onehost-menu-bindings.mjs';

const jobId='job-17';
test('P03 native cancel only confirms exact real job and approved owner receipt',()=>{
  assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'STOP_REQUESTED',
    result:{jobId,cancelled:true,status:'CANCEL_REQUESTED'}},jobId),true);
  assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'STOP_REQUESTED',
    result:{jobId,cancelled:true,status:'STOP_REQUESTED',ack:true}},jobId),true);
  assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'COMPLETED',
    result:{jobId,cancelled:true}},jobId),true);
test('P03 completed cancel accepts terminal state only for authenticated same job',()=>{
  for(const spelling of ['CANCELLED','CANCELED']) {
    assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'COMPLETED',
      result:{jobId,cancelled:true,status:spelling,state:spelling,ack:true}},jobId),true);
  }
  for(const receipt of [
    {jobId:'other-job',cancelled:true,status:'CANCELLED',ack:true},
    {jobId,cancelled:false,status:'CANCELLED',ack:true},
    {jobId,status:'CANCELLED',ack:true},
    {jobId,cancelled:true,status:'CANCELLED',ack:false},
    {jobId,cancelled:true,status:'CANCELLED',state:'CONSENT_REQUIRED'},
    {jobId,cancelled:true,status:'CANCELLED',errorCode:'ACL_DENIED'},
    {jobId,cancelled:true,status:'CANCELLED_CONSENT_REQUIRED'},
  ]) {
    assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'COMPLETED',result:receipt},jobId),false);
  }
  assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'COMPLETED',errorCode:'DENIED',
    result:{jobId,cancelled:true,status:'CANCELLED'}},jobId),false);
  assert.equal(nativeModelCancelAck({routeId:'models.pull',state:'COMPLETED',
    result:{jobId,cancelled:true,status:'CANCELLED'}},jobId),false);
});

  for(const reply of [
    {routeId:'models.cancel',state:'STOP_REQUESTED',result:{jobId:'foreign',status:'CANCEL_REQUESTED'}},
    {routeId:'models.cancel',state:'STOP_REQUESTED'},
    {routeId:'models.cancel',state:'STOP_REQUESTED',result:{jobId,status:'CONSENT_REQUIRED',ack:false}},
    {routeId:'models.cancel',state:'STOP_REQUESTED',result:{jobId,status:'PROVIDER_OFFLINE_HOLD'}},
    {routeId:'models.cancel',state:'STOP_REQUESTED',result:{jobId,errorCode:'ACL_DENIED'}},
    {routeId:'models.cancel',state:'STOP_REQUESTED',errorCode:'CONSENT_REQUIRED',result:{jobId}},
    {routeId:'models.cancel',state:'COMPLETED',result:{jobId,cancelled:false}},
    {routeId:'models.retry',state:'STOP_REQUESTED',result:{jobId}}
  ])assert.equal(nativeModelCancelAck(reply,jobId),false);
});

// B06: transport COMPLETED cannot mask owner/provider errors in two native field shapes.
for (const field of ['error','error_code']) {
  for (const value of ['CONSENT_DENIED','PROVIDER_OFFLINE_HOLD',{'code':'DENIED'}]) {
    assert.equal(nativeOwnerReceiptHolds({state:'COMPLETED',[field]:value}),true,
      field+' must deny any populated native owner error');
  }
  assert.equal(nativeOwnerReceiptHolds({state:'COMPLETED',[field]:''}),false,
    'empty native error field alone is not a denial');
}

test('P03 model cancel STOP_REQUESTED does not launder outer owner denials',()=>{
  const pending={routeId:'models.cancel',state:'STOP_REQUESTED',result:{jobId,cancelled:true,status:'CANCEL_REQUESTED',ack:true}};
  assert.equal(nativeModelCancelAck(pending,jobId),true);
  for(const denial of [{error:'CONSENT_DENIED'},{error_code:'ACL_DENIED'},
    {error:{code:'PROVIDER_OFFLINE_HOLD'}},{status:'CONSENT_REQUIRED'},{ok:false}])
    assert.equal(nativeModelCancelAck({...pending,...denial},jobId),false);
});

test('native owner rejects pending privilege, SID and consent states while retaining legitimate completion',()=>{
  for(const state of ['PERMISSION_REQUIRED','AUTHORIZATION_REQUIRED','NOT_AUTHORIZED',
    'NOT_AUTHENTICATED','AWAITING_CONSENT','NEEDS_CONSENT','CONSENT_PENDING',
    'SID_MISMATCH','ACL_MISMATCH']){
    assert.equal(nativeOwnerReceiptHolds({state,ok:true,ack:true}),true,state);
    assert.equal(nativeOwnerReceiptHolds({status:'owner_'+state+'_gate',ok:true}),true,state+' wrapped');
  }
  for(const state of ['COMPLETED','QUEUED','IN_PROGRESS','READY'])
    assert.equal(nativeOwnerReceiptHolds({state,ok:true,ack:true}),false,state);
});

test('G2 native owner explicit errorMessage/error_message cannot be privileged ACK',()=>{
  for(const field of ['errorMessage','error_message']){
    for(const denial of ['CONSENT_REQUIRED','ACL_DENIED',{code:'PROVIDER_OFFLINE_HOLD'}]){
      const owner={ok:true,ack:true,run_id:'S03-original-1',source_head:'a'.repeat(40),[field]:denial};
      const reply={routeId:'chat.commands',state:'COMPLETED',result:owner};
      assert.equal(nativeOwnerReceiptHolds(owner),true,field+' receipt denial');
      assert.equal(nativeCompletedOwnerReply(reply),false,field+' transport denial');
      assert.equal(nativeOwnerActionReceipt(reply,'chat.commands','selfbuilder.propose').ack,false,field+' owner denial');
    }
    const owner={ok:true,ack:true,run_id:'S03-original-1',source_head:'a'.repeat(40),[field]:''};
    assert.equal(nativeOwnerReceiptHolds(owner),false,field+' empty error keeps valid receipt');
  }
});

// F03: the original OneHost must have issued an exact-job cancellation effect.
// A UA-trusted STOP_REQUESTED transport with no positive P03 owner bit is HOLD.
test('P03 native STOP_REQUESTED requires explicit same-job cancelled=true',()=>{
  const positive={routeId:'models.cancel',state:'STOP_REQUESTED',
    result:{jobId,cancelled:true,status:'CANCEL_REQUESTED',ack:true}};
  assert.equal(nativeModelCancelAck(positive,jobId),true);
  for(const value of [undefined,false,null,'true',0]){
    assert.equal(nativeModelCancelAck({...positive,result:{...positive.result,cancelled:value}},jobId),false);
  }
  assert.equal(nativeModelCancelAck({...positive,result:{...positive.result,ownerResult:{approved:false}}},jobId),false);
  assert.equal(nativeModelCancelAck({...positive,result:{...positive.result,jobId:'foreign'}},jobId),false);
});
