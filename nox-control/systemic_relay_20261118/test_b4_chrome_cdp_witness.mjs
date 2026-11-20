import {test} from 'node:test';
import assert from 'node:assert/strict';
import {capture} from './b4_chrome_cdp_witness.mjs';
const body='data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n';
class Stub {
  constructor(){this.bodies=new Map();}
  on(fn){this.emit=fn;}
  close(){}
  async send(cmd,p={}){if(cmd==='Browser.getVersion')return {product:'CDP-FIXTURE'};
    if(cmd==='Network.streamResourceContent')return {};
    if(cmd==='Network.getResponseBody')return {body:this.bodies.get(p.requestId).toString('base64'),base64Encoded:true};return {};}
}
async function run(missing=false,chunksForSecondTurn=null,responseBodyForSecondTurn=null,encoding=null,options={}){const c=new Stub();return capture({ws:'ws://127.0.0.1:9333/fake',makeSession:async()=>c,timeoutMs:2000,onReady:async()=>{
  setTimeout(async()=>{for(let i=0;i<2;i++){
    const requestId=String(i+1),o=i===1?options:{},timestamp=Object.hasOwn(o,'requestTimestamp')?o.requestTimestamp:100+i;
    const chunks=i===1&&chunksForSecondTurn?chunksForSecondTurn.map(b=>Buffer.from(b)):[Buffer.from(body)];
    const captured=Buffer.concat(chunks);
    c.bodies.set(requestId,i===1&&responseBodyForSecondTurn!==null?Buffer.from(responseBodyForSecondTurn):captured);
    c.emit('Network.requestWillBeSent',{requestId,timestamp,request:{method:'POST',url:'http://localhost/api/nox/chat',postData:'{"secret":"'+i+'"}'}});
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
    else for(const chunk of chunks)c.emit('Network.dataReceived',{requestId,timestamp:dataTime,data:chunk.toString('base64')});
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
  const unicodeBody='data: '+JSON.stringify({choices:[{delta:{content:visible}}]})+'\n\ndata: [DONE]\n\n';
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
