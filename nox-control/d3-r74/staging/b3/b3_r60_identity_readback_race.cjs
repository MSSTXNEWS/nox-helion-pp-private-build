'use strict';
// R60: local same-dialog identity admission only; no shared writes or network.
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {createHash}=require('node:crypto');
const vm=require('node:vm');
const digest=s=>createHash('sha256').update(s).digest('hex');
const src=execFileSync(process.execPath,[__dirname+'/b3_r57_phase_transition_port.cjs','--emit'],{encoding:'utf8'});
assert.equal(digest(src),'779f308a18cb652fe7dbe5b555750068ee121fbfe4ec4ea6a8d0a9e9f58581a0');
function once(s,a,b){assert.equal(s.split(a).length,2,a);return s.replace(a,b);}
function transform(s){
 s=once(s,'const dialogModelPins=new Map();','const dialogModelPins=new Map(),pendingIdentity=new Set();\nfunction holdIdentity(id){if(pendingIdentity.has(id))throw Error("HOLD_DIALOG_IDENTITY_IN_FLIGHT");pendingIdentity.add(id);return()=>pendingIdentity.delete(id);}');
 s=once(s,'let closed=false,finished=false,','let releaseIdentity,closed=false,finished=false,');
 s=once(s,'const id=await dialogId(data,nativeSignal);\nmodelPinAdmission(id);','const id=await dialogId(data,nativeSignal);\nreleaseIdentity=holdIdentity(id);\nmodelPinAdmission(id);');
 s=once(s,'const phase={meta:', 'const phase=payload.error==="HOLD_DIALOG_IDENTITY_IN_FLIGHT"?null:{meta:');
 s=once(s,'finished=true;\nsignal?.removeEventListener','finished=true;releaseIdentity?.();\nsignal?.removeEventListener');
 s=once(s,'async function jsonChat(data,signal) {\ntry{','async function jsonChat(data,signal) {\nlet releaseIdentity;try{');
 s=once(s,'const id=await dialogId(data,signal);\nmodelPinAdmission(id);','const id=await dialogId(data,signal);\nreleaseIdentity=holdIdentity(id);\nmodelPinAdmission(id);');
 s=once(s,"}catch(e){return errorResponse(String(e.message||'HOLD_NATIVE_JSON').slice(0,150));}\n}","}catch(e){return errorResponse(String(e.message||'HOLD_NATIVE_JSON').slice(0,150));}finally{releaseIdentity?.();}\n}");
 return s;
}
const candidate=transform(src);
new Function(candidate);
assert(Buffer.byteLength(candidate)<=25454);
if(process.argv.includes('--emit')){process.stdout.write(candidate);return;}
const id='a'.repeat(32),other='b'.repeat(32);
const model='GLM-5.3-Flash',drift='Qwen-drift',answer='Привет ¿sí? 👩‍💻';
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
function fixture(source){
 const entered=deferred(),release=deferred(),rows=new Map(),phases=[];
 let posts=0,reads=0,stops=0,label=model,first=true,fail=false;
 const loc=new URL('https://fixture.invalid/nox-web-v29/pc/resonance.html');
 const json=(x,status=200)=>new Response(JSON.stringify(x),{status});
 const window={NOX_NATIVE_OWNER:true,dispatchEvent:e=>{if(e.type==='nox:native-phase')phases.push(e.detail.phase);},fetch:async(path,init)=>{
   const url=new URL(String(path),loc);
   if(url.pathname==='/api/nox/stop'){stops++;return json({status:'STOP_REQUESTED',stream_cancellation_signalled:true});}
   if(url.pathname==='/api/ui/memory/dialogs/create')return json({dialog_id:id});
   if(url.pathname==='/api/ui/memory/dialogs/history'){
     reads++;const d=url.searchParams.get('dialog_id');
     if(first&&d===id){first=false;entered.resolve();await release.promise;if(fail)return json({status:'READY',dialog_id:d,messages:[]});}
     return json({status:'READY',dialog_id:d,messages:rows.get(d)||[]});
   }
   assert.equal(url.pathname,'/api/nox/chat/stream');
   const data=JSON.parse(init.body),d=data.dialog_id,ex='fixture-exchange-'+(++posts);
   const frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM',dialog_id:d},{type:'start',model:label,dialog_id:d},{type:'delta',text:answer,dialog_id:d},{type:'done',saved:true,s03_integrated:true,dialog_id:d,exchange_id:ex}];
   rows.set(d,[...(rows.get(d)||[]),{role:'user',content:data.message,exchange_id:ex},{role:'assistant',content:answer,exchange_id:ex}]);
   return new Response(frames.map(x=>JSON.stringify(x)).join('\n')+'\n');
 }};
 vm.runInNewContext(source,{window,location:loc,URL,Request,Response,ReadableStream,TextEncoder,TextDecoder,AbortController,Intl,performance,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},setTimeout,clearTimeout,requestAnimationFrame:f=>setTimeout(f,0)},{timeout:1000});
 async function turn(d=id,sse=true){
   const payload=sse?{dialog_id:d,request_id:'fixture',message:'Вопрос'}:{message:'Вопрос'};
   const r=await window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify(payload)});
   if(!sse){const b=await r.json();return {answer:b.answer||'',done:r.status===200,error:b.error};}
   const e=(await r.text()).split('\n\n').filter(Boolean).map(x=>JSON.parse(x.slice(6)));
   return {answer:e.filter(x=>x.type==='token').map(x=>x.t).join(''),done:e.some(x=>x.type==='done'),error:e.find(x=>x.type==='error')?.error};
 }
 return {turn,entered:entered.promise,release:release.resolve,set:l=>{label=l;},fail:()=>{fail=true;},counts:()=>({posts,reads,stops}),phases};
}
async function run(){
 const old=fixture(src),a=old.turn();await old.entered;old.set(drift);
 const b=await old.turn();assert.equal(b.answer,answer);assert.equal(b.done,true);
 old.release();const first=await a;assert.equal(first.done,false);assert.equal(old.counts().posts,2);
 let cases=0;
 for(const firstSse of [true,false]){
   const f=fixture(candidate),p=f.turn(id,firstSse);await f.entered;f.set(drift);
   for(const sse of [true,false]){
     const before=f.counts(),phases=f.phases.slice(),r=await f.turn(id,sse);
     assert.equal(r.answer,'');assert.equal(r.done,false);assert.equal(r.error,'HOLD_DIALOG_IDENTITY_IN_FLIGHT');
     assert.deepEqual(f.counts(),before);assert.deepEqual(f.phases,phases);cases++;
   }
   const independent=await f.turn(other);assert.equal(independent.done,true);assert.equal(independent.answer,answer);cases++;
   f.release();assert.equal((await p).done,true);
   const later=await f.turn();assert.equal(later.answer,'');assert.equal(later.error,'HOLD_DIALOG_MODEL_DRIFT');cases++;
 }
 const f=fixture(candidate),p=f.turn();await f.entered;f.fail();f.release();assert.equal((await p).done,false);
 f.set(drift);assert.equal((await f.turn()).done,true);cases++;
 console.log(JSON.stringify({task:'5A05-B3-R58-SAME-DIALOG-IDENTITY-READBACK-RACE-20261124-R60',old_race_reproduced:true,cases,bytes:Buffer.byteLength(candidate),sha256:digest(candidate),native_accepted:false}));
}
run().catch(e=>{console.error(e);process.exitCode=1;});
