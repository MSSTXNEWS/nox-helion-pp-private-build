'use strict';
// R42 G2-C P03 source-only regression: a rejected host progress frame MUST NOT
// publish altered model-rights metadata or revoke the user's prior consent.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const src=fs.readFileSync(path.resolve(__dirname,'../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js'),'utf8');
function element(tag){return {tagName:tag||'div',value:'',textContent:'',checked:false,hidden:true,disabled:false,dataset:{},children:[],
  classList:{add(){},toggle(){}},style:{setProperty(){}},append(...x){this.children.push(...x)},
  replaceChildren(...x){this.children=x},addEventListener(){},setAttribute(){},removeAttribute(){}}}
const elements={};
const doc={getElementById(id){return elements[id]||(elements[id]=element())},createElement:element,querySelectorAll(){return []},addEventListener(){}};
const win={chrome:{webview:{postMessage(){},addEventListener(){}}}};
const app=new Function('document','window','URL','setTimeout','clearTimeout',src+';return {state,processMessage};')(doc,win,URL,()=>0,()=>{});
const base={id:'llama3.1',name:'Llama',officialUrl:'https://ollama.com/library/llama3.1',
 artifactVerified:true,exactTag:'llama3.1:8b',immutableRevision:'f'.repeat(64),
 license:'Apache-2.0',licenseEvidenceUrl:'https://example.org/old',artifactBytes:2000000000,
 sha256:'1'.repeat(64),manifestSha256:'2'.repeat(64),requiredVramGiB:4,
 recommendedRamGiB:8,requiredDiskGiB:3,compatibilityReviewed:true};
const job={jobId:'11111111-1111-4111-8111-111111111111',modelTag:base.exactTag,
 state:'Running',status:'Starting',completedBytes:100,totalBytes:200};
function reset(){app.state.models=[{...base}];app.state.activeId=base.id;
 app.state.activeJob={...job};app.state.hostReady=true;
 app.state.capabilities={pull:true,stop:true,retry:true,importGguf:true};
 doc.getElementById('licenseAck').checked=true;}
reset();
app.processMessage({type:'p03.snapshot.v1',models:[{...base,license:'MIT'}],
 activeJob:{...job,completedBytes:901,totalBytes:200},capabilities:app.state.capabilities});
assert.equal(app.state.models[0].license,'Apache-2.0','rejected progress cannot change model rights');
assert.equal(doc.getElementById('licenseAck').checked,true,'rejected progress cannot mutate consent');
assert.equal(app.state.activeJob.completedBytes,100,'invalid progress cannot mutate durable job');
reset();
app.processMessage({type:'p03.snapshot.v1',models:[{...base,license:'MIT'}],
 activeJob:{...job,completedBytes:101,totalBytes:200},capabilities:app.state.capabilities});
assert.equal(app.state.models[0].license,'MIT','valid metadata update still applies');
assert.equal(doc.getElementById('licenseAck').checked,false,'changed license must revoke old consent');
reset();
app.processMessage({type:'p03.snapshot.v1',models:[{...base,license:'MIT'}],
 activeJob:{...job,jobId:'invalid'},capabilities:app.state.capabilities});
assert.equal(app.state.models[0].license,'Apache-2.0','invalid job ID cannot change model rights');
assert.equal(doc.getElementById('licenseAck').checked,true,'invalid job ID cannot revoke consent');
console.log('P03 R42 atomic snapshot regression 3 scenarios PASS (source-only).');
