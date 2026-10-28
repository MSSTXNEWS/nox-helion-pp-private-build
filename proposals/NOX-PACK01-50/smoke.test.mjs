import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {CATEGORIES,verifyCatalog,normalizeCapabilities,filteredActions,optionsForField,makeRequest} from "./registry.mjs";
import {visualPreset,validateLiveVisualEvent,mountCinematic} from "./cinema50.mjs";
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


test("50 cinematic cards have five original department materials",()=>{
 const presets=catalog.actions.map((item,i)=>visualPreset(item,i));
 assert.equal(presets.length,50);
 assert.equal(new Set(presets.map(x=>x.domain)).size,5);
 assert.equal(new Set(presets.map(x=>x.material)).size,5);
 assert.ok(presets.every((x,i)=>x.domain===catalog.actions[i].category));
});
test("legacy browser-spoofable verification cannot light cinema cards",()=>{
 const ids=new Set(catalog.actions.map(x=>x.routeId));
 const forged={source:"NOX_EVENT_V3_VERIFIED",evidenceVerified:true,
   eventId:"evt-1",runId:"run-1",routeId:catalog.actions[0].routeId,
   state:"streaming",progress:{numerator:1,denominator:4}};
 assert.equal(validateLiveVisualEvent(forged,ids),false);
});

test("fifty visual cards preserve disabled state, real event and cleanup",()=>{
 const oldDoc=globalThis.document,oldWindow=globalThis.window;
 const handlers=new Map();
 let nativeListener=null;let nativeDisconnected=false;
 const style=()=>({setProperty(){},removeProperty(){}});
 const cards=catalog.actions.map((x,i)=>({dataset:{routeId:x.routeId,state:i===0?"CONNECTED":"HOLD"},
   style:style(),removeAttribute(k){delete this.dataset[k.slice(5).replace(/-([a-z])/g,(_,m)=>m.toUpperCase())]}}));
 const root={nodeType:1,dataset:{},
   classList:{contains:n=>n==="nox-pack01"},
   closest(){return null},
   querySelectorAll(){return cards},
   removeAttribute(k){delete this.dataset[k.slice(5).replace(/-([a-z])/g,(_,m)=>m.toUpperCase())]}};
 globalThis.document={hidden:false,
   addEventListener:(n,h)=>handlers.set(n,h),
   removeEventListener:n=>handlers.delete(n)};
 globalThis.window={matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}})};
 try{
   const ui=mountCinematic(root,catalog,{
     subscribeVerifiedNative:(fn)=>{nativeListener=fn;return ()=>{nativeDisconnected=true;nativeListener=null;}}
   });
   ui.decorate();
   assert.equal(cards[0].dataset.cinemaDomain,"chat");
   assert.equal(cards[0].dataset.cinemaLive,undefined);
   const now=Date.now();
   const verified={routeId:catalog.actions[0].routeId,raw:{
      schema:"NOX-INSTALLER-EVENT-v3",evidence_verified:true,
      run_id:"run-1",event_id:"event-1",task_id:"NIP01-01",
      action_id:"chat.start",package_id:"P02",event_type:"task.started",
      event_sequence:1,receipt_sha256:"a".repeat(64),
      timestamp_utc:new Date(now).toISOString()
   }};
   assert.equal(ui.applyNativeEvent(verified),false);
   assert.equal(cards[0].dataset.cinemaLive,undefined);
   assert.equal(nativeListener(verified),true);
   assert.equal(cards[0].dataset.cinemaLive,"running");
   assert.equal(nativeListener(verified),false);
   const old={...verified,raw:{...verified.raw,event_id:"event-older",event_sequence:1}};
   assert.equal(nativeListener(old),false);
   const held={...verified,routeId:catalog.actions[1].routeId,
     raw:{...verified.raw,event_id:"event-2",event_sequence:2}};
   assert.equal(nativeListener(held),true);
   assert.equal(cards[1].dataset.cinemaLive,undefined);
   document.hidden=true;handlers.get("visibilitychange")();
   assert.equal(root.dataset.cinemaPaused,"true");
   assert.equal(ui.setMode("eco"),true);
   assert.equal(root.dataset.cinemaMode,"eco");
   ui.destroy();
   assert.equal(nativeDisconnected,true);
   assert.equal(nativeListener,null);
   assert.equal(root.dataset.cinemaReady,undefined);
   assert.equal(handlers.size,0);
 }finally{globalThis.document=oldDoc;globalThis.window=oldWindow}
});


test("cinema failed native subscription rolls back visual claims and listeners",()=>{
 const oldDoc=globalThis.document,oldWindow=globalThis.window;
 let listeners=0,removed=0;
 const root={nodeType:1,dataset:{},
   classList:{contains:n=>n==="nox-pack01"},
   closest:()=>null,
   querySelectorAll:()=>[],
   removeAttribute(name){delete this.dataset[name.replace(/^data-/,"").replace(/-([a-z])/g,(_,x)=>x.toUpperCase())];}};
 globalThis.document={hidden:false,
   addEventListener(){listeners++;},
   removeEventListener(){removed++;}};
 globalThis.window={matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}})};
 try{
   assert.throws(()=>mountCinematic(root,catalog,{
     subscribeVerifiedNative:()=>{throw Error("Windows native events unavailable");}
   }),/Windows native events unavailable/);
   assert.equal(root.dataset.cinemaReady,undefined);
   assert.equal(root.dataset.cinemaMode,undefined);
   assert.equal(root.dataset.cinemaPaused,undefined);
   assert.equal(listeners,removed);
 }finally{globalThis.document=oldDoc;globalThis.window=oldWindow;}
});
