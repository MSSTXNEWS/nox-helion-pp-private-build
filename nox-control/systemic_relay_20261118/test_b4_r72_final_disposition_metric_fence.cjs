'use strict';
const assert=require('node:assert/strict');
const {classifyCompletion}=require('./b4_r70_completion_metric_fence.cjs');
const {classifyFinalizedCompletion}=require('./b4_r72_final_disposition_metric_fence.cjs');
function runTests(assert,oldGate,gate){
 const a='a'.repeat(64),b='b'.repeat(64),c='c'.repeat(64),d='d'.repeat(64);
 let count=0;
 for(const turn of [2,3]){
 const sample={conversation_id:'conv',exchange_id:'x'+turn,clock_id:'clock',terminal_event_id:'terminal'+turn,served_sha256:a,begin_ms:100,first_visible_ms:110,eof_ms:150,outcome:'STREAM_ENDED_READBACK_REQUIRED'};
 const proof={...sample,verified:true,dom_receipt_id:'dom'+turn,canonical_receipt_id:'s03'+turn,dom_sha256:b,answer_sha256:b,dom_commit_ms:170,observation_id:'obs'+turn,observation_sha256:c,terminal_receipt_sha256:d,browser_sha256:a,physical_dialog_id:'physical',s03_dialog_id:'s03',session_id:'session',request_id:'request'+turn,attempt_id:'attempt'+turn,event_id:'event'+turn,turn_id:'turn'+turn,assistant_message_id:'msg'+turn,reservation_receipt_id:'reserve'+turn,turn};
 const final={...proof,state:'ACK_RESERVED_AFTER_DOM_RECHECK',receipt_id:'final'+turn};
 const pending=gate(sample,proof,{...final,state:'PENDING'});
 assert.equal(oldGate(sample,proof).status,'VERIFIED_COMPLETION_SAMPLE');
 assert.equal(pending.status,'HOLD_FINAL_DISPOSITION');assert.equal(pending.completion_ms,null);count++;
 for(const bad of [undefined,{...final,verified:false},{...final,state:'REJECTED'},{...final,state:'STOPPED'},{...final,receipt_id:proof.dom_receipt_id},{...final,observation_sha256:d},{...final,terminal_receipt_sha256:c},{...final,attempt_id:'foreign'},{...final,reservation_receipt_id:'other'},{...final,turn:turn===2?3:2}]){
 const result=gate(sample,proof,bad);assert.equal(result.completion_ms,null);assert.equal(result.ttft_ms,null);assert.equal(result.native_accepted,false);count++;
 }
 const ok=gate(sample,proof,final);assert.equal(ok.status,'VERIFIED_COMPLETION_SAMPLE');assert.equal(ok.ttft_ms,10);assert.equal(ok.completion_ms,70);assert.equal(ok.stream_eof_ms,50);assert.equal(ok.native_accepted,false);count++;
 const stop=gate({...sample,outcome:'STOPPED',stop_ms:130},proof,undefined);assert.equal(stop.status,'RECOVERED_AFTER_STOP');assert.equal(stop.completion_ms,null);assert.equal(stop.recovery_ms,40);count++;
 }
 return count;
}
console.log('B4 R72 synthetic classification PASS '+runTests(assert,classifyCompletion,classifyFinalizedCompletion));
