// D03 · Existing approved R11 A1 owner status. Read and execute the exact
// production guard from the original Python publisher: no mock owner approval.
// SOURCE_ONLY. Does NOT certify a Windows SID, install exit or E07 release.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const begin=source.indexOf('function a1ReceiptDenied(');
const end=source.indexOf('const onNative=',begin);
assert.ok(begin>=0&&end>begin,'Original publisher guard is required');
const context=vm.createContext({});
vm.runInContext(source.slice(begin,end),context,{timeout:1000});
const denied=context.a1ReceiptDenied;
assert.equal(typeof denied,'function');
const ready={state:'COMPLETED',result:{
 schema:'NOX-A1-NATIVE-COMMAND-STATUS-v1',state:'ACTIVE_NATIVE_BOOT_RECEIPT',
 native_bound:true,boot_state:'READY_FOR_EXISTING_IDLE_TICK'
}};
test('D03 A1 original owner explicit approvals/denials remain fail-closed',()=>{
 const cases=[
  ['valid owner receipt',ready,false],
  ['owner unauthorized',{...ready,result:{...ready.result,authorized:false}},true],
  ['owner unapproved',{...ready,result:{...ready.result,approved:false}},true],
  ['owner consent revoked',{...ready,result:{...ready.result,consented:false}},true],
  ['transport success false',{...ready,success:false},true],
  ['string ACK',{...ready,result:{...ready.result,ack:'true'}},true],
  ['literal true fields',{...ready,result:{...ready.result,authorized:true,consented:true,approved:true,ack:true}},false],
  ['nested owner refusal',{...ready,result:{...ready.result,ownerResult:{authorized:false}}},true]
 ];
 for(const [label,receipt,expected] of cases)
  assert.equal(denied(receipt),expected,label);
});
