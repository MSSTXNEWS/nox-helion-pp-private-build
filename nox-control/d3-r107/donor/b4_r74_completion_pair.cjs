'use strict';
const {classifyPinnedCompletion}=require('./b4_r73_pinned_disposition_metric_bridge.cjs');
const scope=['conversation_id','physical_dialog_id','s03_dialog_id','session_id','served_sha256','server_sha256','owner_admission_receipt_sha256','browser_sha256'];
const ids=['exchange_id','request_id','attempt_id','event_id','turn_id','user_message_id','assistant_message_id','terminal_event_id'];
// Consume an entire independently authenticated existing-dialog pair, not two
// independently counted completions. No durable deduplication or ACK authority.
function classifyCompletionPair(turns,quality){
 const hold=()=>Object.freeze({status:'HOLD_COMPLETION_PAIR',samples:Object.freeze([]),native_accepted:false});
 try{
  if(!Array.isArray(turns)||turns.length!==2)return hold();
  const samples=[],proofs=[],seen=new Set();
  for(let i=0;i<2;i++){
   const {receipts,trusted}=turns[i];
   const result=classifyPinnedCompletion(receipts,quality,trusted);
   if(result.status!=='VERIFIED_COMPLETION_SAMPLE'||result.turn!==i+2)return hold();
   const p=trusted.proof;
   // R73 has validated the exact detached disposition and proof binding.
   const f=JSON.parse(receipts.disposition.toString('utf8'));
   for(const id of [p.observation_id,p.reservation_receipt_id,f.disposition_id,p.dom_receipt_id,p.canonical_receipt_id]){
    if(seen.has(id))return hold();
    seen.add(id);
   }
   proofs.push(p);samples.push(result);
  }
  const [a,b]=proofs;
  if(scope.some(k=>a[k]!==b[k])||ids.some(k=>a[k]===b[k]))return hold();
  if(a.user_message_id===b.assistant_message_id||a.assistant_message_id===b.user_message_id)return hold();
  if(a.terminal_receipt_sha256===b.terminal_receipt_sha256)return hold();
  if(a.clock_id===b.clock_id&&turns[1].trusted.sample.begin_ms<a.dom_commit_ms)return hold();
  return Object.freeze({status:'VERIFIED_COMPLETION_PAIR',samples:Object.freeze(samples),native_accepted:false});
 }catch{return hold();}
}
module.exports={classifyCompletionPair};
