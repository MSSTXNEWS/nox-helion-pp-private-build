import assert from 'node:assert/strict';
import {test} from 'node:test';
import {nativeModelCancelAck} from '../../ui/onehost-menu-bindings.mjs';

const jobId='job-17';
test('P03 native cancel only confirms exact real job and approved owner receipt',()=>{
  assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'STOP_REQUESTED',
    result:{jobId,status:'CANCEL_REQUESTED'}},jobId),true);
  assert.equal(nativeModelCancelAck({routeId:'models.cancel',state:'STOP_REQUESTED',
    result:{jobId,status:'STOP_REQUESTED',ack:true}},jobId),true);
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
