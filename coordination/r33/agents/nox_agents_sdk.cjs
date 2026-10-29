"use strict";
/*
 * NOX R33 · OpenAI Agents SDK observer — optional, server-side, read-only.
 * This module NEVER updates source, Git, T02, QA or release gates.
 * Current ChatGPT manual roles remain the primary owners.
 *
 * SDK: @openai/agents (official OpenAI Agents SDK). It is dynamically imported
 * only after opt-in, a server-side key, and deterministic guards pass.
 */
const HEAD=/^[0-9a-f]{40}$/i;
const SECRET=/(sk-(?:proj-)?[a-z0-9_-]{12,}|gh[opusr]_[a-z0-9]{12,}|glpat-[a-z0-9_-]{12,}|-----BEGIN [^-]+ PRIVATE KEY-----)/i;
const ALLOWED_KEYS=new Set(["head","manuals","automations","errors","accepted","source_ready","journal_sync","last_run_at","task_ids"]);
function isPlain(x){return x&&typeof x==="object"&&!Array.isArray(x)&&Object.getPrototypeOf(x)===Object.prototype;}
function normalizeEvidence(raw){
 if(!isPlain(raw))throw Error("NOX_INPUT_INVALID");
 if(!HEAD.test(String(raw.head||"")))throw Error("NOX_HEAD_REQUIRED");
 const value={head:String(raw.head).toLowerCase()};
 const numeric=["manuals","automations","errors","accepted"];
 for(const k of numeric){
  const n=raw[k];
  if(!Number.isSafeInteger(n)||n<0||n>100000)throw Error("NOX_COUNT_INVALID_"+k);
  value[k]=n;
 }
 value.source_ready=raw.source_ready===true;
 value.journal_sync=raw.journal_sync==="PASS"?"PASS":"UNVERIFIED";
 value.last_run_at=typeof raw.last_run_at==="string"&&Number.isFinite(Date.parse(raw.last_run_at))?raw.last_run_at:null;
 value.task_ids=Array.isArray(raw.task_ids)?raw.task_ids.filter(x=>typeof x==="string"&&/^[A-Za-z0-9][\w./:-]{0,90}$/.test(x)).slice(0,24):[];
 if(Object.keys(raw).some(k=>!ALLOWED_KEYS.has(k)))throw Error("NOX_EXTRA_FIELDS_DISALLOWED");
 const data=JSON.stringify(value);
 if(SECRET.test(data)||data.length>2400)throw Error("NOX_PRIVATE_OR_EXCESSIVE_INPUT");
 return value;
}
function configStatus(env=process.env){
 const hasKey=typeof env.OPENAI_API_KEY==="string"&&env.OPENAI_API_KEY.length>20;
 const hasModel=typeof env.NOX_AGENT_MODEL==="string"&&/^[A-Za-z0-9][A-Za-z0-9_.\/-]{2,70}$/.test(env.NOX_AGENT_MODEL);
 const enabled=env.NOX_AGENTS_ENABLED==="true";
 const budget=Number(env.NOX_AGENT_DAILY_BUDGET_USD||0);
 return {enabled,has_key:hasKey,model_configured:hasModel,
   budget_configured:Number.isFinite(budget)&&budget>0&&budget<=50,
   tracing_enabled:env.NOX_AGENTS_TRACE==="true",
   ready:enabled&&hasKey&&hasModel&&Number.isFinite(budget)&&budget>0&&budget<=50};
}
function blockUnsafeOutput(out){
 if(typeof out!=="string"||out.length>3500||SECRET.test(out))return true;
 return /(?:QA_ACCEPTED|SOURCE_READY|RELEASE_READY)\s*(?::|=)\s*(?:TRUE|PASS|100%)/i.test(out);
}
async function inspectWithAgent(input,{env=process.env,loadSdk=()=>import("@openai/agents")}={}){
 const evidence=normalizeEvidence(input);
 const config=configStatus(env);
 if(!config.ready)return {mode:"disabled",reason:!config.enabled?"NOT_ENABLED":!config.has_key?"OPENAI_API_KEY_MISSING":!config.model_configured?"NOX_AGENT_MODEL_UNSET":"BUDGET_CAP_MISSING",analysis:null,head:evidence.head};
 // A call is opt-in per user click. There are no cron/automatic model calls.
 // Budget requires external durable enforcement for sustained spend; the caller
 // must provide an independently tracked budget latch, not this local process.
 if(env.NOX_DURABLE_BUDGET_APPROVED!=="true")
  return {mode:"disabled",reason:"DURABLE_SPEND_CAP_NOT_ENFORCED",analysis:null,head:evidence.head};
 const sdk=await loadSdk();
 if(typeof sdk.Agent!=="function"||typeof sdk.run!=="function"||typeof sdk.withTrace!=="function")
   throw Error("OPENAI_AGENTS_SDK_INCOMPATIBLE");
 const guardInput={
   name:"NOX aggregate only",runInParallel:false,
   execute:async({input})=>({outputInfo:{aggregateOnly:true},tripwireTriggered:typeof input!=="string"||input.length>2800||SECRET.test(input)})
 };
 const guardOutput={
   name:"NOX no self-acceptance",execute:async({agentOutput})=>({
     outputInfo:{sourceOnly:true},tripwireTriggered:blockUnsafeOutput(String(agentOutput||""))
   })
 };
 const agent=new sdk.Agent({
  name:"NOX Read-only Operations Analyst",
  model:env.NOX_AGENT_MODEL,
  instructions:"Read only the supplied aggregate NOX status. Give a concise Russian analysis of evidence gaps, delivery failures and the single most useful next manual-owner action. Never claim to execute work, write Git, accept QA, change budgets, or approve build/release. No secret speculation. Do not invent dates or metrics.",
  inputGuardrails:[guardInput],outputGuardrails:[guardOutput],tools:[]
 });
 const prompt="NOX aggregate evidence (not confidential data): "+JSON.stringify(evidence);
 const started=Date.now();
 const result=await sdk.withTrace("NOX R33 evidence-only observer",()=>sdk.run(agent,prompt,{maxTurns:1,workflowName:"NOX R33 guardrails"}));
 const finalOutput=String(result?.finalOutput??"");
 if(blockUnsafeOutput(finalOutput))throw Error("NOX_OUTPUT_GUARDRAIL");
 return {mode:"sdk",reason:null,head:evidence.head,analysis:finalOutput,
   elapsed_ms:Date.now()-started,accepted_delta:null,
   trace_note:config.tracing_enabled?"SDK_TRACING_POLICY_ENABLED":"SDK_DEFAULT_TRACING_APPLIES"};
}
module.exports={normalizeEvidence,configStatus,blockUnsafeOutput,inspectWithAgent};
