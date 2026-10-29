import test from "node:test";
import assert from "node:assert/strict";
import {createVisualPlan,cinematicPrompt,requestViaExistingHost,verifyVisualPlan,verifyAsset} from "../src/generation.mjs";
import {COMPOSITIONS} from "../../NOX-WOW151-200/catalog.mjs";
const hash="a".repeat(64);
const approved={id:"original-obsidian",sha256:hash,kind:"texture",license:"NOX_ORIGINAL",approved:true};
const base={brief:"premium photorealistic night scene",output:"image",compositionId:151,assets:[approved]};
test("all 50 ending compositions can inform a distinct visual AI brief",()=>{
 assert.equal(COMPOSITIONS.length,50);
 const texts=new Set(),ids=new Set();
 for(const c of COMPOSITIONS){
  const plan=createVisualPlan({...base,compositionId:c.id});
  assert.equal(plan.status,"PLANNED_NOT_RENDERED");
  assert.equal(verifyVisualPlan(plan),true);
  ids.add(plan.composition.id);
  texts.add(cinematicPrompt(plan));
 }
 assert.equal(ids.size,50);assert.equal(texts.size,50);
});
for(const output of ["image","image_edit","video","scene3d","presentation","avatar","showcase"]){
 test("shared visual plan for "+output,()=>{
  const p=createVisualPlan({...base,output,ownerPersona:output==="avatar"?{
   approved:true,personaId:"waldemar-sorn",masterSha256:hash}:null});
  assert.equal(p.output,output);assert.ok(p.style.includes("no cartoon"));
 });
}
test("unapproved external materials and avatar masters fail closed",()=>{
 for(const a of [{...approved,approved:false},{...approved,sha256:"bad"},{...approved,license:"REVIEW_REQUIRED"},
  {...approved,license:"LICENSED_OWNER"},{...approved,id:"../secret"}]){
  assert.throws(()=>createVisualPlan({...base,assets:[a]}),/ASSET_SOURCE_NOT_APPROVED/);
 }
 assert.throws(()=>createVisualPlan({...base,output:"avatar"}),/PERSONA_IDENTITY_NOT_APPROVED/);
});
test("generation cannot bypass native consent or unconnected capability",async()=>{
 const p=createVisualPlan(base);
 await assert.rejects(requestViaExistingHost(null,p,{userConsent:true}),/TRUSTED_NATIVE_HOST_REQUIRED/);
 const host={capability:async()=>false,authorize:async()=>true,dispatch:async()=>({status:"QUEUED_NOT_RENDERED"})};
 await assert.rejects(requestViaExistingHost(host,p,{userConsent:false}),/TRUSTED_NATIVE_HOST_REQUIRED/);
 await assert.rejects(requestViaExistingHost(host,p,{userConsent:true}),/GENERATION_HOST_NOT_CONNECTED/);
});
test("authorized native queue is not counted as a rendered image",async()=>{
 const p=createVisualPlan(base),calls=[];
 const host={capability:async route=>{calls.push(route);return true},
  authorize:async req=>{calls.push(req.compositionId);return true},
  dispatch:async (route,body)=>{calls.push(body.prompt);return {status:"QUEUED_NOT_RENDERED",runId:"R-123"}}};
 const out=await requestViaExistingHost(host,p,{userConsent:true});
 assert.equal(out.status,"QUEUED_NOT_RENDERED");assert.equal(out.outputSha256,null);
 assert.equal(calls[0],"images.generate");assert.equal(calls[1],151);
});
test("host can claim completion only with actual output digest and run ID",async()=>{
 const p=createVisualPlan(base);
 const host={capability:async()=>true,authorize:async()=>true,
   dispatch:async()=>({status:"COMPLETED_VERIFIED",outputSha256:"bad",runId:"R-77"})};
 await assert.rejects(requestViaExistingHost(host,p,{userConsent:true}),/OUTPUT_RECEIPT_REQUIRED/);
 host.dispatch=async()=>({status:"COMPLETED_VERIFIED",outputSha256:hash,runId:"R-77"});
 const out=await requestViaExistingHost(host,p,{userConsent:true});
 assert.equal(out.status,"COMPLETED_VERIFIED");
 assert.equal(out.outputSha256,hash);
});
test("copy-only immutable plan and max source bounds",()=>{
 const a=createVisualPlan(base);
 assert.equal(Object.isFrozen(a),true);
 assert.equal(Object.isFrozen(a.resources),true);
 assert.throws(()=>createVisualPlan({...base,brief:"x".repeat(2600)}),/INVALID_BRIEF/);
 assert.throws(()=>createVisualPlan({...base,assets:Array(17).fill(approved)}),/ASSET_QUOTA/);
});
