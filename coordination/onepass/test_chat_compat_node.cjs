// Offline source acceptance for owner-stage JSON/SSE -> existing native NDJSON.
// Never calls Vast or mutates S03.
'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/nox-legacy-chat-bridge-v293.js','utf8');
const D='a'.repeat(32),ANS='{"tempo":72,"rootMidi":30,"motif":[0,2,4],"density":0.4}';
function fixture(nativeOwner=true){
 const state={requests:[],mode:'good',brokenHistory:false,prompt:'',createFail:false};
 const mocked=async(url,opts={})=>{
   const name=String(url).split('?')[0];
   state.requests.push(name);
   if(name==='/api/ui/memory/dialogs/create')return new Response(JSON.stringify(
     state.createFail?{error:'NO_OWNER'}:{dialog_id:D}),{status:state.createFail?401:200});
   if(name==='/api/nox/chat/stream'){
     const request=JSON.parse(opts.body);state.prompt=request.message;
     assert.equal(request.dialog_id,D);
     const records=[{type:'preparing'},{type:'start'},
       {type:'delta',text:ANS.slice(0,10)},{type:'delta',text:ANS.slice(10)}];
     if(state.mode==='good')records.push({type:'done',saved:true,s03_integrated:true,dialog_id:D,exchange_id:'test_s03_1234567'});
     if(state.mode==='bad_done')records.push({type:'done',saved:false,s03_integrated:false,dialog_id:D,exchange_id:'test_s03_1234567'});
     if(state.mode==='error')records.push({type:'error',error:'HOLD_ORIGINAL_S03'});
     return new Response(records.map(x=>JSON.stringify(x)).join('\n')+'\n',{status:200,headers:{'Content-Type':'application/x-ndjson'}});
   }
   if(name==='/api/ui/memory/dialogs/history'){
     const msgs=[{role:'user',content:state.prompt},
       {role:'assistant',content:state.brokenHistory?'WRONG':ANS}];
     return new Response(JSON.stringify({status:'READY',dialog_id:D,messages:msgs}),{status:200});
   }
   return new Response('LEGACY_NOT_INSTALLED',{status:404});
 };
 const window={NOX_NATIVE_OWNER:nativeOwner,fetch:mocked};
 const location={href:'https://owner.nox.test/nox-web-v29/cinema.html',
   origin:'https://owner.nox.test',pathname:'/nox-web-v29/cinema.html'};
 window.location=location;
 const context={window,location,URL,Request,Response,ReadableStream,TextEncoder,TextDecoder,
   console,Promise,AbortController,AbortSignal};
 vm.runInNewContext(source,context,{filename:'nox-legacy-chat-bridge-v293.js'});
 return {state,window};
}
async function req(f,extra={},url='/api/nox/chat'){
 const r=await f.window.fetch(url,{method:'POST',body:JSON.stringify({message:'NOX score',...extra})});
 return {status:r.status,value:await r.json()};
}
(async()=>{
 let n=0;
 const f=fixture();
 const first=await req(f);
 assert.equal(first.status,200);assert.equal(first.value.answer,ANS);
 assert.equal(first.value.history_persisted,true);assert.equal(first.value.exchange_id,'test_s03_1234567');
 assert.deepEqual(f.state.requests.slice(0,3),['/api/ui/memory/dialogs/create','/api/nox/chat/stream','/api/ui/memory/dialogs/history']);
 n++;
 const s=fixture();
 const r=await s.window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({message:'NOX score',request_id:'one'})});
 assert.equal(r.status,200);
 const ev=(await r.text()).split('\n').filter(x=>x.startsWith('data: ')).map(x=>JSON.parse(x.slice(6)));
 assert.deepEqual(ev.map(x=>x.type),['meta','token','token','done']);assert.equal(ev.at(-1).saved,true);
 n++;
 for(const [mode,pattern] of [['bad_done','HOLD_S03_COMMIT_RECEIPT'],['incomplete','HOLD_INCOMPLETE_NATIVE_RESPONSE'],['error','HOLD_ORIGINAL_S03']]){
   const z=fixture();z.state.mode=mode;const out=await req(z);
   assert.equal(out.status,503);assert.equal(out.value.history_persisted,false);assert.match(out.value.error,new RegExp(pattern));n++;
 }
 const broken=fixture();broken.state.brokenHistory=true;
 let out=await req(broken);assert.equal(out.status,503);assert.match(out.value.error,/HOLD_DIALOG_HISTORY_READBACK/);n++;
 const denied=fixture();denied.state.createFail=true;
 out=await req(denied);assert.equal(out.status,503);assert.equal(denied.state.requests.includes('/api/nox/chat/stream'),false);n++;
 const noOwner=fixture(false);
 const raw=await noOwner.window.fetch('/api/nox/chat',{method:'POST',body:'{}'});
 assert.equal(raw.status,404);assert.equal(noOwner.state.requests[0],'/api/nox/chat');n++;
 const other=fixture();
 const untouched=await other.window.fetch('https://other.example/api/nox/chat',{method:'POST',body:'{}'});
 assert.equal(untouched.status,404);assert.equal(other.state.requests[0],'https://other.example/api/nox/chat');n++;
 const prior=fixture();
 const rprior=await prior.window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({message:'NOX score',dialog_id:D})});
 assert.equal(rprior.status,200);assert.match(await rprior.text(),/history_persisted/);
 assert.equal(prior.state.requests.includes('/api/ui/memory/dialogs/create'),false);n++;
 console.log('NOX_NATIVE_OWNER_LEGACY_COMPAT_OFFLINE_TESTS=PASS '+n+'/'+n);
})().catch(e=>{console.error('NOX_NATIVE_OWNER_LEGACY_COMPAT_OFFLINE_TESTS=FAIL',e);process.exit(2)});
