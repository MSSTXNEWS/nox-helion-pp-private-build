'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{runInNewContext}=require('node:vm');
const bundle=path.resolve(process.argv[2]),client=path.resolve(process.argv[3]),out=path.resolve(process.argv[4]);
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'nox-a1-a6-source-')),source=fs.readFileSync(client,'utf8');
let child,origin,port,stderr='';const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,why){for(let i=0;i<200;i++){const value=await fn();if(value)return value;await sleep(25);}throw Error('Deadline '+why);}
async function control(route,body){const r=await fetch(origin+'/__source_fixture/'+route,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});assert.equal(r.status,200);return r.json();}
async function start(){
 child=spawn(process.env.NOX_TEST_PYTHON||'python3',[path.join(__dirname,'asgi_fixture.py'),'--bundle',bundle,'--state',temp,'--port',String(port)],{stdio:['ignore','ignore','pipe']});child.stderr.on('data',s=>stderr+=s);
 await until(async()=>{if(child.exitCode!==null)throw Error(stderr);try{return await control('status');}catch{return false;}},'ASGI startup');
}
async function kill(){if(!child||child.exitCode!==null)return;const exited=once(child,'exit');child.kill('SIGKILL');await exited;}
function env(sid,dialog){
 const window=new EventTarget(),calls=[];window.NOX_NATIVE_OWNER=true;const store=new Map();window.sessionStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)};
 window.fetch=(input,init={})=>{const url=new URL(input,origin);calls.push({method:init.method||'GET',path:url.pathname,search:url.search,body:init.body});const headers=new Headers(init.headers);headers.set('cookie','owner=fixture; sid='+sid);return fetch(url,{...init,headers});};
 const pathname='/nox-web-v29/pc/resonance.html';runInNewContext(source,{window,location:{origin,pathname,href:origin+pathname},URL,Request,Response,AbortController,ReadableStream,TextDecoder,TextEncoder,performance,CustomEvent});
 return {api:window.NOX_OWNER_RESONANCE_STREAM,calls,open:(id,message)=>window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({request_id:id,dialog_id:dialog,message})}),snapshot:async id=>{const r=await window.fetch('/api/nox/chat/requests/'+id);return r.status===200?r.json():null;}};
}
const decode=async r=>(await r.text()).trim().split('\n\n').map(s=>JSON.parse(s.slice(6)));
(async()=>{
 const server=net.createServer();server.listen(0,'127.0.0.1');await once(server,'listening');port=server.address().port;await new Promise(r=>server.close(r));origin='http://127.0.0.1:'+port;
 const checks=[];await start();
 // Real transport disconnect; producer remains live until fixture releases it.
 const a=env('a','a'.repeat(32)),rid='cross-reconnect-001',question='HOLD:reconnect';let response=await a.open(rid,question);
 await until(async()=>{const s=await a.snapshot(rid);return s?.answer?s:null;},'first delta');await response.body.cancel('source transport break');
 const before=(await control('status')).invocations.length,callsBefore=a.calls.length;
 const resumed=await a.api.resume(rid);await control('release',{question});const events=await decode(resumed);
 assert.equal(events[0].replace_answer,true);assert.equal(events.at(-1).type,'done');assert.equal(events.filter(x=>x.type==='token').map(x=>x.t).join(''),'Привет 🌌 — '+question);
 assert.ok(a.calls.slice(callsBefore).every(c=>c.method==='GET'));assert.equal((await control('status')).invocations.length,before);
 const snapshot=await a.snapshot(rid),state=await control('status'),pair=state.messages.filter(m=>m.exchange_id===snapshot.exchange_id);
 assert.deepEqual(pair.map(m=>m.role),['user','assistant']);assert.equal(pair[1].content,snapshot.answer);assert.equal(events.at(-1).s03_record_id,snapshot.s03_record_id);assert.equal(events.at(-1).history_persisted,true);
 checks.push('actual transport reconnect uses GET only, one inference, exact Unicode and atomic S03 pair');
 // Two real producers; scoped STOP cannot stop the other request.
 const b=env('b','b'.repeat(32)),stopId='cross-stop-001',otherId='cross-other-001';
 const stoppedResponse=await a.open(stopId,'HOLD:stop'),otherResponse=await b.open(otherId,'HOLD:other');
 await until(async()=>{const x=await a.snapshot(stopId),y=await b.snapshot(otherId);return x?.answer&&y?.answer;},'two producers');
 assert.equal(a.api.stop(stopId),true);const stopEvents=await decode(stoppedResponse);assert.equal(stopEvents.at(-1).error,'STREAM_STOP_REQUESTED');
 await until(async()=>{const s=await a.snapshot(stopId);return s?.terminal?s:null;},'scoped STOP');
 assert.equal((await a.snapshot(stopId)).saved,false);assert.equal((await b.snapshot(otherId)).terminal,false);
 await until(()=>a.api.inspect(stopId)?.stop_delivery==='acknowledged','STOP receipt');assert.equal(a.api.inspect(stopId).native_execution_verified,false);
 assert.deepEqual(JSON.parse(a.calls.find(c=>c.path==='/api/nox/stop').body),{request_id:stopId});
 await control('release',{question:'HOLD:other'});assert.equal((await decode(otherResponse)).at(-1).type,'done');checks.push('request-scoped STOP acknowledgement leaves other producer and server alive; no GPU-halt claim');
 // Kill this isolated ASGI process, restart against the same real SQLite DB.
 const restartId='cross-restart-001',c=env('c','c'.repeat(32));response=await c.open(restartId,'HOLD:restart');
 await until(async()=>{const s=await c.snapshot(restartId);return s?.answer?s:null;},'pre-restart delta');await response.body.cancel('source process restart');
 const previous=await control('status');await kill();await start();const restarted=await control('status');assert.notEqual(restarted.pid,previous.pid);
 const n=c.calls.length,result=await decode(await c.api.resume(restartId));assert.equal(result.at(-1).error,'HOLD_NATIVE_STREAM_INTERRUPTED_RESTART');assert.ok(!result.some(x=>x.type==='done'));
 assert.ok(c.calls.slice(n).every(x=>x.method==='GET'));assert.equal((await control('status')).invocations.length,previous.invocations.length);
 const interrupted=await c.snapshot(restartId);assert.equal(interrupted.state,'interrupted');assert.equal(interrupted.saved,false);checks.push('actual ASGI process restart marks orphan interrupted; GET recovery never repeats inference');
 const report={scope:'SOURCE_CROSS_CONTRACT_ACTUAL_ASGI_SQLITE_SYNTHETIC_MODEL',passed:checks.length,checks,backend_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(bundle,'native_v29_full_bridge.py'))).digest('hex'),ledger_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(bundle,'owner_chat_request_ledger.py'))).digest('hex'),client_sha256:require('node:crypto').createHash('sha256').update(source).digest('hex'),native_accepted:false,onehost_mutated:false,synthetic_model_invocations:(await control('status')).invocations.length};
 fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);console.error(stderr);process.exitCode=1;}).finally(async()=>{await kill();fs.rmSync(temp,{recursive:true,force:true});});
