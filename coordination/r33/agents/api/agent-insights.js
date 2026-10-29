"use strict";
/* Vercel Node function; deployed under an existing Vercel-protected project.
 * No model call without server-side OpenAI key, selected model, explicit budget
 * and NOX_AGENTS_ENABLED flag. Never expose raw private Git or user data.
 */
const {normalizeEvidence,configStatus,inspectWithAgent}=require("../nox_agents_sdk.cjs");
const httpError=(res,status,error)=>res.status(status).json({ok:false,error,source:"NOX_R33",analysis:null});
function originAllowed(req){
 const host=String(req.headers?.host||"").toLowerCase();
 const origin=String(req.headers?.origin||"");
 try{
  const u=new URL(origin);
  return u.protocol==="https:"&&u.host.toLowerCase()===host;
 }catch{return false}
}
module.exports=async function handler(req,res){
 res.setHeader("Cache-Control","private, no-store, max-age=0");
 res.setHeader("Content-Type","application/json; charset=utf-8");
 res.setHeader("X-Content-Type-Options","nosniff");
 if(req.method==="GET"){
   const s=configStatus();
   return res.status(200).json({ok:true,mode:"read_only",configured:s.ready,has_key:s.has_key,trace_enabled:s.tracing_enabled,reason:s.ready?"READY":"NO_KEY_OR_BUDGET",source:"NOX_R33"});
 }
 if(req.method!=="POST")return httpError(res,405,"METHOD_NOT_ALLOWED");
 // An authenticated Vercel deployment already supplies access control;
 // the Origin check prevents third-party browser sites initiating paid calls.
 if(!originAllowed(req))return httpError(res,403,"SAME_ORIGIN_REQUIRED");
 if(Number(req.headers["content-length"]||0)>3500)return httpError(res,413,"PAYLOAD_TOO_LARGE");
 try{
   const input=typeof req.body==="string"?JSON.parse(req.body):req.body;
   const evidence=normalizeEvidence(input);
   const result=await inspectWithAgent(evidence);
   return res.status(result.mode==="disabled"?503:200).json({ok:result.mode==="sdk",...result});
 }catch(e){
   // Do not surface raw model errors, keys, environment or private trace payloads.
   const message=String(e?.message||"");
   const status=/^NOX_(INPUT|HEAD|COUNT|EXTRA|PRIVATE|OUTPUT)/.test(message)?422:502;
   return httpError(res,status,status===422?"VALIDATION_REJECTED":"AGENT_UNAVAILABLE");
 }
};
