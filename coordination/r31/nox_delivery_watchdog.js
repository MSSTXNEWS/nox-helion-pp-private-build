/* NOX R31 · Fail-closed receipt delivery watchdog, no dependencies.
   Consumes authenticated snapshots made by existing T02 coordination owner.
   Never grants write permissions or promotes acceptance.
*/
(function(root,factory){
 const api=factory();
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 if(root)root.NOX_DELIVERY_WATCHDOG=api;
})(typeof window!=="undefined"?window:null,function(){
 "use strict";
 const SHA=/^[0-9a-f]{40}$/;
 const ID=/^[a-z0-9][\w./:-]{0,180}$/i;
 const iso=s=>typeof s==="string"&&Number.isFinite(Date.parse(s));
 const sha=s=>typeof s==="string"&&SHA.test(s);
 const id=s=>typeof s==="string"&&ID.test(s);
 const validProof=p=>p&&typeof p==="object"&&sha(p.blob)&&sha(p.head)&&
   typeof p.url==="string"&&/^https:\/\/github\.com\/MSSTXNEWS\/nox-helion-pp-private-build\/(blob\/[a-f0-9]{40}\/|issues\/177#issuecomment-)/.test(p.url)&&
   p.readback===true;
 const states=["completed","failed","in_progress","no_update"];
 const normalizedTask=t=>t&&typeof t==="object"&&id(t.id)&&typeof t.title==="string"&&typeof t.enabled==="boolean";
 function evaluate(input,opts){
  opts=opts||{};
  if(!input||input.schema!=="NOX_R31_DELIVERY_INPUT_V1"||!iso(input.observed_at)||
     !sha(input.head)||!Array.isArray(input.executors)||!Array.isArray(input.receipts))
      return{ok:false,errors:["INVALID_INPUT_SCHEMA_OR_SOURCE"],workers:[],summary:null};
  const now=iso(opts.now)?Date.parse(opts.now):Date.parse(input.observed_at);
  if(now<Date.parse(input.observed_at)-60000)return{ok:false,errors:["FUTURE_OBSERVATION"],workers:[],summary:null};
  const errors=[],byWorker=new Map(),receiptIds=new Set(),receiptMap=new Map();
  for(const t of input.executors){
   if(!normalizedTask(t)||byWorker.has(t.id)){errors.push("INVALID_OR_DUPLICATE_EXECUTOR");continue;}
   if(t.category!=="manual"&&t.category!=="auto"){errors.push("INVALID_EXECUTOR_CATEGORY:"+t.id);continue;}
   if(t.category==="auto"&&t.scope!=="current"&&t.scope!=="historical"&&t.scope!=="unassigned"){
    errors.push("INVALID_SCOPE:"+t.id);continue;
   }
   if(t.last_run!=null&&(!id(t.last_run.id)||!iso(t.last_run.started_at)||
        !states.includes(t.last_run.status)||t.last_run.completed_at!=null&&!iso(t.last_run.completed_at)))
    errors.push("INVALID_RUN:"+t.id);
   byWorker.set(t.id,t);
  }
  for(const r of input.receipts){
   if(!r||!id(r.executor_id)||!id(r.run_id)||!iso(r.at)){errors.push("INVALID_RECEIPT");continue;}
   const fingerprint=r.executor_id+"::"+r.run_id;
   if(receiptIds.has(fingerprint)){errors.push("DUPLICATE_RECEIPT:"+fingerprint);continue;}
   receiptIds.add(fingerprint);
   if(!byWorker.has(r.executor_id)){errors.push("ORPHAN_RECEIPT:"+fingerprint);continue;}
   if(r.task_id!=null&&!id(r.task_id))errors.push("INVALID_TASK_ID:"+fingerprint);
   if(r.proof!=null&&!validProof(r.proof))errors.push("UNVERIFIED_RECEIPT:"+fingerprint);
   receiptMap.set(fingerprint,r);
  }
  const maxDelay=Number.isFinite(opts.grace_minutes)&&opts.grace_minutes>=0?opts.grace_minutes:30;
  const receiptCoverageComplete=input.receipt_index_complete===true;
  const workers=[...byWorker.values()].map(t=>{
   const run=t.last_run||null, rr=run?receiptMap.get(t.id+"::"+run.id):null;
   const last=run?.completed_at||run?.started_at||null;
   let status="NOT_OBSERVED",reason="No verified current run";
   if(run){
    if(rr&&validProof(rr.proof)&&rr.proof.head!==undefined&&rr.proof.head!==input.head){
     status="STALE_HEAD";reason="Receipt HEAD differs from current source";
    }else if(rr&&validProof(rr.proof)){
     status="DELIVERED_VERIFIED";reason="Exact latest RunID has immutable Git readback";
    }else if(rr){
     status="REPORTED_UNVERIFIED";reason="Report exists but immutable proof has not been read back";
    }else if(run.status==="in_progress"){
     status="RUN_IN_PROGRESS";reason="In progress; receipt not yet due";
    }else if(!receiptCoverageComplete){
     status="RECEIPT_INDEX_INCOMPLETE";reason="Coverage is not independently complete; missing receipt is not proven";
    }else if(!iso(last)){
     status="NOT_OBSERVED";reason="Run lacks factual completion timestamp";
    }else if((now-Date.parse(last))/60000>=maxDelay){
     status="MISSING_RECEIPT";reason="Last completed/failed run is missing a receipt past grace period";
    }else{
     status="AWAITING_RECEIPT";reason="Latest run within delivery grace period";
    }
   }
   return{id:t.id,title:t.title,category:t.category,scope:t.scope||"current",enabled:t.enabled,
    last_run_id:run?.id||null,last_run_at:last,last_run_status:run?.status||null,status,reason,
    receipt_proof:rr&&validProof(rr.proof)?rr.proof.url:null};
  });
  const current=workers.filter(x=>x.scope==="current");
  const count=s=>current.filter(x=>x.status===s).length;
  const summary={manual_current:current.filter(x=>x.category==="manual").length,
   auto_current:current.filter(x=>x.category==="auto").length,
   delivered_verified:count("DELIVERED_VERIFIED"),
   reported_unverified:count("REPORTED_UNVERIFIED"),
   missing:count("MISSING_RECEIPT"),
   in_progress:count("RUN_IN_PROGRESS"),
   awaiting:count("AWAITING_RECEIPT"),
   not_observed:count("NOT_OBSERVED"),
   index_incomplete:count("RECEIPT_INDEX_INCOMPLETE"),
   error_count:errors.length,
   reliable:false
  };
  summary.reliable=errors.length===0&&current.length>0&&current.every(x=>x.status==="DELIVERED_VERIFIED");
  const journal=input.journal||{};
  const journalVerified=journal.status==="PASS"&&validProof(journal.proof)&&journal.head===input.head;
  const panel=input.panel||{};
  const panelVerified=panel.status==="PASS"&&validProof(panel.proof)&&panel.head===input.head;
  const feed={ok:errors.length===0,errors,workers,summary,
   journal_sync:journalVerified?"PASS":"BLOCKED_OR_UNVERIFIED",
   panel_sync:panelVerified?"PASS":"BLOCKED_OR_UNVERIFIED",
   complete:summary.reliable&&journalVerified&&panelVerified,
   observed_at:input.observed_at,head:input.head};
  return feed;
 }
 return{evaluate,validProof};
});