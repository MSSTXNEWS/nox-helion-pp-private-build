import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {nativeOwnerActionReceipt} from '../../ui/onehost-menu-bindings.mjs';

test('EXPRESS S03 proposal status demands exact native owner/consent ACK',()=>{
  const source=readFileSync(new URL('../../ui/menu-pages/menu.js',import.meta.url),'utf8');
  assert.match(source,/nativeOwnerActionReceipt\(result,'chat.commands','selfbuilder.propose'\)/);
  const valid={routeId:'chat.commands',state:'COMPLETED',result:{ack:true,
    run_id:'S03-ABC-1',source_head:'a'.repeat(40)}};
  assert.equal(nativeOwnerActionReceipt(valid,'chat.commands','selfbuilder.propose').ack,true);
  for(const denied of [
    {...valid,routeId:'models.catalog'},
    {...valid,status:'CONSENT_REQUIRED'},
    {...valid,error_code:'PROVIDER_OFFLINE_HOLD'},
    {...valid,ok:false},
    {...valid,result:{...valid.result,ok:false}},
    {...valid,result:{...valid.result,source_head:'broken'}},
    {...valid,result:{...valid.result,run_id:'fake'}}
  ])assert.equal(nativeOwnerActionReceipt(denied,'chat.commands','selfbuilder.propose').ack,false);
});
