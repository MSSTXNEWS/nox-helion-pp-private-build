import test from "node:test";
import assert from "node:assert/strict";
import {evaluateFiniteSource} from "./finite_acceptance_r33.mjs";

const hex=(x)=>x.repeat(40);
const base=()=>({
  head:hex("a"),tree:hex("b"),
  sources:[{path:"Packages/P03/Source/P03.ModelCenter.Wow/ui.js",blob:hex("c")}],
  ownerEvidenceBlob:hex("d"),criteria:[],
  host50:{total:50,bound:40,nativePending:14},
  archive:{parts:3,files:729,verified:false},
  gitlabBuild:false
});
test("No full TaskID ledger means product percentage stays N/D",()=>{
  const x=evaluateFiniteSource(base());
  assert.equal(x.phase,"SOURCE_GATES_INCOMPLETE");
  assert.equal(x.completed,0);
  assert.equal(x.productPercent,null);
  assert.equal(x.sourceCoverage,.8);
});
test("No new owner/meaningful source change stops repeated cycles",()=>{
  const a=base(),x=evaluateFiniteSource(a,a);
  assert.equal(x.phase,"WAITING_OWNER_SOURCE_CHANGE");
  assert.equal(x.runAnotherQaCycle,false);
});
test("Changed source blob alone enables focused delta QA, not acceptance",()=>{
  const a=base(),b=base();b.sources[0].blob=hex("e");
  const x=evaluateFiniteSource(b,a);
  assert.equal(x.runAnotherQaCycle,true);
  assert.equal(x.ready,false);
});
test("Missing HEAD/tree fails closed",()=>{
  const x=evaluateFiniteSource({...base(),head:null});
  assert.equal(x.phase,"HOLD_INVALID_HEAD");
  assert.equal(x.productPercent,null);
});
test("Duplicate path cannot masquerade as two source proofs",()=>{
  const a=base();a.sources.push(a.sources[0]);
  assert.ok(evaluateFiniteSource(a).errors.includes("SOURCE_BLOB_LIST_MISSING_OR_INVALID"));
});
test("A build flag before valid gates is a blocker, not progress",()=>{
  assert.ok(evaluateFiniteSource({...base(),gitlabBuild:true}).errors.includes("PREMATURE_GITLAB_BUILD_ATTEMPT"));
});
test("Self-declared acceptance without Git readback is not criterion PASS",()=>{
  const a=base();a.criteria=[{id:"P01",head:a.head,status:"SOURCE_VERIFIED",readback:false}];
  assert.equal(evaluateFiniteSource(a).completed,0);
});
test("Different T08 HEAD is never same-SHA acceptance",()=>{
  const a=base();a.t08={head:hex("e"),receiptBlob:hex("f"),independent:true,accepted:true,readback:true};
  assert.ok(evaluateFiniteSource(a).errors.includes("INDEPENDENT_T08_SAME_HEAD_NOT_ACCEPTED"));
});
test("Even perfect self-declared metadata cannot self-sign T10",()=>{
  const a=base(),r=hex("c");
  a.criteria=["base","P01","P02","P03","P04","P05","common_integration","accepted_head_manifest"]
    .map(id=>({id,head:a.head,sourceBlob:r,receiptBlob:r,testReceiptBlob:r,readback:true,status:"SOURCE_VERIFIED"}));
  a.host50={total:50,bound:50,nativePending:0};
  a.archive={parts:3,files:729,verified:true,sha256:"f".repeat(64)};
  a.t08={head:a.head,receiptBlob:r,independent:true,accepted:true,readback:true};
  a.t09={head:a.head,tree:a.tree,frozen:true,receiptBlob:r};
  a.t10={head:a.head,accepted:true,receiptBlob:r,readback:true};
  const x=evaluateFiniteSource(a);
  assert.equal(x.completed,8);
  assert.equal(x.ready,false);
  assert.equal(x.phase,"READY_FOR_EXTERNAL_SIGNED_ACCEPTANCE");
  assert.equal(x.productPercent,null);
});
