/* NOX shared visual assets + AI generation planning for existing native host only.
   Does not create another LLM, image model, video renderer, API, or bypass filters. */
import {COMPOSITIONS,COMPOSITION_BY_ID} from "../../NOX-WOW151-200/catalog.mjs";
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}$/;
const HASH=/^[a-f0-9]{64}$/i;
const allowed=new Set(["image","image_edit","video","scene3d","presentation","avatar","showcase"]);
const profiles=Object.freeze({ECO:{width:768,height:432,fps:12},BALANCED:{width:1280,height:720,fps:24},MAX:{width:1920,height:1080,fps:30}});
const sourceStyles=Object.freeze(["cinematic obsidian","deep graphite","filmic highlights","plausible motivated lighting",
 "restrained warm amber","cold cyan accent","physical scale","subtle atmosphere","no cartoon","legible details"]);
function fail(s){throw Error(s)}
export function verifyAsset(asset){
 if(!asset||typeof asset!=="object"||asset.approved!==true||!ID.test(asset.id||"")||
  !HASH.test(asset.sha256||"")||!["NOX_ORIGINAL","CC0-1.0","MIT","LICENSED_OWNER"].includes(asset.license)||
  !["glb","gltf","exr","hdr","texture","image","video"].includes(asset.kind)||
  asset.license==="LICENSED_OWNER"&&asset.consent!==true)fail("ASSET_SOURCE_NOT_APPROVED");
 return Object.freeze({id:asset.id,sha256:asset.sha256.toLowerCase(),kind:asset.kind,license:asset.license});
}
export function createVisualPlan({brief,output="image",compositionId=151,mode="BALANCED",assets=[],
   ownerPersona=null,providerId=null}={}){
 if(typeof brief!=="string"||!brief.trim()||brief.length>2500||/[\u0000-\u0008\u000e-\u001f]/.test(brief))fail("INVALID_BRIEF");
 if(!allowed.has(output)||!Object.hasOwn(profiles,mode))fail("INVALID_OUTPUT_OR_PROFILE");
 const c=COMPOSITION_BY_ID.get(compositionId);if(!c)fail("UNKNOWN_WOW_COMPOSITION");
 if(!Array.isArray(assets)||assets.length>16)fail("ASSET_QUOTA");
 const checked=assets.map(verifyAsset);if(new Set(checked.map(a=>a.id)).size!==checked.length)fail("DUPLICATE_ASSET");
 if(providerId!==null&&!ID.test(providerId))fail("INVALID_PROVIDER");
 if(output==="avatar"&&(ownerPersona===null||ownerPersona.approved!==true||!ID.test(ownerPersona.personaId||"")||
  !HASH.test(ownerPersona.masterSha256||"")))fail("PERSONA_IDENTITY_NOT_APPROVED");
 const palette=c.tone==="ice"?"ice cyan and graphite":c.tone==="amber"?"molten amber and obsidian":
  c.tone==="bronze"?"bronze and midnight graphite":"charcoal, titanium, restrained cinematic light";
 const format=output==="video"?"multi-shot moving cinematic sequence":
  output==="scene3d"?"physical 3D scene with lighting/materials":output==="presentation"?"storyboard-based presentation":
  output==="avatar"?"identity-preserving owner-approved portrait":"photographic cinematic still";
 return Object.freeze({
  schema:"NOX_VISUAL_PLAN_V1",status:"PLANNED_NOT_RENDERED",output,mode,
  providerId,brief:brief.trim(),composition:Object.freeze({
   id:c.id,title:c.title,scene:c.family,directorId:c.directorId,opticalId:c.opticalId,depth:c.depth}),
  palette,style:Object.freeze([...sourceStyles]),format,quality:Object.freeze({...profiles[mode]}),
  resources:Object.freeze(checked),persona:ownerPersona?Object.freeze({
   personaId:ownerPersona.personaId,masterSha256:ownerPersona.masterSha256.toLowerCase()}):null,
  route:"images.generate",authorization:"NATIVE_HOST_REQUIRED"
 });
}
export function verifyVisualPlan(p){
 if(!p||p.schema!=="NOX_VISUAL_PLAN_V1"||p.status!=="PLANNED_NOT_RENDERED"||
  !allowed.has(p.output)||!Object.hasOwn(profiles,p.mode)||!COMPOSITION_BY_ID.has(p.composition?.id)||
  !Array.isArray(p.resources)||p.resources.length>16)return false;
 try{
  if(typeof p.brief!=="string"||!p.brief.trim()||p.brief.length>2500)return false;
  for(const a of p.resources)verifyAsset({...a,approved:true,consent:true});
  if(p.output==="avatar"&&(!ID.test(p.persona?.personaId||"")||!HASH.test(p.persona?.masterSha256||"")))return false;
  return true;
 }catch{return false}
}
export function cinematicPrompt(plan){
 if(!verifyVisualPlan(plan))fail("INVALID_PLAN");
 const known=plan.resources.map(x=>x.id+"#"+x.sha256.slice(0,12)).join(", ");
 return [plan.brief,plan.format,plan.palette,...plan.style,
  "Director shot "+plan.composition.directorId,
  "Optical material "+plan.composition.opticalId,
  "Composition "+plan.composition.id,
  known?"Approved resource IDs: "+known:null].filter(Boolean).join("; ").slice(0,4000);
}
export async function requestViaExistingHost(host,plan,{userConsent=false}={}){
 if(!verifyVisualPlan(plan))fail("INVALID_PLAN");
 if(userConsent!==true||!host||typeof host.authorize!=="function"||
  typeof host.dispatch!=="function"||typeof host.capability!=="function")
  fail("TRUSTED_NATIVE_HOST_REQUIRED");
 if(await host.capability(plan.route)!==true)fail("GENERATION_HOST_NOT_CONNECTED");
 const approved=await host.authorize({route:plan.route,output:plan.output,
  compositionId:plan.composition.id,resources:plan.resources.map(x=>x.sha256)});
 if(approved!==true)fail("HOST_DENIED");
 const response=await host.dispatch(plan.route,{plan,prompt:cinematicPrompt(plan)});
 if(!response||typeof response!=="object"||
  !["QUEUED_NOT_RENDERED","REQUESTED_NOT_RENDERED","RUNNING","COMPLETED_VERIFIED"].includes(response.status))
  fail("UNTRUSTED_HOST_REPLY");
 // "COMPLETED_VERIFIED" is native-only and must be backed by the host's own receipt.
 if(response.status==="COMPLETED_VERIFIED"&&(!HASH.test(response.outputSha256||"")||!ID.test(response.runId||"")))
  fail("OUTPUT_RECEIPT_REQUIRED");
 return Object.freeze({status:response.status,runId:response.runId||null,
  outputSha256:response.outputSha256||null});
}
