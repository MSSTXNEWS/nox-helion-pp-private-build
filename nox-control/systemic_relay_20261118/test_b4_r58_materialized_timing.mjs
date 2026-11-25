// R58: exact materialized R61 + delayed upstream transport. Network-free serial fixture.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import vm from 'node:vm';
import {performance} from 'node:perf_hooks';
import {measureSseResponse} from './b4_sse_latency_probe.mjs';
import {bindUpstreamTimingPair} from './b4_upstream_timing_pair.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
const root=process.argv[2];
assert(root,'path to exact materialized B3 candidate required');
const candidate=readFileSync(root,'utf8');
assert.equal(Buffer.byteLength(candidate),24786);
assert.equal(sha(candidate),'9cd1cd1ab96a01b295418b59d53669b742d804520af15e3da648716b02427ef3');
const id='a'.repeat(32),model='GLM-5.3-Flash', prior='fixture-exchange-1';
const answerFor=turn=>'Привет '+turn+', ¿qué tal? 👩‍💻';
const route='fixture-route',weights=sha('fixture-weight'),tokenizer=sha('fixture-tokenizer');
const pins={model,route_id:route,weights_sha256:weights,tokenizer_sha256:tokenizer,baseline_posts:1,turns:[]};
const records=[]; let upstreamPosts=1;
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
 const ex='fixture-exchange-'+(++posts),turn=posts,request_id='fixture-upstream-'+turn;
 const startedAt=performance.now();upstreamPosts++;
 const raw=[{choices:[{delta:{content:answerFor(turn)},finish_reason:null}]},{choices:[{delta:{},finish_reason:'stop'}]},'[DONE]'].map(x=>'data: '+(typeof x==='string'?x:JSON.stringify(x))+'\n\n').join('');
 // Separate first transport byte, first printable text, terminal event, physical EOF.
 const packets=[': heartbeat\n\n',...raw.match(/[^\n]+\n\n/g)];
 let cursor=0;
 const upstreamResponse=new Response(new ReadableStream({async pull(c){
   if(cursor>0)await delay(30);
   if(cursor===packets.length){c.close();return;}
   c.enqueue(new TextEncoder().encode(packets[cursor++]));
 }}),{headers:{'content-type':'text/event-stream'}});

 const upstreamWire=upstreamResponse.clone().text();
 const upstream=await measureSseResponse(upstreamResponse,{startedAt});
 // Derive the native bridge deltas from the same upstream fixture bytes, no second request.
 const sameWire=await upstreamWire;
 assert.equal(sameWire,': heartbeat\n\n'+raw);
 assert(upstream.ttft_ms-upstream.first_byte_ms>=15,'heartbeat must not count as printable TTFT');
 assert(upstream.sse_done_ms-upstream.ttft_ms>=15,'terminal must not count as first text');
 assert(upstream.completion_ms-upstream.sse_done_ms>=15,'DONE must not count as EOF');
 const answer=sameWire.split('\n\n').filter(x=>x.startsWith('data: {')).map(x=>JSON.parse(x.slice(6)).choices[0].delta.content??'').join('');
 assert.equal(upstream.visible_text_sha256,sha(answer));
 const record=Buffer.from(JSON.stringify({...upstream,turn,dialog_id:id,exchange_id:ex,request_id,model,route_id:route,weights_sha256:weights,tokenizer_sha256:tokenizer,upstream_posts:upstreamPosts,timing_scope:'upstream-response-consumer'}));
 records.push(record);pins.turns.push({turn,exchange_id:ex,request_id,record_sha256:sha(record),body_sha256:sha(sameWire)});
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
 expected.turns.push({turn,exchange_id:'fixture-exchange-'+turn,body_sha256:sha(wire),visible_text_sha256:sha(answerFor(turn))});
 observed.push({turn,browser_posts:browserPosts,admitted_posts:posts,proof});
 assert.equal(posts,turn);assert.equal(upstreamPosts,turn);assert.equal(proof.visible_text_sha256,sha(answerFor(turn)));
}
const pair=bindUpstreamTimingPair(expected,observed,pins,records);
assert.equal(pair.status,'B4_TIMING_INPUTS_MATCHED');
assert.equal(pair.native_verified,false);assert.equal(pair.canonical_s03_verified,false);
assert.equal(JSON.stringify(rows.slice(0,2)),priorSnapshot);assert.equal(rows.length,6);
assert.equal(posts,3);assert.equal(browserPosts,3);assert.equal(upstreamPosts,3);assert.equal(stops,0);
assert.deepEqual(phases,['waiting','speaking','idle','waiting','speaking','idle']);
assert.throws(()=>bindUpstreamTimingPair(expected,[observed[0],{...observed[1],admitted_posts:4}],pins,records),/B4_PAIR_POST_COUNT/);
assert.throws(()=>bindUpstreamTimingPair(expected,observed,pins,[records[1],records[0]]),/B4_UPSTREAM_DIGEST/);
assert.equal(pair.model_tokens_per_second,null);
console.log('B4_R58_MATERIALIZED_TIMING '+JSON.stringify({turns:pair.turns,newBrowserPosts:browserPosts-1,newAdmittedPosts:posts-1,newMockUpstreamPosts:upstreamPosts-1,priorUnchanged:true,canonical_s03_verified:false,native_accepted:false}));
