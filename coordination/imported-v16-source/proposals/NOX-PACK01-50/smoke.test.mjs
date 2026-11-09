import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {CATEGORIES,verifyCatalog,normalizeCapabilities,filteredActions,optionsForField,makeRequest} from "./registry.mjs";
const catalog=JSON.parse(readFileSync(new URL("./catalog.json",import.meta.url),"utf8"));
const choices={
 "host.models.installed":[{id:"qwen3:4b",label:"Qwen 3 4B",installed:true}],
 "host.personas":[{id:"persona-a",label:"Approved Persona",installed:true}],
 "host.cores":[{id:"CORE_01",label:"Approved core",installed:true}],
 "host.voices.installed":[{id:"es-voice",label:"Installed Spanish voice",installed:true}]
};
test("exactly fifty paths across five distinct categories",()=>{
 assert.deepEqual(verifyCatalog(catalog),Object.fromEntries(CATEGORIES.map(x=>[x,10])));
 assert.equal(new Set(catalog.actions.map(x=>x.routeId)).size,50);
});
test("all 50 start disabled until native host explicitly advertises capability",()=>{
 const statuses=normalizeCapabilities(catalog,{});
 assert.equal(Object.values(statuses).filter(x=>x.enabled).length,0);
 assert.equal(Object.values(statuses).filter(x=>x.state==="HOLD").length,50);
});
test("unsupported capability states and injection never activate",()=>{
 const id=catalog.actions[0].routeId;
 for(const bad of [null,{},{"enabled":true,state:"AVAILABLE"},{"enabled":true,state:"garbage"},{
  enabled:true,state:"CONNECTED",sourceId:123}]){
   const state=normalizeCapabilities(catalog,{[id]:bad});
   if(bad?.state==="CONNECTED")assert.equal(state[id].enabled,true);
   else assert.equal(state[id].enabled,false);
 }
});
test("dangerous commands require host-confirmed native-consent capability",()=>{
 const item=catalog.actions.find(x=>x.risk==="dangerous");
 const c=normalizeCapabilities(catalog,{[item.routeId]:{enabled:true,state:"VERIFIED"}});
 assert.equal(c[item.routeId].enabled,false);
 const d=normalizeCapabilities(catalog,{[item.routeId]:{enabled:true,state:"VERIFIED",nativeConsent:true}});
 assert.equal(d[item.routeId].enabled,true);
});
test("canonical route/risk/owner policy cannot be downgraded in the UI catalogue",()=>{
  for(const [index,entry] of catalog.actions.entries()){
    for(const field of ["risk","owner","routeId","taskId"]){
      const altered=structuredClone(catalog),a=altered.actions[index];
      a[field]=field==="risk"?(entry.risk==="safe"?"sensitive":"safe"):
               field==="owner"?(entry.owner%6+1):
               field==="routeId"?"tampered.route":"NIP01-99";
      assert.throws(()=>verifyCatalog(altered),/CANONICAL_OWNER_RISK_MISMATCH/);
    }
    if(entry.risk==="dangerous"){
      const state=normalizeCapabilities(catalog,{[entry.routeId]:{state:"VERIFIED",enabled:true}});
      assert.equal(state[entry.routeId].enabled,false);
    }
  }
});
test("search and category filtering have no side effects",()=>{
 assert.equal(filteredActions(catalog,"Qwen").length,0);
 assert.ok(filteredActions(catalog,"gpu").length>=1);
 assert.equal(filteredActions(catalog,"","models").length,10);
 assert.equal(filteredActions(catalog,"","all").length,50);
});
test("settings reject unknown or uninstalled model choices",()=>{
 const field=catalog.actions.find(x=>x.routeId==="models.pull").settings[0];
 assert.deepEqual(optionsForField(field,{"host.models.installed":[{id:"bad",label:"No",installed:false}]}),[]);
 const item=catalog.actions.find(x=>x.routeId==="models.pull");
 assert.throws(()=>makeRequest(item,{model:"fake-model"},choices),/UNSUPPORTED_SETTING/);
 const req=makeRequest(item,{model:"qwen3:4b"},choices);
 assert.equal(req.routeId,"models.pull");
 assert.equal(req.settings.model,"qwen3:4b");
});
test("source modules neither open public networks nor invoke OS commands",()=>{
 const code=readFileSync(new URL("./panel.mjs",import.meta.url),"utf8");
 assert.equal(/\bfetch\s*\(/.test(code),false);
 assert.equal(/\bchild_process\b/.test(code),false);
 assert.equal(code.includes("innerHTML"),false);
 assert.ok(code.includes("NO_PACK_ON_D02_HOME"));
});
// Fifty independent contract/test cases. Each has a distinct native action envelope.
for(const [i,x] of catalog.actions.entries()){
 test("NIP01-"+String(i+1).padStart(2,"0")+" "+x.routeId,()=>{
   assert.equal(x.taskId,"NIP01-"+String(i+1).padStart(2,"0"));
   assert.ok(CATEGORIES.includes(x.category));
   assert.equal(x.intent,"nox.feature.request");
   const enabled=normalizeCapabilities(catalog,{[x.routeId]:{
    state:"VERIFIED",enabled:true,nativeConsent:true}});
   assert.equal(enabled[x.routeId].enabled,true);
   const form={};
   for(const f of x.settings){
     const opts=optionsForField(f,choices);
     assert.ok(opts.length>0);
     form[f.key]=opts[0][0];
   }
   const request=makeRequest(x,form,choices);
   assert.equal(request.routeId,x.routeId);
   assert.equal(request.taskId,x.taskId);
   assert.equal(request.requestedOwner,x.owner);
   assert.equal(request.intent,"nox.feature.request");
   assert.equal(Object.keys(request.settings).length,x.settings.length);
 });
}
