"use strict";
const assert=require("node:assert/strict");
const watch=require("./nox_delivery_watchdog.js");
const HEAD="a".repeat(40),BLOB="b".repeat(40),NOW="2026-10-30T01:00:00Z";
const proof={blob:BLOB,head:HEAD,url:"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/"+HEAD+"/coordination/r31/receipt.json",readback:true};
function fixture(){
 return{schema:"NOX_R31_DELIVERY_INPUT_V1",observed_at:NOW,head:HEAD,
  executors:[{id:"1",title:"Manual №1",category:"manual",scope:"current",enabled:true,
   last_run:{id:"M1-20261030-C01",started_at:"2026-10-30T00:05:00Z",
      completed_at:"2026-10-30T00:20:00Z",status:"completed"}}],
  receipts:[{executor_id:"1",run_id:"M1-20261030-C01",at:"2026-10-30T00:20:00Z",
    task_id:"P04/model_snapshot",proof}],
  journal:{status:"PASS",head:HEAD,proof},panel:{status:"PASS",head:HEAD,proof}};
}
const evaluation=x=>watch.evaluate(x,{now:NOW,grace_minutes:30});
let x=fixture(),z=evaluation(x);assert.equal(z.complete,true);assert.equal(z.workers[0].status,"DELIVERED_VERIFIED");
x=fixture();x.receipts=[];z=evaluation(x);assert.equal(z.workers[0].status,"MISSING_RECEIPT");assert.equal(z.complete,false);
x=fixture();x.receipts[0].proof=null;z=evaluation(x);assert.equal(z.workers[0].status,"REPORTED_UNVERIFIED");
x=fixture();x.receipts[0].proof.head="c".repeat(40);z=evaluation(x);assert.equal(z.workers[0].status,"STALE_HEAD");
x=fixture();x.journal.status="PARTIAL";z=evaluation(x);assert.equal(z.complete,false);assert.equal(z.journal_sync,"BLOCKED_OR_UNVERIFIED");
x=fixture();x.panel.proof=null;z=evaluation(x);assert.equal(z.panel_sync,"BLOCKED_OR_UNVERIFIED");
x=fixture();x.receipts.push({...x.receipts[0]});z=evaluation(x);assert.equal(z.ok,false);assert(z.errors.some(e=>e.includes("DUPLICATE_RECEIPT")));
x=fixture();x.executors.push({...x.executors[0]});z=evaluation(x);assert.equal(z.ok,false);
x=fixture();x.executors[0].last_run={id:"newrun",started_at:"2026-10-30T00:58:00Z",status:"in_progress"};z=evaluation(x);assert.equal(z.workers[0].status,"RUN_IN_PROGRESS");assert.equal(z.complete,false);
x=fixture();x.executors[0].last_run={id:"newrun",started_at:"2026-10-30T00:54:00Z",status:"completed",completed_at:"2026-10-30T00:55:00Z"};z=evaluation(x);assert.equal(z.workers[0].status,"AWAITING_RECEIPT");
x=fixture();x.receipts=[];x.executors[0].scope="historical";z=evaluation(x);assert.equal(z.summary.manual_current,0);assert.equal(z.complete,false);
x=fixture();x.receipts[0].proof.url="https://attacker.invalid/receipt";z=evaluation(x);assert.equal(z.workers[0].status,"REPORTED_UNVERIFIED");
console.log("NOX R31: 12 delivery watchdog checks passed");
