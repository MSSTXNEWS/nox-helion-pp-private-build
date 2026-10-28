import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const source=fs.readFileSync(new URL("./media-weights.js",import.meta.url),"utf8");
const meta=JSON.parse(fs.readFileSync(new URL("./media-weights-candidates.json",import.meta.url),"utf8"));
class Node {
 constructor(tag,doc){this.tag=tag;this.doc=doc;this.nodeType=1;this.dataset={};this.children=[];this.disabled=false;this.checked=false;this.isConnected=true;this.listeners={};this.attributes={};this.value="";this.textContent="";this.hidden=false;this.className="";this.classList={add:()=>{},remove:()=>{}};}
 append(...nodes){this.children.push(...nodes)}
 replaceChildren(...nodes){this.children=[...nodes]}
 setAttribute(name,val){this.attributes[name]=String(val)}
 getAttribute(name){return this.attributes[name]}
 addEventListener(ev,fn){this.listeners[ev]=fn}
 removeEventListener(ev){delete this.listeners[ev]}
 closest(){return null}
 click(){this.listeners.click?.()}
 emit(ev){this.listeners[ev]?.()}
}
function setup(){
 const callbacks={},sent=[];
 const doc={listeners:{},createElement(tag){return new Node(tag,doc)},createTextNode(value){const n=new Node("#text",doc);n.textContent=value;return n},addEventListener(name,fn){this.listeners[name]=fn},getElementById(id){return id==="mediaWeightsMount"?root:null}};
 const root=doc.createElement("section");
 const win={chrome:{webview:{addEventListener(name,fn){callbacks[name]=fn},postMessage(data){sent.push(data)}}}};
 vm.runInNewContext(source,{window:win,document:doc,console,Math,Date});
 doc.listeners.DOMContentLoaded();
 const find=(node,pred)=>{const todo=[node];while(todo.length){const n=todo.shift();if(pred(n))return n;todo.push(...n.children)}return null};
 const findAll=(node,pred)=>{const result=[],todo=[node];while(todo.length){const n=todo.shift();if(pred(n))result.push(n);todo.push(...n.children)}return result};
 const host=data=>callbacks.message({data});
 return {root,win,doc,sent,host,find,findAll};
}
test("20+ categories with exact distinct buttons for each source variant",()=>{
 const u=setup(), lib=u.win.NoxMediaWeights;
 assert.equal(lib.models.length,meta.choices.length);
 assert.equal(lib.categories.length,meta.categories.length);
 assert.ok(lib.models.length>=100);
 assert.equal(new Set(lib.models.map(x=>x.variantId)).size,lib.models.length);
 assert.ok(lib.categories.includes("persona")&&lib.categories.includes("emotions")&&lib.categories.includes("politics"));
 assert.ok(lib.categories.includes("orientation")&&lib.categories.includes("memory")&&lib.categories.includes("thread"));
 assert.equal(u.findAll(u.root,n=>n.dataset.category).length,20);
 for(const tab of lib.categories){
  const btn=u.find(u.root,n=>n.dataset.category===tab);
  assert.ok(btn,tab);btn.click();
  const number=lib.models.filter(x=>x.category===tab).length;
  assert.equal(u.findAll(u.root,n=>n.dataset.variant).length,number+(number),tab);
 }
});
test("all 109 variants are disabled until trusted host publishes an approved source",()=>{
 const u=setup(),lib=u.win.NoxMediaWeights;
 for(const tab of lib.categories){
  u.find(u.root,n=>n.dataset.category===tab).click();
  const downloads=u.findAll(u.root,n=>n.dataset.variant&&n.textContent.startsWith("Скачать"));
  assert.ok(downloads.length>0,tab);
  assert.ok(downloads.every(x=>x.disabled));
 }
 assert.deepEqual(u.sent,[]);
});
test("each weight button sends distinct modelId and variantId, not a generic download",()=>{
 const u=setup(),lib=u.win.NoxMediaWeights,options=lib.models.filter(x=>x.category==="photo");
 u.find(u.root,n=>n.dataset.category==="photo").click();
 const models=options.slice(0,2);
 u.host({type:"p03.media.snapshot.v1",capabilities:{download:true,cancel:true,prepare:true},
  models:models.map(o=>({variantId:o.variantId,modelId:o.modelId,installable:true,licenseVerified:true,
    immutableRevision:"a".repeat(40),manifestSha256:"b".repeat(64),expectedBytes:40000000})),jobs:[]});
 const ack=u.find(u.root,n=>n.tag==="input"&&n.type==="checkbox");
 assert.ok(ack);ack.checked=true;ack.emit("change");
 for(const o of models){
  const button=u.find(u.root,n=>n.dataset.variant===o.variantId&&n.textContent.startsWith("Скачать"));
  assert.ok(button&&!button.disabled,o.variantId);button.click();
 }
 assert.equal(u.sent.length,2);
 assert.equal(u.sent[0].action,"download");
 assert.notEqual(u.sent[0].variantId,u.sent[1].variantId);
 assert.equal(u.sent[0].modelId,models[0].modelId);
 assert.equal(u.sent[1].modelId,models[1].modelId);
 assert.equal(u.sent[0].licenseAcknowledged,true);
});
test("independent progress/abort per variant, never false completion",()=>{
 const u=setup(),chosen=u.win.NoxMediaWeights.models.find(x=>x.category==="video");
 u.find(u.root,n=>n.dataset.category==="video").click();
 u.host({type:"p03.media.snapshot.v1",capabilities:{download:true,cancel:true,prepare:true},models:[],
  jobs:[{variantId:chosen.variantId,modelId:chosen.modelId,state:"Downloading",jobId:"11111111-2222-3333-4444-555555555555",
   completedBytes:1024,totalBytes:1000000}]});
 const stop=u.find(u.root,n=>n.dataset.variant===chosen.variantId&&n.textContent==="Отменить");
 assert.ok(stop&&!stop.disabled);stop.click();
 assert.equal(u.sent.at(-1).action,"cancel");assert.equal(u.sent.at(-1).variantId,chosen.variantId);
 const other=u.win.NoxMediaWeights.models.filter(x=>x.category==="video").find(x=>x.variantId!==chosen.variantId);
 assert.ok(u.find(u.root,n=>n.dataset.variant===other.variantId&&n.textContent.startsWith("Скачать")).disabled);
});
test("independent mounts reusing ONE host and refusing D02 HOME",()=>{
 const u=setup(),sub=u.doc.createElement("section"),api=u.win.NoxMediaWeights.mount(sub,{category:"memory"});
 assert.equal(api.current(),"memory");
 assert.equal(api.count(),meta.choices.filter(x=>x.category==="memory").length);
 api.select("coding");assert.equal(api.current(),"coding");
 assert.throws(()=>u.win.NoxMediaWeights.mount(sub),/ALREADY_MOUNTED/);
 api.destroy();
 const blocked=u.doc.createElement("main");blocked.closest=()=>({nodeType:1});
 assert.throws(()=>u.win.NoxMediaWeights.mount(blocked,{category:"3d"}),/D02_HOME_LOCK/);
});
