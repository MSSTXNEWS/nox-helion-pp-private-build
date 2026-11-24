// R54: actual pinned B3 emitter -> B4 passive stream consumer. Fixture only.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import {performance} from 'node:perf_hooks';
import {measureSseResponse} from './b4_sse_latency_probe.mjs';
import {bindExistingTurnPair} from './b4_existing_turn_pair.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
const root=process.argv[2];
assert(root,'path to pinned B3 checkout required');
const candidate=execFileSync(process.execPath,[root+'/coordination/onepass/b3_r57_phase_transition_port.cjs','--emit'],{encoding:'utf8',maxBuffer:1024*1024});
assert.equal(sha(candidate),'779f308a18cb652fe7dbe5b555750068ee121fbfe4ec4ea6a8d0a9e9f58581a0');
const id='a'.repeat(32),model='GLM-5.3-Flash', prior='fixture-exchange-1';
const answer='Привет, ¿qué tal? 👩‍💻';
const rows=[{role:'user',content:'prior question',exchange_id:prior},{role:'assistant',content:'prior answer',exchange_id:prior}];
const priorSnapshot=JSON.stringify(rows);
let posts=1,browserPosts=1,stops=0; const phases=[];
const loc=new URL('http://fixture.invalid/nox-web-v29/pc/resonance.html');
const json=(x,status=200)=>new Response(JSON.stringify(x),{status});
const window={NOX_NATIVE_OWNER:true,dispatchEvent:e=>{if(e.type==='nox:native-phase')phases.push(e.detail.phase);},fetch:async(path,init)=>{
 const url=new URL(String(path),loc);
 if(url.pathname==='/api/nox/stop'){stops++;return json({status:'STOP_REQUESTED',stream_cancellation_signalled:true});}
 if(url.pathname==='/api/ui/memory/dialogs/history'){
   assert.equal(url.searchParams.get('dialog_id'),id);return json({status:'READY',dialog_id:id,messages:rows});
 }
 assert.equal(url.pathname,'/api/nox/chat/stream');
 const data=JSON.parse(init.body);assert.equal(data.dialog_id,id);
 const ex='fixture-exchange-'+(++posts);
 const frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM',dialog_id:id},
 {type:'start',model,dialog_id:id},...Array.from(answer,text=>({type:'delta',text,dialog_id:id})),
 {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:ex}];
 rows.push({role:'user',content:data.message,exchange_id:ex},{role:'assistant',content:answer,exchange_id:ex});
 const buf=new TextEncoder().encode(frames.map(x=>JSON.stringify(x)).join('\n')+'\n');
 return new Response(new ReadableStream({start(c){for(let n=0;n<buf.length;n++)c.enqueue(buf.subarray(n,n+1));c.close();}}));
}};
vm.runInNewContext(candidate,{window,location:loc,URL,Request,Response,ReadableStream,TextEncoder,TextDecoder,AbortController,Intl,performance,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},setTimeout,clearTimeout,requestAnimationFrame:f=>setTimeout(f,0)},{timeout:1000});
const expected={dialog_id:id,prior_exchange_id:prior,baseline_browser_posts:1,baseline_admitted_posts:1,turns:[]};
const observed=[];
for(const turn of [2,3]){
 const startedAt=performance.now();
 browserPosts++;
 const response=await window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({dialog_id:id,request_id:'fixture-'+turn,message:'Вопрос '+turn+' ¿sí?'})});
 // Clone the same response for independent raw-body digest, not another request.
 const raw=response.clone().arrayBuffer();
 const proof=await measureSseResponse(response,{protocol:'nox-browser',expectedDialogId:id,startedAt});
 const wire=Buffer.from(await raw);
 expected.turns.push({turn,exchange_id:'fixture-exchange-'+turn,body_sha256:sha(wire),visible_text_sha256:sha(answer)});
 observed.push({turn,browser_posts:browserPosts,admitted_posts:posts,proof});
 assert.equal(posts,turn);assert.equal(proof.visible_text_sha256,sha(answer));
}
const pair=bindExistingTurnPair(expected,observed);
assert.equal(pair.status,'B4_PAIR_INPUTS_MATCHED');
assert.equal(pair.native_verified,false);assert.equal(pair.canonical_s03_verified,false);
assert.equal(JSON.stringify(rows.slice(0,2)),priorSnapshot);assert.equal(rows.length,6);
assert.equal(posts,3);assert.equal(browserPosts,3);assert.equal(stops,0);
assert.deepEqual(phases,['waiting','speaking','idle','waiting','speaking','idle']);
assert.throws(()=>bindExistingTurnPair(expected,[observed[0],{...observed[1],admitted_posts:4}]),/B4_PAIR_POST_COUNT/);
console.log('B4_R54_COMPOSED '+JSON.stringify({turns:pair.turns.map(({turn,ttft_ms,completion_ms})=>({turn,ttft_ms,completion_ms})),newBrowserPosts:browserPosts-1,newAdmittedPosts:posts-1,priorUnchanged:true,canonical_s03_verified:false,native_accepted:false}));
