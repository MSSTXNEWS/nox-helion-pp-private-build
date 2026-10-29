"use strict";
const assert=require("node:assert/strict");
const mod=require("./chatgpt_otch1_adapter.js");
const HEAD="a".repeat(40),BLOB="b".repeat(40);
const p={git_blob:BLOB,git_url:"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/"+HEAD+"/coordination/manual/no1/receipt.json"};
const roster={owner_manual_roles:[{id:"1"},{id:"2"},{id:"3"}],automation_roles:[{id:"auto-A"}]};
const receipt=()=>({schema:"NOX_R31_CHATGPT_OTCH1_RECEIPT_V1",
  run_id:"NOX-M1-R31-C01",executor_id:"1",task_id:"P04/model_snapshot",
  started_at:"2026-10-30T00:00:00Z",finished_at:"2026-10-30T00:20:00Z",
  source_head:HEAD,approaches:[{n:1,status:"DONE",proof:p}],cycle_complete:false,
  gates:Object.fromEntries("ABCDE".split("").map(x=>[x,{status:"PARTIAL"}])),
  error_ids:["ERR-SRC-004"],stage:"INTEGRATED",physical_proof:p,
  journal_sync:"PENDING_T02",product_percent:null});
const go=x=>mod.check(x,roster,HEAD),has=(x,needle)=>x.problems.some(v=>v.includes(needle));
let r=receipt();assert(go(r).ok);assert.equal(go(r).approaches_proven,1);
r=receipt();r.cycle_complete=true;assert(has(go(r),"FALSE_10"));
r=receipt();r.source_head="c".repeat(40);assert(has(go(r),"STALE_HEAD"));
r=receipt();r.gates.A={status:"PASS"};assert(has(go(r),"GATE_PROOF_MISSING_A"));
r=receipt();r.stage="QA_ACCEPTED";assert(has(go(r),"QA_ACCEPTED_NOT_SELF"));
r=receipt();r.journal_sync="PASS";assert(has(go(r),"JOURNAL_PASS"));
r=receipt();r.physical_proof=null;assert(has(go(r),"PHYSICAL_PROOF_MISSING"));
r=receipt();r.product_percent=100;assert(has(go(r),"PRODUCT_PERCENT"));
r=receipt();r.executor_id="new-auto-not-in-roster";assert(has(go(r),"EXECUTOR_NOT_IN_APPROVED"));
r=receipt();r.approaches=[{n:2,status:"DONE",proof:p}];assert(has(go(r),"APPROACH_ORDER"));
r=receipt();r.approaches=[{n:1,status:"DONE"}];assert(has(go(r),"APPROACH_PROOF"));
r=receipt();r.error_ids=null;assert(has(go(r),"ERROR_IDS"));
r=receipt();assert.deepEqual(JSON.parse(JSON.stringify(mod.parseMarked("x NOX_OTCH1_JSON_BEGIN\n"+JSON.stringify(r)+"\nNOX_OTCH1_JSON_END"))),r);
assert.equal(mod.parseMarked("BAD_REPORT_WITHOUT_MARKERS"),null);
console.log("NOX ChatGPT R31 adapter: 14 validation checks passed");
