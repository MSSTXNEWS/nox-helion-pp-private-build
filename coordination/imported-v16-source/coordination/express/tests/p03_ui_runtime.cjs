'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const uiPath=path.resolve(__dirname,'../../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js');
const uiBytes=fs.readFileSync(uiPath);
const src=uiBytes.toString('utf8');
// Producer pin is a release fail-closed boundary: do not bless a drifted WebView.
const ledger=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../P03_PINNED_GIT_BLOBS.json'),'utf8'));
const sourceName='Packages/P03/Source/P03.ModelCenter.Wow/ui.js';
const ownerPin=ledger.pins.filter(p=>p.path===sourceName);
const approvedPin=ledger.approved_overrides.filter(p=>p.path===sourceName);
const currentGitBlob=crypto.createHash('sha1').update('blob '+uiBytes.length+String.fromCharCode(0)).update(uiBytes).digest('hex');
assert.equal(ownerPin.length,1,'one original P03 UI owner pin');
assert.equal(approvedPin.length,1,'one P03 UI approved override');
assert.equal(approvedPin[0].owner,3,'original owner 3 retained');
assert.equal(approvedPin[0].pre_git_blob_sha1,ownerPin[0].git_blob_sha1,'approved preimage cannot drift');
assert.equal(approvedPin[0].post_git_blob_sha1,currentGitBlob,'current UI Git blob must be approved');
assert.equal(approvedPin[0].post_bytes,uiBytes.length,'approved UI byte length must match');

class El{constructor(t='div'){this.tagName=t.toUpperCase();this.children=[];this.handlers={};this.textContent='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.style={setProperty(){}};this.classList={add(){},remove(){},toggle(){}};this.dataset={}}append(...x){this.children.push(...x)}replaceChildren(...x){this.children=x}setAttribute(){}removeAttribute(){}addEventListener(k,fn){this.handlers[k]=fn}focus(){}}
const els=new Map(),timers=new Map(),sent=[];let callback;let tick=0;
const doc={getElementById(k){if(!els.has(k))els.set(k,new El());return els.get(k)},createElement:t=>new El(t),querySelector:s=>s==='.topbar'?doc.getElementById('__fixture_topbar'):null,querySelectorAll:()=>[],addEventListener(){},activeElement:{tagName:'BODY'}};
const win={addEventListener(){},chrome:{webview:{postMessage(x){sent.push(x)},addEventListener(k,fn){callback=fn}}}};
const ctx=vm.createContext({document:doc,window:win,URL,setTimeout:(fn,ms)=>{timers.set(++tick,{fn,ms});return tick},clearTimeout:n=>timers.delete(n),setInterval:(fn,ms)=>{timers.set(++tick,{fn,ms,interval:true});return tick},clearInterval:n=>timers.delete(n),console,Date,Math,Set,Map,JSON,Number});
vm.runInContext(src,ctx,{filename:'P03.ModelCenter.Wow/ui.js'});
// The real UI announces readiness after registering its native listener.
// This is a lifecycle notification, not a user action or install command.
assert.equal(sent.shift()?.type,'p03.ready.v1');
const evalCode=s=>vm.runInContext(s,ctx),post=data=>callback({data,isTrusted:true,source:win.chrome.webview});let total=0;
function ok(value,msg){assert.ok(value,msg);total++}
// Synthetic renderer events cannot create a native owner snapshot or ACK.
const forged={type:'p03.snapshot.v1',models:[{id:'forged',name:'Forged'}],activeJob:null};
callback({isTrusted:false,source:win.chrome.webview,data:forged});
ok(!evalCode('state.hostReady'),'renderer event cannot forge native catalog');
callback({isTrusted:true,source:{},data:forged});
ok(!evalCode('state.hostReady'),'foreign message source cannot impersonate OneHost');
callback({source:win.chrome.webview,data:forged});
ok(!evalCode('state.hostReady'),'missing native trust marker is rejected');
const seed=JSON.parse(JSON.stringify(evalCode('state.models'))),uuid='12345678-1234-1234-1234-123456789abc';
const model={...seed.find(m=>m.id==='qwen3'),artifactVerified:true,exactTag:'qwen3:0.6b',immutableRevision:'a'.repeat(64),license:'synthetic',licenseEvidenceUrl:'https://ollama.com/library/qwen3',artifactBytes:10000,sha256:'b'.repeat(64),manifestSha256:'c'.repeat(64),requiredDiskGiB:1,requiredVramGiB:1,compatibilityReviewed:true};
const job={jobId:uuid,modelId:'qwen3',modelTag:'qwen3:0.6b',state:'Running',completedBytes:10,totalBytes:100};
// Native events must carry a fresh, monotone owner timestamp to mutate the queue.
const eventAt=n=>new Date(Date.now()-12000+n*1000).toISOString();
const snap=(m=model)=>({type:'p03.snapshot.v1',models:seed.map(x=>x.id==='qwen3'?m:x),activeJob:job,hardware:{diskFreeGiB:20,vramFreeGiB:12,ramFreeGiB:32},capabilities:{pull:true,stop:true,retry:true,diagnose:true,importGguf:true}});
post(snap());evalCode('state.activeId="qwen3";render()');els.get('licenseAck').checked=true;els.get('licenseAck').handlers.change();
ok(!els.get('pullBtn').disabled,'verified fixture enables host action');
evalCode("sendAction('pull')");ok(sent.length===1,'one host command only');ok(evalCode('state.pending.has("pull")'),'await ACK');
post({type:'p03.command.ack.v1',action:'pull',commandId:'wrong',accepted:true});ok(evalCode('state.pending.has("pull")'),'wrong ACK denied');
post({type:'p03.command.ack.v1',action:'pull',commandId:sent[0].commandId,accepted:true});ok(!evalCode('state.pending.has("pull")'),'matching ACK accepted');ok(els.get('toast').textContent.includes('receipt'),'ACK not install');
post(snap({...model,immutableRevision:'d'.repeat(64)}));ok(!els.get('licenseAck').checked,'revision change revokes consent');
post({...snap(),models:[model,model]});ok(evalCode('state.models.length')===seed.length,'duplicate catalog rejected');
post(snap());
post({type:'p03.event.v1',event:{jobId:uuid,modelTag:'qwen3:0.6b',phase:'progress',status:'x'.repeat(3000),completedBytes:20,totalBytes:100}});
ok(evalCode('state.activeJob.completedBytes')===10,'oversize event cannot change progress');
// Unstamped/advisory or future events never mutate native queue or show LIVE.
post({type:'p03.event.v1',event:{jobId:uuid,modelTag:'qwen3:0.6b',phase:'progress',status:'unstamped',completedBytes:99,totalBytes:100}});
ok(evalCode('state.activeJob.completedBytes')===10,'unstamped event cannot advance queue');
ok(evalCode('state.events[0].phase')==='advisory','unstamped history remains advisory');
post({type:'p03.event.v1',event:{jobId:uuid,modelTag:'qwen3:0.6b',phase:'progress',status:'future',atUtc:new Date(Date.now()+60000).toISOString(),completedBytes:99,totalBytes:100}});
ok(evalCode('state.activeJob.completedBytes')===10,'future event cannot advance queue');

post({type:'p03.event.v1',event:{jobId:uuid,modelTag:'qwen3:0.6b',phase:'progress',status:'valid',atUtc:eventAt(1),completedBytes:20,totalBytes:100}});
ok(evalCode('state.activeJob.completedBytes')===20,'verified progress rises');
post({type:'p03.event.v1',event:{jobId:uuid,modelTag:'qwen3:0.6b',phase:'progress',status:'regress',atUtc:eventAt(2),completedBytes:10,totalBytes:100}});
ok(evalCode('state.activeJob.completedBytes')===20,'progress never regresses');
post({type:'p03.event.v1',event:{jobId:uuid,modelTag:'qwen3:0.6b',phase:'cancelled',status:'stopped',atUtc:eventAt(3)}});
ok(evalCode('state.activeJob.state')==='Cancelled','terminal cancellation persists');
post({type:'p03.event.v1',event:{jobId:uuid,modelTag:'qwen3:0.6b',phase:'progress',status:'late',atUtc:eventAt(4),completedBytes:100,totalBytes:100}});
ok(evalCode('state.activeJob.state')==='Cancelled','terminal state never revives');
// E03 R05: terminal jobs cannot be revived by older host snapshots.
post({...snap(),activeJob:{...job,state:'Running',completedBytes:0,totalBytes:100}});
ok(evalCode('state.activeJob.state')==='Cancelled','stale snapshot cannot resurrect terminal job');
ok(evalCode('state.activeJob.completedBytes')===20,'stale snapshot cannot erase observed bytes');
const childId='abcdef12-abcd-abcd-abcd-abcdef123456';
post({...snap(),activeJob:{...job,jobId:childId,state:'Queued',completedBytes:null,totalBytes:null}});
ok(evalCode('state.activeJob.jobId')===childId,'retry uses new real job ID');
post({...snap(),activeJob:{...job,jobId:childId,state:'Running',completedBytes:50,totalBytes:100}});
post({...snap(),activeJob:{...job,jobId:childId,state:'Queued',completedBytes:10,totalBytes:100}});
ok(evalCode('state.activeJob.state')==='Running','old queued snapshot cannot revert Running');
ok(evalCode('state.activeJob.completedBytes')===50,'snapshot counters cannot regress');
post(snap({...model,artifactVerified:false,exactTag:'unreviewed:tag',license:'unverified-license'}));
evalCode('state.activeId="qwen3";render()');
const dna=els.get('dnaList').children.map(x=>x.textContent);
ok(!dna.includes('unverified-license')&&!dna.includes('unreviewed:tag'),'DNA hides unreviewed values');
ok(dna.includes('REVIEW_REQUIRED'),'DNA keeps honest review indicator');
// W06 R96: transient null active-job snapshot must not revoke native STOP.
const stopR96='abcdef12-abcd-abcd-abcd-abcdef123456';
post({...snap(),activeJob:{...job,jobId:stopR96,state:'Running'}});
ok(!els.get('stopBtn').disabled,'Running queue exposes STOP');
post({...snap(),activeJob:null});
ok(evalCode('state.activeJob?.jobId')===stopR96&&!els.get('stopBtn').disabled,
   'null owner snapshot cannot erase unconfirmed STOP target');
const sentR96=sent.length;
evalCode("sendAction('stop')");
ok(sent.length===sentR96+1&&sent[sentR96].type==='p03.command.v1'&&
   sent[sentR96].action==='stop'&&sent[sentR96].jobId===stopR96,
   'STOP issued to actual durable jobId after null snapshot');
post({...snap(),activeJob:{...job,jobId:stopR96,state:'Cancelled'}});
ok(els.get('stopBtn').disabled,'confirmed terminal Cancelled disables STOP');
console.log('E03_EXPRESS_R05_RUNTIME_PASS '+total+' scenarios, no real weights or Windows EXE');
