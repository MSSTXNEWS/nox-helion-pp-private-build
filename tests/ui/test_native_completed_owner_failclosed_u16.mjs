import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeReadVerified,nativeCompletedOwnerReply,nativeOwnerReceiptHolds,nativeAutostartPersistenceAck} from '../../ui/onehost-menu-bindings.mjs';

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
