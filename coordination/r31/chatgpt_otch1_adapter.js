/* NOX R31 · ChatGPT OTCH-1 drop-in adapter.
 * Parses machine-readable receipts emitted by existing ChatGPT manual/auto chats.
 * Shape validation != proof authentication: T02 must Git fetch, compare exact blob,
 * validate same HEAD and journal CAS before any accepted status.
 * No model/ChatGPT internal patches or automatic writes.
 */
(function(root,factory){
 const api=factory();
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 if(root)root.NOX_CHATGPT_OTCH1=api;
})(typeof window!=="undefined"?window:null,function(){
 "use strict";
 const SHA=/^[a-f0-9]{40}$/i;
 const GATES=["A","B","C","D","E"];
 const STAGES=["SOURCE_PREPARED","SOURCE_VERIFIED","INTEGRATED","QA_PENDING","QA_REJECTED","QA_ACCEPTED"];
 const STATES=["PASS","PARTIAL","BLOCKED","NOT_RUN"];
 const id=s=>typeof s==="string"&&/^[A-Za-z0-9][\w./:-]{0,180}$/.test(s);
 const sha=s=>typeof s==="string"&&SHA.test(s);
 const date=s=>typeof s==="string"&&Number.isFinite(Date.parse(s));
 const proof=p=>p&&typeof p==="object"&&sha(p.git_blob)&&typeof p.git_url==="string"&&
   /^https:\/\/github\.com\/MSSTXNEWS\/nox-helion-pp-private-build\/blob\/[a-f0-9]{40}\//i.test(p.git_url);
 function check(receipt,roster,expectedHead){
  const problems=[];
  if(!receipt||receipt.schema!=="NOX_R31_CHATGPT_OTCH1_RECEIPT_V1")return {ok:false,problems:["BAD_SCHEMA"]};
  if(!id(receipt.run_id))problems.push("RUN_ID_INVALID");
  if(!id(receipt.executor_id))problems.push("EXECUTOR_ID_INVALID");
  if(!date(receipt.started_at)||!date(receipt.finished_at)||Date.parse(receipt.finished_at)<Date.parse(receipt.started_at))
   problems.push("ACTUAL_TIMES_INVALID");
  if(!sha(receipt.source_head))problems.push("HEAD_INVALID");
  if(expectedHead&&receipt.source_head!==expectedHead)problems.push("STALE_HEAD");
  const owner=(roster?.owner_manual_roles||[]).some(x=>String(x.id)===String(receipt.executor_id))||
              (roster?.automation_roles||[]).some(x=>String(x.id)===String(receipt.executor_id));
  if(!owner)problems.push("EXECUTOR_NOT_IN_APPROVED_ROSTER");
  const steps=receipt.approaches;
  if(!Array.isArray(steps)||steps.length>10)problems.push("APPROACHES_INVALID");
  else{
   const indices=steps.map(x=>x?.n);
   if(indices.some((v,i)=>v!==i+1))problems.push("APPROACH_ORDER_INVALID");
   for(const step of steps){
    if(step.status==="DONE"&&!proof(step.proof))problems.push("APPROACH_PROOF_MISSING_"+step.n);
    if(!["DONE","BLOCKED","NOT_RUN"].includes(step.status))problems.push("APPROACH_STATUS_INVALID_"+step.n);
   }
  }
  if(receipt.cycle_complete===true&&(!Array.isArray(steps)||steps.length!==10||steps.some(x=>x.status!=="DONE")))
   problems.push("FALSE_10_APPROACH_COMPLETION");
  const gates=receipt.gates;
  if(!gates||GATES.some(k=>!gates[k]||!STATES.includes(gates[k].status)))problems.push("GATES_MISSING_OR_INVALID");
  else for(const k of GATES)if(gates[k].status==="PASS"&&!proof(gates[k].proof))
    problems.push("GATE_PROOF_MISSING_"+k);
  if(!Array.isArray(receipt.error_ids)||receipt.error_ids.some(x=>!id(x)))problems.push("ERROR_IDS_MISSING_OR_INVALID");
  if(!id(receipt.task_id))problems.push("TASK_ID_INVALID");
  if(!STAGES.includes(receipt.stage))problems.push("STAGE_INVALID");
  // Accepting product work is a separate independent QA gate, not part of this format.
  if(receipt.stage==="QA_ACCEPTED")problems.push("QA_ACCEPTED_NOT_SELF_ATTESTABLE");
  if(receipt.journal_sync==="PASS")problems.push("JOURNAL_PASS_REQUIRES_T02_INDEPENDENT_READBACK");
  if(!["PENDING_T02","BLOCKED_T02","VERIFIED_BY_T02"].includes(receipt.journal_sync))
    problems.push("JOURNAL_SYNC_UNKNOWN");
  if(!proof(receipt.physical_proof)&&receipt.stage!=="QA_PENDING"&&receipt.stage!=="QA_REJECTED")
    problems.push("PHYSICAL_PROOF_MISSING");
  if(receipt.product_percent!=null)problems.push("PRODUCT_PERCENT_NOT_SELF_ATTESTABLE");
  const done=Array.isArray(steps)?steps.filter(x=>x.status==="DONE"&&proof(x.proof)).length:0;
  return {ok:problems.length===0,problems,run_id:receipt.run_id,
    executor_id:receipt.executor_id,head:receipt.source_head,approaches_proven:done,
    cycle_total:10,proof_status:"NEEDS_GIT_READBACK",accepted_delta:null,
    journal_status:"REQUIRES_T02_CAS_READBACK"};
 }
 function parseMarked(text){
  if(typeof text!=="string")return null;
  const open="NOX_OTCH1_JSON_BEGIN",close="NOX_OTCH1_JSON_END";
  const a=text.lastIndexOf(open),b=a<0?-1:text.indexOf(close,a+open.length);
  if(a<0||b<0)return null;
  const raw=text.slice(a+open.length,b).trim();
  if(raw.length>30000)return null;
  try{return JSON.parse(raw);}catch(e){return null;}
 }
 return {check,parseMarked};
});