import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {measureSseResponse} from './b4_sse_latency_probe.mjs';
import {bindUpstreamTimingPair} from './b4_upstream_timing_pair.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
const id='a'.repeat(32),model='GLM-5.3-Flash',route='fixture-route';
const weights=sha('fixture-weight'),tokenizer=sha('fixture-tokenizer');
const expected={dialog_id:id,prior_exchange_id:'prior-1',baseline_browser_posts:1,baseline_admitted_posts:1,turns:[]};
const pins={model,route_id:route,weights_sha256:weights,tokenizer_sha256:tokenizer,baseline_posts:1,turns:[]};
const observed=[],records=[],objects=[];
const sse=frames=>frames.map(x=>'data: '+(typeof x==='string'?x:JSON.stringify(x))+'\n\n').join('');
const response=body=>new Response(body,{headers:{'content-type':'text/event-stream'}});
for(const turn of [2,3]){
 const ex='exchange-'+turn,req='request-'+turn,answer='Привет '+turn+' ¿sí? 👋';
 const body=sse([{type:'meta',dialog_id:id,answer_source:'NATIVE_PENDING'},{type:'token',t:answer},{type:'done',dialog_id:id,exchange_id:ex,status:'done',saved:true,history_persisted:true,answer_source:'LIVE_NOX',s03_integrated:true}]);
 const raw=sse([{choices:[{delta:{content:answer},finish_reason:null}]},{choices:[{delta:{},finish_reason:'stop'}]},'[DONE]']);
 const browser=await measureSseResponse(response(body),{protocol:'nox-browser',expectedDialogId:id});
 const upstream=await measureSseResponse(response(raw));
 expected.turns.push({turn,exchange_id:ex,body_sha256:sha(body),visible_text_sha256:sha(answer)});
 observed.push({turn,browser_posts:turn,admitted_posts:turn,proof:browser});
 const rec={...upstream,turn,dialog_id:id,exchange_id:ex,request_id:req,model,route_id:route,weights_sha256:weights,tokenizer_sha256:tokenizer,upstream_posts:turn,timing_scope:'upstream-response-consumer'};
 const bytes=Buffer.from(JSON.stringify(rec));objects.push(rec);records.push(bytes);
 pins.turns.push({turn,exchange_id:ex,request_id:req,record_sha256:sha(bytes),body_sha256:sha(raw)});
}
const result=bindUpstreamTimingPair(expected,observed,pins,records);
assert.equal(result.status,'B4_TIMING_INPUTS_MATCHED');assert.equal(result.native_verified,false);
assert.equal(result.model_tokens_per_second,null);assert.equal(result.turns.length,2);
let n=0;
for(const [field,value,code] of [
 ['model','other-model','B4_UPSTREAM_BINDING'],['route_id','other-route','B4_UPSTREAM_BINDING'],
 ['weights_sha256',sha('other'),'B4_UPSTREAM_BINDING'],['tokenizer_sha256',sha('other'),'B4_UPSTREAM_BINDING'],
 ['exchange_id','prior-1','B4_UPSTREAM_BINDING'],['request_id','request-2','B4_UPSTREAM_BINDING'],
 ['visible_text_sha256',sha('wrong'),'B4_UPSTREAM_BINDING'],['body_sha256',sha('wrong'),'B4_UPSTREAM_BINDING'],
 ['upstream_posts',4,'B4_UPSTREAM_BINDING'],['timing_scope','browser-consumer','B4_UPSTREAM_BINDING'],
 ['native_verified',true,'B4_UPSTREAM_BINDING'],['model_tokens_per_second',10,'B4_UPSTREAM_BINDING'],
 ['ttft_ms',-1,'B4_UPSTREAM_TIMING'],['completion_ms',-1,'B4_UPSTREAM_TIMING']
]){
 const bytes=Buffer.from(JSON.stringify({...objects[1],[field]:value}));
 const p={...pins,turns:[pins.turns[0],{...pins.turns[1],record_sha256:sha(bytes)}]};
 assert.throws(()=>bindUpstreamTimingPair(expected,observed,p,[records[0],bytes]),{code});n++;
}
assert.throws(()=>bindUpstreamTimingPair(expected,observed,pins,[records[1],records[0]]),{code:'B4_UPSTREAM_DIGEST'});n++;
assert.throws(()=>bindUpstreamTimingPair(expected,observed,{...pins,turns:[pins.turns[0],{...pins.turns[1],request_id:'request-2'}]},records),{code:'B4_UPSTREAM_PIN'});n++;
console.log('B4_R55_SOURCE '+JSON.stringify({positive:2,negative:n,turns:result.turns,native_accepted:false,network_posts:0}));
