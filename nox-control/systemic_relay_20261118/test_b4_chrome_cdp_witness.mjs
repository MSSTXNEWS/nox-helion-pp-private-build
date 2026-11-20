import {test} from 'node:test';
import assert from 'node:assert/strict';
import {capture} from './b4_chrome_cdp_witness.mjs';
const body='data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n';
class Stub {
  constructor(){this.bodies=new Map();}
  on(fn){this.emit=fn;}
  close(){}
  async send(cmd,p={}){if(cmd==='Browser.getVersion')return {product:'CDP-FIXTURE'};
    if(cmd==='Network.streamResourceContent')return {};
    if(cmd==='Network.getResponseBody')return {body:this.bodies.get(p.requestId).toString('base64'),base64Encoded:true};return {};}
}
async function run(missing=false,chunksForSecondTurn=null,responseBodyForSecondTurn=null,encoding=null,options={}){const c=new Stub();
  if(options.postDataMode){
    const normalSend=c.send.bind(c);
    c.send=(cmd,p={})=>{
      if(cmd!=='Network.getRequestPostData')return normalSend(cmd,p);
      if(options.postDataMode==='late')return new Promise(resolve=>setTimeout(
        ()=>resolve({postData:'{"fallback":'+JSON.stringify(p.requestId)+'}'}),35));
      if(options.postDataMode==='reject')return Promise.reject(Error('POST_DATA_UNAVAILABLE'));
      if(options.postDataMode==='hang')return new Promise(()=>{});
      return normalSend(cmd,p);
    };
  }
  return capture({ws:'ws://127.0.0.1:9333/fake',makeSession:async()=>c,timeoutMs:2000,onReady:async()=>{
  setTimeout(async()=>{for(let i=0;i<2;i++){
    const requestId=String(i+1),o=i===1?options:{},timestamp=Object.hasOwn(o,'requestTimestamp')?o.requestTimestamp:100+i;
    const chunks=i===1&&chunksForSecondTurn?chunksForSecondTurn.map(b=>Buffer.from(b)):[Buffer.from(body)];
    const captured=Buffer.concat(chunks);
    c.bodies.set(requestId,i===1&&responseBodyForSecondTurn!==null?Buffer.from(responseBodyForSecondTurn):captured);
    c.emit('Network.requestWillBeSent',{requestId,timestamp,request:{method:'POST',url:'http://localhost/api/nox/chat',
      ...(i===1&&o.postDataMode?{}:{postData:'{"secret":"'+i+'"}'})}});
    const emitExtra=()=>c.emit('Network.responseReceivedExtraInfo',{requestId,statusCode:o.extraStatus??200,headers:o.extraHeaders??{}});
    if(o.extraBefore)emitExtra();
    const response={status:200,mimeType:'text/event-stream',headers:i===1&&encoding?{'Content-Encoding':encoding}:{}};
    for(const key of ['fromDiskCache','fromServiceWorker','fromPrefetchCache','fromEarlyHints','cacheStorageCacheName','serviceWorkerResponseSource','serviceWorkerRouterInfo']){
      if(o[key]!==undefined)response[key]=o[key];
    }
    const responseTime=Object.hasOwn(o,'responseTimestamp')?o.responseTimestamp:timestamp+.005;
    const responseEvent={requestId,timestamp:responseTime,response,hasExtraInfo:o.hasExtraInfo===true};
    if(o.omitHasExtraInfo)delete responseEvent.hasExtraInfo;
    c.emit('Network.responseReceived',responseEvent);
    if(o.extraAfter)emitExtra();
    await new Promise(r=>setImmediate(r));
    if(o.cacheEvent)c.emit('Network.requestServedFromCache',{requestId});
    const dataTime=Object.hasOwn(o,'dataTimestamp')?o.dataTimestamp:timestamp+.01;
    if(missing&&i===1)c.emit('Network.dataReceived',{requestId,timestamp:dataTime});
    else for(const [index,chunk] of chunks.entries())c.emit('Network.dataReceived',{requestId,timestamp:Array.isArray(o.chunkTimestamps)?o.chunkTimestamps[index]:dataTime,data:chunk.toString('base64')});
    if(o.extraBeforeFinish)emitExtra();
    c.emit('Network.loadingFinished',{requestId,timestamp:Object.hasOwn(o,'closeTimestamp')?o.closeTimestamp:timestamp+.02});
    await new Promise(r=>setImmediate(r));
  }},10);
}});}
test('two Chrome-protocol POST events bind distinct digest-only receipts, with SSE timing',async()=>{
  const x=await run();assert.equal(x.cdp_consistent,true);assert.equal(x.ttft_sse_verified,true);
  assert.equal(x.turns.length,2);assert.notEqual(x.turns[0].request_sha256,x.turns[1].request_sha256);
  assert.equal(x.turns[0].ttft_ms,10);assert.equal(x.turns[1].sse_done_ms,10);
  assert.equal(x.turns[1].cdp_decoded_body_matches_stream,true);
  assert.equal(x.turns[1].cdp_streamed_body_sha256,x.turns[1].cdp_decoded_body_sha256);
  assert.equal(x.native_verified,false);assert.equal(x.browser_authenticated,false);
  assert.equal(x.canonical_s03_verified,false);assert.equal(x.remote_attested,false);
  assert.doesNotMatch(JSON.stringify(x),/secret|Hello/);
});
test('CDP chunk without data cannot prove TTFT or DONE',async()=>{
  const x=await run(true);assert.equal(x.cdp_consistent,false);assert.equal(x.ttft_sse_verified,false);
  assert.equal(x.turns[1].ttft_ms,null);assert.equal(x.turns[1].sse_done_ms,null);
});

test('split UTF-8 and SSE framing are lossless; partial frame/invalid EOF fail closed',async()=>{
  const {createHash}=await import('node:crypto');
  const visible='Привет 🐈';
  const unicodeBody='data: '+JSON.stringify({choices:[{delta:{content:visible}}]})+'\n\ndata: '+JSON.stringify({choices:[{delta:{},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n';
  const raw=Buffer.from(unicodeBody,'utf8'),split=raw.indexOf(Buffer.from('🐈'))+2;
  assert.ok(split>2);
  const ok=await run(false,[raw.subarray(0,split),raw.subarray(split,split+1),raw.subarray(split+1)]);
  assert.equal(ok.ttft_sse_verified,true);
  assert.equal(ok.turns[1].visible_text_sha256,createHash('sha256').update(visible).digest('hex'));
  const partial=await run(false,[Buffer.from(body),Buffer.from('data: {"incomplete":true}')]);
  assert.equal(partial.ttft_sse_verified,false);
  assert.equal(partial.turns[1].stream_timing_complete,false);
  assert.equal(partial.turns[1].visible_text_sha256,null);
  const broken=await run(false,[Buffer.from(body),Buffer.from([0xf0,0x9f])]);
  assert.equal(broken.ttft_sse_verified,false);
  assert.equal(broken.turns[1].stream_timing_complete,false);
  assert.equal(broken.turns[1].visible_text_sha256,null);
  assert.doesNotMatch(JSON.stringify(ok),/Привет|🐈/);
});
test('independent decoded CDP body detects missing, duplicated, reordered, altered chunks and compressed response',async()=>{
  const chunks=[Buffer.from(body.slice(0,25)),Buffer.from(body.slice(25))];
  const normal=await run(false,chunks);
  assert.equal(normal.ttft_sse_verified,true);
  const missing=await run(false,[chunks[0]],Buffer.from(body));
  assert.equal(missing.cdp_consistent,false);assert.equal(missing.ttft_sse_verified,false);
  const duplicated=await run(false,[chunks[0],chunks[0],chunks[1]],Buffer.from(body));
  assert.equal(duplicated.cdp_consistent,false);assert.equal(duplicated.ttft_sse_verified,false);
  const reordered=await run(false,[chunks[1],chunks[0]],Buffer.from(body));
  assert.equal(reordered.cdp_consistent,false);assert.equal(reordered.ttft_sse_verified,false);
  const mutated=await run(false,[Buffer.from(body.replace('Hello','Hella'))],Buffer.from(body));
  assert.equal(mutated.cdp_consistent,false);assert.equal(mutated.ttft_sse_verified,false);
  assert.notEqual(mutated.turns[1].cdp_streamed_body_sha256,mutated.turns[1].cdp_decoded_body_sha256);
  const encoded=await run(false,[Buffer.from(body)],null,'gzip');
  assert.equal(encoded.cdp_consistent,false);assert.equal(encoded.ttft_sse_verified,false);
  assert.equal(encoded.turns[1].cdp_decoded_body_matches_stream,false);
  assert.doesNotMatch(JSON.stringify(normal),/Hello|secret/);
});

test('early/late ExtraInfo, HTTP2 headers and cache metadata fence SSE acceptance',async()=>{
  // HTTP/2/QUIC may omit headersText; normalized Headers object suffices.
  for(const flags of [
    {hasExtraInfo:true,extraBefore:true,extraHeaders:{':status':'200','content-encoding':'identity'}},
    {hasExtraInfo:true,extraAfter:true,extraHeaders:{'Content-Encoding':'identity'}},
    {hasExtraInfo:true,extraBeforeFinish:true,extraHeaders:{}},
  ]){
    const x=await run(false,null,null,null,flags);
    assert.equal(x.cdp_consistent,true,JSON.stringify(flags));
    assert.equal(x.ttft_sse_verified,true,JSON.stringify(flags));
  }
  for(const flags of [
    {hasExtraInfo:true}, // expected late headers absent
    {omitHasExtraInfo:true}, // unproven metadata contract
    {hasExtraInfo:true,extraAfter:true,extraStatus:304}, // cached 200 alias
    {hasExtraInfo:true,extraBefore:true,extraHeaders:{'Content-Encoding':'gzip'}},
    {hasExtraInfo:true,extraBeforeFinish:true,extraHeaders:{'content-encoding':'br'}},
    {hasExtraInfo:true,extraAfter:true,extraHeaders:{'Content-Encoding':'identity, gzip'}},
    {hasExtraInfo:true,extraBefore:true,extraAfter:true}, // duplicate ExtraInfo
    {extraAfter:true}, // contradictory extra when hasExtraInfo=false
    {cacheEvent:true},
    {fromDiskCache:true},
    {fromServiceWorker:true},
    {fromPrefetchCache:true},
    {fromEarlyHints:true},
    {cacheStorageCacheName:'unexpected-cache'},
    {serviceWorkerResponseSource:'network'},
    {serviceWorkerRouterInfo:{matchedSourceType:'network'}},
  ]){
    const x=await run(false,null,null,null,flags);
    assert.equal(x.cdp_consistent,false,JSON.stringify(flags));
    assert.equal(x.ttft_sse_verified,false,JSON.stringify(flags));
    assert.equal(x.turns[1].ttft_ms,null,JSON.stringify(flags));
  }
});

test('CDP timestamp admission is finite, nonnegative, monotonic and ordered request→first→visible→DONE→close',async()=>{
  const valid=await run();
  assert.equal(valid.cdp_consistent,true);assert.equal(valid.ttft_sse_verified,true);
  for(const flags of [
    {requestTimestamp:-1,responseTimestamp:0.005,dataTimestamp:0.01,closeTimestamp:0.02},
    {requestTimestamp:NaN},{requestTimestamp:Infinity},
    {responseTimestamp:NaN},{responseTimestamp:Infinity},
    {responseTimestamp:100.5},
    {dataTimestamp:101.003},{dataTimestamp:NaN},{dataTimestamp:Infinity},
    {closeTimestamp:101.009},{closeTimestamp:NaN},{closeTimestamp:Infinity},
    {responseTimestamp:101.015,dataTimestamp:101.01},
  ]){
    const r=await run(false,null,null,null,flags);
    assert.equal(r.cdp_consistent,false,JSON.stringify(flags),'invalid chronology must fail body validity');
    assert.equal(r.ttft_sse_verified,false,JSON.stringify(flags),'invalid chronology cannot count as measured latency');
    assert.equal(r.turns[1].stream_timing_complete,false,JSON.stringify(flags));
  }
});

test('duplicate terminal and post-DONE frames fail closed, including split chunks',async()=>{
  // Keep one legitimate split-terminal control and exercise the real capture path.
  const splitAt=Buffer.byteLength(body)-5;
  const valid=await run(false,[Buffer.from(body).subarray(0,splitAt),Buffer.from(body).subarray(splitAt)]);
  assert.equal(valid.cdp_consistent,true);assert.equal(valid.ttft_sse_verified,true);
  const tails=[
    'data: [DONE]\\n\\n',
    'data: {"choices":[{"delta":{"content":"late"}}]}\\n\\n',
    'data: {"unexpected":true}\\n\\n',
    'data: malformed-json\\n\\n',
    ': comment-after-terminal\\n\\n'
  ].map(s=>s.replaceAll('\\n','\n'));
  for(const extra of tails){
    const mutated=Buffer.from(body+extra,'utf8'),split=Buffer.byteLength(body)-2;
    const output=await run(false,[mutated.subarray(0,split),mutated.subarray(split)]);
    assert.equal(output.cdp_consistent,false,'post-terminal frame must invalidate digest-bound witness');
    assert.equal(output.ttft_sse_verified,false,'post-terminal frame must invalidate TTFT evidence');
    assert.equal(output.turns[1].ttft_ms,null);
    assert.equal(output.turns[1].sse_done_ms,null);
    assert.equal(output.turns[1].stream_timing_complete,false);
    assert.equal(output.turns[1].visible_text_sha256,null);
  }
});

test('malformed JSON and explicit SSE errors before DONE invalidate measured TTFT; valid heartbeat/usage allowed',async()=>{
  const permitted=[
    ': keepalive\\n\\n',
    'event: ping\\n\\n',
    'data: {"choices":[],"usage":{"completion_tokens":2}}\\n\\n',
    'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}\\n\\n',
    'event: usage\\ndata: {"usage":{"completion_tokens":1}}\\n\\n'
  ].map(s=>s.replaceAll('\\n','\n'));
  for(const fragment of permitted){
    const x=await run(false,[Buffer.from(fragment+body)]);
    assert.equal(x.cdp_consistent,true,fragment);
    assert.equal(x.ttft_sse_verified,true,fragment);
  }
  const invalid=[
    'event: error\\ndata: {"error":{"message":"upstream failed"}}\\n\\n',
    'event: error\\n\\n',
    'data: {"error":{"message":"model error"}}\\n\\n',
    'data: not-json\\n\\n',
    'data: []\\n\\n',
    'data: {"unknown":true}\\n\\n',
    'data: {"choices":[]}\\n\\n',
    'data: {"choices":[{"delta":{"content":2}}]}\\n\\n',
    'data: {"choices":[{"delta":null}]}\\n\\n',
    'event: unexpected\\ndata: {"choices":[{"delta":{"content":"text"}}]}\\n\\n'
  ].map(s=>s.replaceAll('\\n','\n'));
  for(const fragment of invalid){
    const altered=Buffer.from(body.replace('data: [DONE]',fragment+'data: [DONE]'));
    const split=Math.min(altered.length-1,Buffer.byteLength(body)-6);
    const x=await run(false,[altered.subarray(0,split),altered.subarray(split)]);
    assert.equal(x.cdp_consistent,false,fragment);
    assert.equal(x.ttft_sse_verified,false,fragment);
    assert.equal(x.turns[1].ttft_ms,null,fragment);
    assert.equal(x.turns[1].sse_done_ms,null,fragment);
    assert.equal(x.turns[1].visible_text_sha256,null,fragment);
  }
});

test('late asynchronous getRequestPostData ACK is joined; rejected or hanging lookup fails closed',async()=>{
  const late=await run(false,null,null,null,{postDataMode:'late'});
  assert.equal(late.cdp_consistent,true,'late ACK before bounded deadline must bind request');
  assert.equal(late.ttft_sse_verified,true);
  assert.match(late.turns[1].request_sha256,/^[a-f0-9]{64}$/);
  assert.notEqual(late.turns[0].request_sha256,late.turns[1].request_sha256);
  const rejected=await run(false,null,null,null,{postDataMode:'reject'});
  assert.equal(rejected.cdp_consistent,false);
  assert.equal(rejected.ttft_sse_verified,false);
  assert.equal(rejected.turns[1].request_sha256,null);
  const began=Date.now();
  const stalled=await run(false,null,null,null,{postDataMode:'hang'});
  assert.ok(Date.now()-began<1800,'fallback must not hang capture forever');
  assert.equal(stalled.cdp_consistent,false);
  assert.equal(stalled.ttft_sse_verified,false);
  assert.equal(stalled.turns[1].request_sha256,null);
});

test('CDP [DONE] is verified only after a unique explicit model finish_reason=stop',async()=>{
  const clean=await run();
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  const malformed=[
    body.replace('"finish_reason":"stop"','"finish_reason":"length"'),
    body.replace('"finish_reason":"stop"','"finish_reason":"content_filter"'),
    body.replace('"finish_reason":"stop"','"finish_reason":"tool_calls"'),
    body.replace('"finish_reason":"stop"','"finish_reason":null'),
    body.replace('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',''),
    body.replace('data: [DONE]','data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]'),
    body.replace('data: [DONE]','data: {"choices":[{"delta":{"content":"late"}}]}\n\ndata: [DONE]')
  ];
  for(const wire of malformed){
    const actual=await run(false,[Buffer.from(wire)]);
    assert.equal(actual.cdp_consistent,false,'invalid finish reason cannot be accepted');
    assert.equal(actual.ttft_sse_verified,false,'[DONE] cannot hide incomplete or repeated model finality');
    assert.equal(actual.turns[1].ttft_ms,null);
    assert.equal(actual.turns[1].sse_done_ms,null);
    assert.equal(actual.turns[1].visible_text_sha256,null);
  }
});


test('nonfinite numbers anywhere in JSON SSE payload fail closed before DONE',async()=>{
  const inject=json=>body.replace('data: [DONE]','data: '+json+'\n\ndata: [DONE]');
  // These literals parse successfully but become +/-Infinity in JavaScript.
  const invalid=[
    '{"usage":{"total_tokens":1e309}}',
    '{"usage":{"nested":[{"score":-1e309}]}}',
    '{"choices":[{"delta":{},"metadata":{"score":1e309}}]}'
  ];
  for(const json of invalid){
    const x=await run(false,[Buffer.from(inject(json))]);
    assert.equal(x.cdp_consistent,false,json);
    assert.equal(x.ttft_sse_verified,false,json);
    assert.equal(x.turns[1].stream_timing_complete,false,json);
  }
  const valid=await run(false,[Buffer.from(inject('{"usage":{"total_tokens":42,"nested":[0.05,-3,1e12]}}'))]);
  assert.equal(valid.cdp_consistent,true);
  assert.equal(valid.ttft_sse_verified,true);
});


test('first-visible TTFT ignores zero-width, controls and isolated marks before real RU/ES/emoji text',async()=>{
  const delta=text=>'data: '+JSON.stringify({choices:[{delta:{content:text}}]})+'\n\n';
  const terminal='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n';
  const invisible='\u200B\u200E\uFEFF\u00AD\u0000\t\u0301\uFE0F';
  const invisibleWire=delta(invisible)+terminal;
  const invisibleOnly=await run(false,[Buffer.from(invisibleWire,'utf8')]);
  assert.equal(invisibleOnly.cdp_consistent,true,'unambiguous SSE body bytes still match');
  assert.equal(invisibleOnly.ttft_sse_verified,false,'invisible-only content cannot certify first-visible TTFT');
  assert.equal(invisibleOnly.turns[1].ttft_ms,null);
  const visible='Привет, ¡Hola! 🧠';
  const chunks=[delta(invisible),delta(visible),terminal].map(s=>Buffer.from(s,'utf8'));
  const admitted=await run(false,chunks,null,null,{chunkTimestamps:[101.010,101.015,101.018]});
  assert.equal(admitted.cdp_consistent,true);
  assert.equal(admitted.ttft_sse_verified,true);
  assert.equal(admitted.turns[1].first_network_byte_ms,5);
  assert.equal(admitted.turns[1].ttft_ms,15,'first printable RU/ES/emoji delta, not first invisible delta');
  assert.equal(admitted.turns[1].sse_done_ms,18);
  for(const printable of ['Русский','Español','🧠','!','7']){
    const sample=await run(false,[Buffer.from(delta(invisible)+delta(printable)+terminal)]);
    assert.equal(sample.ttft_sse_verified,true,printable);
  }
  assert.doesNotMatch(JSON.stringify(admitted),/Привет|Hola|secret/);
});


test('CDP accepts only one zero-indexed SSE choice for TTFT/completion',async()=>{
  const wire=choices=>
    'data: '+JSON.stringify({choices})+'\n\n'+
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'+
    'data: [DONE]\n\n';
  for(const validChoice of [
    {index:0,delta:{content:'Indexed'}},
    {delta:{content:'Legacy'}}
  ]){
    const x=await run(false,[Buffer.from(wire([validChoice]))]);
    assert.equal(x.cdp_consistent,true);
    assert.equal(x.ttft_sse_verified,true);
  }
  const invalid=[
    [{index:0,delta:{content:'A'}},{index:1,delta:{content:'B'}}],
    [{delta:{content:'A'}},{delta:{content:'B'}}],
    [{index:1,delta:{content:'Wrong'}}],
    [{index:-1,delta:{content:'Wrong'}}],
    [{index:'0',delta:{content:'Wrong'}}],
    [{index:null,delta:{content:'Wrong'}}],
    [{index:0.5,delta:{content:'Wrong'}}],
    [{index:true,delta:{content:'Wrong'}}]
  ];
  for(const choices of invalid){
    const x=await run(false,[Buffer.from(wire(choices))]);
    assert.equal(x.cdp_consistent,false,JSON.stringify(choices));
    assert.equal(x.ttft_sse_verified,false,JSON.stringify(choices));
    assert.equal(x.turns[1].ttft_ms,null);
    assert.equal(x.turns[1].sse_done_ms,null);
  }
});
