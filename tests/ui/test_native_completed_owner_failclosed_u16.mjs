import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeReadVerified,nativeCompletedOwnerReply,nativeOwnerReceiptHolds} from '../../ui/onehost-menu-bindings.mjs';

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
