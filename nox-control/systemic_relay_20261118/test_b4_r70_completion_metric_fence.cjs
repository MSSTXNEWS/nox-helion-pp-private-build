'use strict';
const {classifyCompletion}=require('./b4_r70_completion_metric_fence.cjs');
function targetedCheck(classify){
 const h=n=>String(n).repeat(64), s={conversation_id:'existing',exchange_id:'turn-2',clock_id:'browser-1',terminal_event_id:'turn-2:terminal',served_sha256:h(1),begin_ms:100,first_visible_ms:110,eof_ms:150,outcome:'STREAM_ENDED_READBACK_REQUIRED'};
 const p={conversation_id:s.conversation_id,exchange_id:s.exchange_id,clock_id:s.clock_id,terminal_event_id:s.terminal_event_id,served_sha256:s.served_sha256,verified:true,dom_receipt_id:'dom2',canonical_receipt_id:'s03-2',dom_sha256:h(2),answer_sha256:h(2),dom_commit_ms:170};
 const cases=[
 ['R80 partial terminal',s,{...p,dom_sha256:h(3)},'HOLD_CANONICAL_TEXT',null,null],
 ['EOF without witness',s,null,'HOLD_PROVENANCE',null,null],
 ['wrong exchange',s,{...p,exchange_id:'turn-3'},'HOLD_SCOPE',null,null],
 ['same receipt',s,{...p,dom_receipt_id:p.canonical_receipt_id},'HOLD_PROVENANCE',null,null],
 ['STOP and full recovery',{...s,outcome:'STOPPED',stop_ms:130},p,'RECOVERED_AFTER_STOP',null,40],
 ['clock inversion',s,{...p,dom_commit_ms:149},'HOLD_CLOCK',null,null],
 ['full turn 3',{...s,exchange_id:'turn-3',terminal_event_id:'turn-3:terminal'},{...p,exchange_id:'turn-3',terminal_event_id:'turn-3:terminal',dom_receipt_id:'dom3',canonical_receipt_id:'s03-3'},'VERIFIED_COMPLETION_SAMPLE',70,null]
 ];
 return cases.map(([name,a,b,status,completion,recovery])=>{const r=classify(a,b);if(r.status!==status||r.completion_ms!==completion||r.recovery_ms!==recovery||r.native_accepted!==false||r.ttft_ms!==(completion===null?null:10))throw Error(name+': '+JSON.stringify(r));return {name,...r};});
}
console.log(JSON.stringify(targetedCheck(classifyCompletion))); console.log('7/7 synthetic classification; native_accepted=false');
