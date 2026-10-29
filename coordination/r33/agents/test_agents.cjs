"use strict";
const assert=require("node:assert/strict");
const {normalizeEvidence,configStatus,blockUnsafeOutput,inspectWithAgent}=require("./nox_agents_sdk.cjs");
const HEAD="a".repeat(40);
const input={head:HEAD,manuals:3,automations:15,errors:11,accepted:0,source_ready:false,journal_sync:"BLOCKED",last_run_at:"2026-10-30T00:00:00Z",task_ids:["P04/model_snapshot"]};
async function main(){
 let checks=0;
 const equal=(a,b)=>{assert.equal(a,b);checks++};
 equal(normalizeEvidence(input).head,HEAD);
 assert.throws(()=>normalizeEvidence({...input,token:"sk-demo"}),/EXTRA/);checks++;
 assert.throws(()=>normalizeEvidence({...input,head:"not-a-sha"}),/HEAD/);checks++;
 assert.throws(()=>normalizeEvidence({...input,accepted:-3}),/COUNT/);checks++;
 equal(blockUnsafeOutput("QA_ACCEPTED: PASS"),true);
 equal(blockUnsafeOutput("Only read-only notes; no release."),false);
 equal(configStatus({}).ready,false);
 equal(configStatus({NOX_AGENTS_ENABLED:"true",OPENAI_API_KEY:"test-cred-abcdefghijklmnopqr",NOX_AGENT_MODEL:"gpt-test",NOX_AGENT_DAILY_BUDGET_USD:"1"}).ready,true);
 let called=0;const fake={Agent:class {constructor(settings){this.settings=settings;}},run:async()=>{called++;return {finalOutput:"На текущем SHA нет независимой QA: требуется приёмка №2."}},withTrace:async(name,fn)=>{equal(name,"NOX R33 evidence-only observer");return fn();}};
 let r=await inspectWithAgent(input,{env:{},loadSdk:async()=>fake});
 equal(r.mode,"disabled");equal(called,0);
 const cfg={NOX_AGENTS_ENABLED:"true",OPENAI_API_KEY:"test-cred-abcdefghijklmnopqr",NOX_AGENT_MODEL:"gpt-test",NOX_AGENT_DAILY_BUDGET_USD:"1"};
 r=await inspectWithAgent(input,{env:cfg,loadSdk:async()=>fake});
 equal(r.reason,"DURABLE_SPEND_CAP_NOT_ENFORCED");equal(called,0);
 r=await inspectWithAgent(input,{env:{...cfg,NOX_DURABLE_BUDGET_APPROVED:"true"},loadSdk:async()=>fake});
 equal(r.mode,"sdk");equal(called,1);
 assert(r.analysis.includes("№2"));checks++;
 let blocked=0;try{await inspectWithAgent(input,{env:{...cfg,NOX_DURABLE_BUDGET_APPROVED:"true"},loadSdk:async()=>({...fake,run:async()=>({finalOutput:"SOURCE_READY = PASS"})})});}catch(e){blocked++;}equal(blocked,1);
 console.log("NOX R33 Agents SDK observer: "+checks+" checks PASS");
}
main().catch(e=>{console.error(e);process.exitCode=1});
