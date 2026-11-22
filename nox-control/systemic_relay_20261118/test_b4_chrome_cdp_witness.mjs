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
    if(cmd==='Page.getFrameTree'){
      this.frameTreeReads=(this.frameTreeReads??0)+1;
      if(this.frameTreeReads>1&&this.rejectFinalSnapshot)throw Error('FIXTURE_SNAPSHOT_REJECTED');
      if(this.frameTreeReads>1&&this.dropFinalFrame)return {frameTree:{}};
      return {frameTree:{frame:{
        id:this.fixtureFrameId??'fixture-frame',
        loaderId:this.fixtureLoaderId??'fixture-loader',
        url:this.fixtureFrameUrl??this.targetUrl??'http://localhost/nox/chat'
      }}};
    }
    if(cmd==='Target.getTargetInfo')return {targetInfo:{
      targetId:this.fixtureTargetId??'fixture-page',
      type:this.targetType??'page',
      url:this.targetUrl??'http://localhost/nox/chat'
    }};
    if(cmd==='Network.getResponseBody'){
       if(this.responseBodyHang?.includes(p.requestId))return new Promise(()=>{});
       if(this.responseBodyReject?.includes(p.requestId))throw Error('BODY_LOOKUP_REJECTED');
      if(this.responseBodyDelay?.[p.requestId])
        await new Promise(resolve=>setTimeout(resolve,this.responseBodyDelay[p.requestId]));
      if(this.responseBodyRejectAfterDelay?.includes(p.requestId)){
        this.responseBodySettled?.(p.requestId,'rejected');
        throw Error('BODY_LOOKUP_LATE_REJECTED');
      }
      this.responseBodySettled?.(p.requestId,'resolved');
      const canonical=this.bodies.get(p.requestId).toString('base64');
      if(p.requestId==='2'&&typeof this.postAckEvent==='function')
        setTimeout(()=>this.postAckEvent(this),25);
      if(typeof this.responseBodyTextMutator==='function')return {body:this.responseBodyTextMutator(this.bodies.get(p.requestId).toString('utf8'),p.requestId),base64Encoded:false};
      return {body:typeof this.responseBodyMutator==='function'?this.responseBodyMutator(canonical,p.requestId):canonical,base64Encoded:true};
    }return {};}
}
async function run(missing=false,chunksForSecondTurn=null,responseBodyForSecondTurn=null,encoding=null,options={}){const c=new Stub();
  c.targetType=options.targetType;
  c.targetUrl=options.targetUrl;
  c.responseBodyMutator=options.responseBodyBase64Mutator;
  c.responseBodyTextMutator=options.responseBodyTextMutator;
  c.responseBodyDelay=options.responseBodyDelay;
  c.responseBodyHang=options.responseBodyHang;
  c.responseBodyReject=options.responseBodyReject;
  c.responseBodyRejectAfterDelay=options.responseBodyRejectAfterDelay;
  c.responseBodySettled=options.responseBodySettled;
  c.postAckEvent=options.postAckEvent;
  if(options.postDataMode||options.firstPostDataMode){
    const normalSend=c.send.bind(c);
    c.send=(cmd,p={})=>{
      if(cmd!=='Network.getRequestPostData')return normalSend(cmd,p);
      // Scope the asynchronous ACK to its own request; a first-turn ACK
      // must never be mistaken for second-turn POST metadata.
      const first=p.requestId==='1';
      const mode=first?(options.firstPostDataMode??options.postDataMode):options.postDataMode;
      const data=first?(options.firstPostDataText??options.postDataText):options.postDataText;
      const delay=first?(options.firstPostDataDelayMs??options.postDataDelayMs??280):
        (options.postDataDelayMs??280);
      if(mode==='late')return new Promise(resolve=>setTimeout(
        ()=>resolve({postData:'{"fallback":'+JSON.stringify(p.requestId)+'}'}),35));
      if(mode==='lateCustom')return new Promise(resolve=>setTimeout(
        ()=>resolve({postData:data}),35));
      if(mode==='lateAfterGuard'||mode==='rejectAfterGuard')
        return new Promise((resolve,reject)=>setTimeout(()=>{
          const rejected=mode==='rejectAfterGuard';
          options.postDataSettled?.(p.requestId,rejected?'rejected':'resolved');
          rejected?reject(Error('POST_DATA_TOO_LATE')):resolve({postData:data??'{"too_late":true}'});
        },delay));
      if(mode==='reject')return Promise.reject(Error('POST_DATA_UNAVAILABLE'));
      if(mode==='hang')return new Promise(()=>{});
      return normalSend(cmd,p);
    };
  }
  return capture({ws:'ws://127.0.0.1:9333/fake',expectedChatOrigin:options.expectedChatOrigin??'http://localhost',makeSession:async()=>c,timeoutMs:2000,quiescenceMs:options.quiescenceMs??80,
    responseBodyAckTimeoutMs:options.responseBodyAckTimeoutMs??750,
    requestPostDataAckTimeoutMs:options.requestPostDataAckTimeoutMs??750,
    bodyAckClock:options.bodyAckClock??(()=>performance.now()),onReady:async()=>{
  setTimeout(async()=>{for(let i=0;i<2;i++){
    const requestId=String(i+1),o=i===1?options:{},timestamp=Object.hasOwn(o,'requestTimestamp')?o.requestTimestamp:100+i;
    const chunks=i===1&&chunksForSecondTurn?chunksForSecondTurn.map(b=>Buffer.from(b)):
      [Buffer.from(i===0&&Object.hasOwn(options,'firstBody')?options.firstBody:body)];
    const captured=Buffer.concat(chunks);
    c.bodies.set(requestId,i===1&&responseBodyForSecondTurn!==null?Buffer.from(responseBodyForSecondTurn):captured);
    const requestUrl=i===1&&o.requestUrl?o.requestUrl:'http://localhost/api/nox/chat';
    const frameId=i===1&&Object.hasOwn(o,'requestFrameId')?o.requestFrameId:'fixture-frame';
    const loaderId=i===1&&Object.hasOwn(o,'requestLoaderId')?o.requestLoaderId:'fixture-loader';
    c.emit('Network.requestWillBeSent',{requestId,timestamp,
      ...(i===1&&o.omitDocumentURL?{}:{documentURL:i===1&&Object.hasOwn(o,'documentURL')?o.documentURL:'http://localhost/nox/chat'}),
      ...(i===1&&o.omitInitiator?{}:{initiator:i===1&&Object.hasOwn(o,'initiatorType')?
        {type:o.initiatorType,...(Object.hasOwn(o,'initiatorUrl')?{url:o.initiatorUrl}:{})}:
        {type:options.firstInitiatorType??'script',...(options.firstInitiatorType==='parser'?{url:'http://localhost/nox/chat'}:{})}}),
      ...(i===1&&o.omitRequestFrame?{}:{frameId}),
      ...(i===1&&o.omitRequestLoader?{}:{loaderId}),
      ...(i===1&&o.redirectResponse?{redirectResponse:{status:302,url:'http://foreign.invalid/old'}}:{}),
      ...(i===1&&Object.hasOwn(o,'redirectHasExtraInfo')?{redirectHasExtraInfo:o.redirectHasExtraInfo}:{}),
      request:{method:'POST',url:requestUrl,
      ...((i===1&&o.postDataMode)||(i===0&&options.firstPostDataMode)?{}:
         {postData:i===1&&Object.hasOwn(o,'postDataText')?o.postDataText:'{"secret":"'+i+'"}'})}});
    if(i===1&&typeof options.lifecycleDuringSecond==='function')options.lifecycleDuringSecond(c);
    if(i===1&&options.injectExtraPost)c.emit('Network.requestWillBeSent',{
      requestId:'unexpected-third',timestamp:101.001,request:{method:'POST',
      url:'http://localhost/api/nox/chat',postData:'{"unexpected":3}'}});
    if(i===1&&options.injectDuplicatePost)c.emit('Network.requestWillBeSent',{
      requestId,timestamp:101.001,request:{method:'POST',
      url:'http://localhost/api/nox/chat',postData:'{"duplicate":true}'}});
    const emitExtra=()=>c.emit('Network.responseReceivedExtraInfo',{requestId,statusCode:o.extraStatus??200,headers:o.extraHeaders??{}});
    if(o.extraBefore)emitExtra();
    const response={status:200,mimeType:'text/event-stream',url:i===1&&o.responseUrl?o.responseUrl:requestUrl,headers:i===1&&encoding?{'Content-Encoding':encoding}:{}};
    for(const key of ['fromDiskCache','fromServiceWorker','fromPrefetchCache','fromEarlyHints','cacheStorageCacheName','serviceWorkerResponseSource','serviceWorkerRouterInfo']){
      if(o[key]!==undefined)response[key]=o[key];
    }
    const responseTime=Object.hasOwn(o,'responseTimestamp')?o.responseTimestamp:timestamp+.005;
    const responseEvent={requestId,timestamp:responseTime,response,hasExtraInfo:o.hasExtraInfo===true,
      ...(i===1&&o.omitResponseFrame?{}:{frameId:i===1&&Object.hasOwn(o,'responseFrameId')?o.responseFrameId:frameId}),
      ...(i===1&&o.omitResponseLoader?{}:{loaderId:i===1&&Object.hasOwn(o,'responseLoaderId')?o.responseLoaderId:loaderId})
    };
    if(o.omitHasExtraInfo)delete responseEvent.hasExtraInfo;
    c.emit('Network.responseReceived',responseEvent);
    if(o.extraAfter)emitExtra();
    await new Promise(r=>setImmediate(r));
    if(o.cacheEvent)c.emit('Network.requestServedFromCache',{requestId});
    const dataTime=Object.hasOwn(o,'dataTimestamp')?o.dataTimestamp:timestamp+.01;
    if(missing&&i===1)c.emit('Network.dataReceived',{requestId,timestamp:dataTime});
    else for(const [index,chunk] of chunks.entries()){
      const encoded=chunk.toString('base64');
      const data=i===1&&typeof o.dataBase64Mutator==='function'?o.dataBase64Mutator(encoded,index):encoded;
      c.emit('Network.dataReceived',{requestId,timestamp:Array.isArray(o.chunkTimestamps)?o.chunkTimestamps[index]:dataTime,data});
    }
    if(o.extraBeforeFinish)emitExtra();
    // Inject an actual second CDP POST before the first loadingFinished,
    // independently of the logical request timestamp on the normal second.
    if(i===0&&options.overlapPostBeforeFirstClose)c.emit('Network.requestWillBeSent',{
      requestId:'overlap-second',timestamp:timestamp+.015,
      frameId:'fixture-frame',loaderId:'fixture-loader',
      documentURL:'http://localhost/nox/chat',initiator:{type:'script'},
      request:{method:'POST',url:'http://localhost/api/nox/chat',postData:'{"overlap":true}'}
    });
    if(!((i===0&&options.omitFirstClose)||(i===1&&options.omitSecondClose))){
      const closeFailed=i===0?options.firstLoadingFailed===true:o.loadingFailed===true;
      const closeTimestamp=i===0&&Object.hasOwn(options,'firstCloseTimestamp')?
        options.firstCloseTimestamp:Object.hasOwn(o,'closeTimestamp')?o.closeTimestamp:timestamp+.02;
      c.emit(closeFailed?'Network.loadingFailed':'Network.loadingFinished',
        {requestId,timestamp:closeTimestamp});
    }
    await new Promise(r=>setImmediate(r));
    // Artificial wall-clock delay between browser POSTs: the first CDP
    // metadata guard can seal before the second request even starts.
    if(i===0&&options.delaySecondPostMs)
      await new Promise(r=>setTimeout(r,options.delaySecondPostMs));
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
  assert.equal(admitted.turns[1].response_headers_received_ms,5);
  assert.equal(admitted.turns[1].first_cdp_data_chunk_ms,10);
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


test('response headers and first observed decoded data chunk have distinct monotonic timestamps',async()=>{
  // responseReceived at +5 ms does not prove bytes arrived at +5 ms.
  const delayed=await run(false,[Buffer.from(body)],null,null,{dataTimestamp:101.018});
  assert.equal(delayed.cdp_consistent,true);
  assert.equal(delayed.ttft_sse_verified,true);
  assert.equal(delayed.turns[1].response_headers_received_ms,5);
  assert.equal(delayed.turns[1].first_cdp_data_chunk_ms,18);
  assert.equal(delayed.turns[1].ttft_ms,18);
  assert.equal(delayed.turns[1].sse_done_ms,18);
  assert.equal(Object.hasOwn(delayed.turns[1],'first_network_byte_ms'),false);
  assert.equal(delayed.tcp_wire_verified,false,'CDP decoded chunks are not TCP raw bytes');

  // Empty CDP chunks cannot supply a first payload witness, even if later bytes arrive.
  const empty=await run(false,[Buffer.alloc(0),Buffer.from(body)],null,null,
    {chunkTimestamps:[101.008,101.015]});
  assert.equal(empty.cdp_consistent,false);
  assert.equal(empty.ttft_sse_verified,false);
  assert.equal(empty.turns[1].ttft_ms,null);

  // A payload timestamp before response metadata contradicts the CDP event sequence.
  const reversed=await run(false,[Buffer.from(body)],null,null,{dataTimestamp:101.003});
  assert.equal(reversed.cdp_consistent,false);
  assert.equal(reversed.ttft_sse_verified,false);
});


test('Network.dataReceived requires canonical base64 before counting bytes, TTFT or digest',async()=>{
  // Padded and unpadded canonical pieces still allow a valid stream.
  const ok=await run(false,[Buffer.from(body.slice(0,-1)),Buffer.from(body.slice(-1))]);
  assert.equal(ok.cdp_consistent,true);
  assert.equal(ok.ttft_sse_verified,true);
  const invalid=[
    s=>'!'+s,             // Buffer.from normally ignores invalid prefix
    s=>s+'\n',            // Buffer.from normally ignores whitespace
    s=>s+'=',              // Excess padding
    s=>' '+s,              // Leading whitespace
    s=>s+'??'              // Invalid suffix
  ];
  for(const mutate of invalid){
    const result=await run(false,[Buffer.from(body)],null,null,{dataBase64Mutator:mutate});
    assert.equal(result.cdp_consistent,false,'noncanonical bytes may not match response body');
    assert.equal(result.ttft_sse_verified,false,'noncanonical data cannot certify TTFT');
    assert.equal(result.turns[1].first_cdp_data_chunk_ms,null);
    assert.equal(result.turns[1].ttft_ms,null);
    assert.equal(result.turns[1].visible_text_sha256,null);
  }
  // Nonzero unused padding bits: both Cg== and Ch== permissively decode LF,
  // but only Cg== is canonical and admissible CDP data.
  const padBits=await run(false,[Buffer.from(body.slice(0,-1)),Buffer.from(body.slice(-1))],null,null,
    {dataBase64Mutator:(s,index)=>index===1?'Ch==':s});
  assert.equal(padBits.cdp_consistent,false);
  assert.equal(padBits.ttft_sse_verified,false);
  assert.equal(padBits.turns[1].visible_text_sha256,null);
});


test('Network.getResponseBody rejects noncanonical base64 padding-bit aliases with identical decoded bytes',async()=>{
  const canonical=Buffer.from(body,'utf8').toString('base64');
  assert.match(canonical,/o=$/,'fixture must end in one padded base64 quantum');
  const alias=canonical.replace(/o=$/,'p=');
  assert.notEqual(alias,canonical);
  assert.deepEqual(Buffer.from(alias,'base64'),Buffer.from(canonical,'base64'),
    'permissive Node decoder maps both encodings to the same original body');
  const clean=await run();
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  const poisoned=await run(false,null,null,null,{
    responseBodyBase64Mutator:(data,id)=>id==='2'?alias:data
  });
  assert.equal(poisoned.cdp_consistent,false);
  assert.equal(poisoned.ttft_sse_verified,false);
  assert.equal(poisoned.turns[1].cdp_decoded_body_sha256,null);
  assert.equal(poisoned.turns[1].ttft_ms,null);
  assert.equal(poisoned.turns[1].sse_done_ms,null);
  assert.equal(poisoned.turns[1].visible_text_sha256,null);
});


test('Network.getResponseBody rejects unpaired UTF-16 surrogates before lossy UTF-8 SHA, preserves RU/ES/emoji',async()=>{
  const visible='Привет, mañana 🐈';
  const unicodeWire=body.replace('Hello',visible);
  const ok=await run(false,[Buffer.from(unicodeWire,'utf8')],null,null,{responseBodyTextMutator:s=>s});
  assert.equal(ok.cdp_consistent,true);
  assert.equal(ok.ttft_sse_verified,true);
  assert.equal(ok.turns[1].cdp_decoded_body_matches_stream,true);
  // Buffer.from replaces either lone surrogate with U+FFFD (same bytes as legitimate replacement character).
  for(const bad of ['\uD800','\uDC00']){
    const poisonedWire=body.replace('Hello','\uFFFD');
    const valid=await run(false,[Buffer.from(poisonedWire,'utf8')],null,null,{responseBodyTextMutator:s=>s});
    assert.equal(valid.cdp_consistent,true,'a genuine U+FFFD in decoded text remains legal');
    const poisoned=await run(false,[Buffer.from(poisonedWire,'utf8')],null,null,{
      responseBodyTextMutator:(s,id)=>id==='2'?s.replace('\uFFFD',bad):s
    });
    assert.equal(poisoned.cdp_consistent,false,'lossy text must not witness the bytes');
    assert.equal(poisoned.ttft_sse_verified,false);
    assert.equal(poisoned.turns[1].cdp_decoded_body_sha256,null);
    assert.equal(poisoned.turns[1].ttft_ms,null);
    assert.equal(poisoned.turns[1].sse_done_ms,null);
  }
});

test('direct and delayed CDP POST digests reject lossy UTF-16 while preserving valid RU ES emoji',async()=>{
  const {createHash}=await import('node:crypto');
  const digest=s=>createHash('sha256').update(Buffer.from(s,'utf8')).digest('hex');
  const good='{"message":"Привет, mañana 🐈"}';
  const genuineReplacement='{"message":"\uFFFD"}';
  for(const postDataText of [good,genuineReplacement]){
    for(const mode of ['direct','lateCustom']){
      const opts={postDataText,...(mode==='lateCustom'?{postDataMode:mode}:{})};
      const x=await run(false,null,null,null,opts);
      assert.equal(x.cdp_consistent,true,mode);
      assert.equal(x.ttft_sse_verified,true,mode);
      assert.equal(x.turns[1].request_sha256,digest(postDataText),mode);
      assert.doesNotMatch(JSON.stringify(x),/Привет|mañana|secret/);
    }
  }
  for(const invalidUnit of ['\uD800','\uDC00']){
    const lossy='{"message":"'+invalidUnit+'"}';
    assert.equal(digest(lossy),digest(genuineReplacement),
      'unpaired surrogate hashes to same bytes as genuine replacement under permissive encoding');
    for(const mode of ['direct','lateCustom']){
      const opts={postDataText:lossy,...(mode==='lateCustom'?{postDataMode:mode}:{})};
      const x=await run(false,null,null,null,opts);
      assert.equal(x.cdp_consistent,false,mode);
      assert.equal(x.ttft_sse_verified,false,mode);
      assert.equal(x.turns[1].request_sha256,null,mode);
      assert.equal(x.turns[1].ttft_ms,null,mode);
      assert.equal(x.turns[1].sse_done_ms,null,mode);
    }
  }
});

test('two-turn attribution follows request-start order even when CDP body ACK completes in reverse',async()=>{
  const control=await run();
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.deepEqual(control.turns.map(t=>t.cdp_request_id),['1','2']);
  const reversed=await run(false,null,null,null,{responseBodyDelay:{'1':60}});
  assert.equal(reversed.cdp_consistent,true);
  assert.equal(reversed.ttft_sse_verified,true);
  assert.deepEqual(reversed.turns.map(t=>t.cdp_request_id),['1','2'],
    'async getResponseBody completion order cannot swap first and second conversational turn');
  assert.deepEqual(reversed.turns.map(t=>t.request_sha256),
    control.turns.map(t=>t.request_sha256));
  assert.deepEqual(reversed.turns.map(t=>t.ttft_ms),control.turns.map(t=>t.ttft_ms));
  await assert.rejects(run(false,null,null,null,{injectExtraPost:true}),/EXTRA_CDP_POST/,
    'any observed unexpected third model POST must invalidate a two-turn measurement');
  await assert.rejects(run(false,null,null,null,{injectDuplicatePost:true}),/DUPLICATE_CDP_ID/,
    'a repeated CDP request ID must fail closed');
});


test('post-body quiescence rejects third POST or CDP disconnect while preserving clean two-turn timing',async()=>{
  const control=await run(false,null,null,null,{quiescenceMs:85});
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.deepEqual(control.turns.map(t=>t.cdp_request_id),['1','2']);
  const latePost=c=>c.emit('Network.requestWillBeSent',{
    requestId:'third-after-second-body-ack',timestamp:103,
    request:{method:'POST',url:'http://localhost/api/nox/chat',postData:'{"unexpected":3}'}
  });
  await assert.rejects(run(false,null,null,null,{quiescenceMs:85,postAckEvent:latePost}),/EXTRA_CDP_POST/);
  await assert.rejects(run(false,null,null,null,{
    quiescenceMs:85,postAckEvent:c=>c.emit('CDP_DISCONNECTED',{})
  }),/CDP_DISCONNECTED/);
});


test('CDP binds chat POSTs to expected serving origin and fails closed on redirects',async()=>{
  const clean=await run();
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  for(const wrongOrigin of ['http://foreign.invalid/api/nox/chat','https://localhost/api/nox/chat']){
    await assert.rejects(run(false,null,null,null,{requestUrl:wrongOrigin}),/CHAT_POST_ORIGIN_MISMATCH/);
  }
  await assert.rejects(run(false,null,null,null,{redirectResponse:true}),/CDP_CHAT_REDIRECT/);
  await assert.rejects(run(false,null,null,null,{redirectHasExtraInfo:false}),/CDP_CHAT_REDIRECT/);
  const responseMismatch=await run(false,null,null,null,{responseUrl:'http://foreign.invalid/api/nox/chat'});
  assert.equal(responseMismatch.cdp_consistent,false);
  assert.equal(responseMismatch.ttft_sse_verified,false);
  const wrongExpectation=await assert.rejects(run(false,null,null,null,{expectedChatOrigin:'https://localhost'}),/CHAT_POST_ORIGIN_MISMATCH/);
});

test('two-turn CDP witness binds one page target, frame and document loader, not unrelated tab/iframe',async()=>{
  const control=await run();
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.deepEqual(control.turns.map(t=>t.cdp_request_id),['1','2']);
  for(const flags of [
    {requestFrameId:'unrelated-iframe'}, {requestLoaderId:'new-document'},
    {requestFrameId:''}, {requestLoaderId:''},
    {omitRequestFrame:true}, {omitRequestLoader:true}
  ]){
    await assert.rejects(run(false,null,null,null,flags),
      /CDP_DIALOG_FRAME_MISMATCH|CDP_MAIN_FRAME_DOCUMENT_CHANGED|CDP_FRAME_PROVENANCE_MISSING/,JSON.stringify(flags));
  }
  for(const flags of [
    {responseFrameId:'unrelated-iframe'}, {responseLoaderId:'other-document'},
    {omitResponseFrame:true}, {omitResponseLoader:true}
  ]){
    const mismatched=await run(false,null,null,null,flags);
    assert.equal(mismatched.cdp_consistent,false,JSON.stringify(flags));
    assert.equal(mismatched.ttft_sse_verified,false,JSON.stringify(flags));
    assert.equal(mismatched.turns[1].ttft_ms,null,JSON.stringify(flags));
  }
  await assert.rejects(run(false,null,null,null,{targetType:'service_worker'}),/CDP_PAGE_TARGET_REQUIRED/);
});


test('CDP independently pins page documentURL and rejects cross-document or ambiguous initiator',async()=>{
  const control=await run();
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.deepEqual(control.turns.map(t=>t.cdp_request_id),['1','2']);
  // Hash-only navigation is the same document; external scripts can be the
  // request initiator without needing an identical bundle URL/stack.
  const hashOnly=await run(false,null,null,null,{documentURL:'http://localhost/nox/chat#chat'});
  assert.equal(hashOnly.ttft_sse_verified,true);
  for(const flags of [
    {omitDocumentURL:true},
    {documentURL:''},
    {documentURL:'http://foreign.invalid/nox/chat'},
    {documentURL:'http://localhost/nox/other'},
    {documentURL:'http://localhost/nox/chat?foreign=1'},
    {documentURL:'file:///nox/chat'}
  ]){
    await assert.rejects(run(false,null,null,null,flags),
      /CDP_DOCUMENT_URL_MISSING|CDP_DOCUMENT_URL_MISMATCH/,JSON.stringify(flags));
  }
  await assert.rejects(run(false,null,null,null,{targetUrl:'about:blank'}),/CDP_PAGE_DOCUMENT_REQUIRED/);
  await assert.rejects(run(false,null,null,null,{targetUrl:'http://foreign.invalid/nox/chat'}),/CDP_DOCUMENT_URL_MISMATCH/);
  for(const flags of [
    {omitInitiator:true},
    {initiatorType:'other'},
    {initiatorType:'preflight'},
    {initiatorType:'parser',initiatorUrl:'http://foreign.invalid/nox/chat'},
    {initiatorType:'parser',initiatorUrl:'http://localhost/nox/chat'}
  ]){
    await assert.rejects(run(false,null,null,null,flags),
      /CDP_INITIATOR_AMBIGUOUS|CDP_PARSER_ORIGIN_MISMATCH|CDP_INITIATOR_TYPE_CHANGED/,
      JSON.stringify(flags));
  }
  const validParser=await run(false,null,null,null,{
    firstInitiatorType:'parser',initiatorType:'parser',initiatorUrl:'http://localhost/nox/chat'
  });
  assert.equal(validParser.cdp_consistent,true);
  assert.equal(validParser.ttft_sse_verified,true);
});

test('main-frame navigation/reload, detached target and document replacement fence both turns through quiescence',async()=>{
  const control=await run(false,null,null,null,{quiescenceMs:85});
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.deepEqual(control.turns.map(t=>t.cdp_request_id),['1','2']);
  // Navigation within the *same* document (hash/SPA) is not a reload.
  const hashChange=await run(false,null,null,null,{
    lifecycleDuringSecond:c=>c.emit('Page.navigatedWithinDocument',{
      frameId:'fixture-frame',url:'http://localhost/nox/chat#after-first-turn'
    })
  });
  assert.equal(hashChange.ttft_sse_verified,true);
  const subframe=await run(false,null,null,null,{
    lifecycleDuringSecond:c=>{
      c.emit('Page.frameNavigated',{frame:{id:'iframe',parentId:'fixture-frame',url:'http://localhost/embed'}});
      c.emit('Page.frameDetached',{frameId:'iframe'});
    }
  });
  assert.equal(subframe.ttft_sse_verified,true);
  const bad=[
    ['Page.frameStartedNavigating',{frameId:'fixture-frame',navigationType:'reload'},/CDP_MAIN_FRAME_NAVIGATION_STARTED/],
    ['Page.frameNavigated',{frame:{id:'fixture-frame',loaderId:'new-loader',url:'http://localhost/nox/chat'}},/CDP_MAIN_FRAME_NAVIGATED/],
    ['Page.frameDetached',{frameId:'fixture-frame'},/CDP_MAIN_FRAME_DETACHED/],
    ['Page.navigatedWithinDocument',{frameId:'fixture-frame',url:'http://localhost/other'},/CDP_SAME_DOCUMENT_URL_CHANGED/],
    ['Target.targetDestroyed',{targetId:'fixture-page'},/CDP_PAGE_TARGET_DESTROYED/],
    ['Target.targetCrashed',{targetId:'fixture-page'},/CDP_PAGE_TARGET_CRASHED/],
    ['Target.detachedFromTarget',{targetId:'fixture-page'},/CDP_PAGE_TARGET_DETACHED/],
    ['Inspector.detached',{reason:'target_closed'},/CDP_INSPECTOR_DETACHED/]
  ];
  for(const [method,p,expected] of bad){
    await assert.rejects(run(false,null,null,null,{
      lifecycleDuringSecond:c=>c.emit(method,p)
    }),expected,'active stream invalidated: '+method);
    await assert.rejects(run(false,null,null,null,{
      quiescenceMs:85,postAckEvent:c=>c.emit(method,p)
    }),expected,'post-body quiet window invalidated: '+method);
  }
});

test('post-quiescence document snapshot catches silent frame/loader/target replacement',async()=>{
  const good=await run(false,null,null,null,{quiescenceMs:85});
  assert.equal(good.cdp_consistent,true);
  assert.equal(good.ttft_sse_verified,true);
  assert.deepEqual(good.turns.map(x=>x.ttft_ms),[10,10]);
  const fragment=await run(false,null,null,null,{quiescenceMs:85,
    postAckEvent:c=>{
      c.fixtureFrameUrl='http://localhost/nox/chat#new-fragment';
      c.targetUrl='http://localhost/nox/chat#new-fragment';
    }
  });
  assert.equal(fragment.ttft_sse_verified,true);
  const poisoned=[
    [c=>{c.fixtureFrameId='silently-new-frame';},/CDP_FINAL_MAIN_FRAME_CHANGED/],
    [c=>{c.fixtureLoaderId='silently-reloaded';},/CDP_FINAL_MAIN_FRAME_CHANGED/],
    [c=>{c.fixtureTargetId='other-tab';},/CDP_FINAL_PAGE_TARGET_CHANGED/],
    [c=>{c.targetType='service_worker';},/CDP_FINAL_PAGE_TARGET_CHANGED/],
    [c=>{c.fixtureFrameUrl='http://localhost/nox/other';},/CDP_FINAL_PAGE_DOCUMENT_CHANGED/],
    [c=>{c.targetUrl='http://foreign.invalid/nox/chat';},/CDP_FINAL_PAGE_DOCUMENT_CHANGED/],
    [c=>{c.dropFinalFrame=true;},/CDP_FINAL_MAIN_FRAME_CHANGED/],
    [c=>{c.rejectFinalSnapshot=true;},/CDP_FINAL_SNAPSHOT_UNAVAILABLE/]
  ];
  for(const [change,expected] of poisoned){
    await assert.rejects(run(false,null,null,null,{
      quiescenceMs:85,postAckEvent:change
    }),expected,'silent post-body change must not certify two turns');
  }
});

test('multi-turn causal boundary rejects overlapping POSTs, missing terminal and ambiguous ordering',async()=>{
  // The same model POSTs, CDP stream hashes and response bodies can be valid
  // individually while the purported turns overlap; they are not a dialogue.
  const serial=await run(false,null,null,null,{requestTimestamp:100.0201});
  assert.equal(serial.cdp_consistent,true);
  assert.equal(serial.ttft_sse_verified,true);
  assert.deepEqual(serial.turns.map(x=>x.ttft_ms),[10,10]);
  for(const requestTimestamp of [100.019,100.02]){
    await assert.rejects(run(false,null,null,null,{requestTimestamp}),
      /CDP_NON_SERIAL_CHAT_POST/,'second request must start strictly after first close');
  }
  await assert.rejects(run(false,null,null,null,{overlapPostBeforeFirstClose:true}),
    /CDP_NON_SERIAL_CHAT_POST/,'second POST seen before first loadingFinished must fail');
  await assert.rejects(run(false,null,null,null,{omitFirstClose:true}),
    /CDP_NON_SERIAL_CHAT_POST/,'unknown first loadingFinished must not certify a second turn');
  const missingDone=body.replace('data: [DONE]\n\n','');
  await assert.rejects(run(false,null,null,null,{firstBody:missingDone}),
    /CDP_NON_SERIAL_CHAT_POST/,'stop without explicit terminal [DONE] is not a completed first turn');
  // Malformed clock evidence remains a HOLD rather than a fake PASS.
  const malformed=await run(false,null,null,null,{requestTimestamp:NaN});
  assert.equal(malformed.cdp_consistent,false);
  assert.equal(malformed.ttft_sse_verified,false);
});

test('decoded SSE output cadence counts codepoints and event gaps, never invented tokens or lossy Unicode',async()=>{
  const printable='Привет 🐈';
  const tail='! За';
  const partA='data: '+JSON.stringify({choices:[{delta:{content:printable}}]})+'\n\n';
  const partB='data: '+JSON.stringify({choices:[{delta:{content:tail}}]})+'\n\n'+
    'data: '+JSON.stringify({choices:[{delta:{},finish_reason:'stop'}]})+'\n\n'+
    'data: [DONE]\n\n';
  const result=await run(false,[Buffer.from(partA),Buffer.from(partB)],null,null,{
    chunkTimestamps:[101.01,101.016]
  });
  assert.equal(result.cdp_consistent,true);
  assert.equal(result.ttft_sse_verified,true);
  const second=result.turns[1];
  const codepoints=[...printable,...tail].length;
  assert.equal(second.sse_text_event_count,2);
  assert.equal(second.sse_output_codepoints,codepoints);
  assert.equal(second.sse_text_event_gap_p95_ms,6);
  assert.equal(second.sse_output_window_ms,6);
  assert.equal(second.sse_codepoints_per_second,Math.round(codepoints*10000/6)/10);
  assert.equal(result.turns[0].sse_text_event_gap_p95_ms,null);
  assert.doesNotMatch(JSON.stringify(result),/Привет|🐈|secret/);
  // Escaped JSON allows a lone surrogate. It must not silently hash or count U+FFFD.
  const broken='data: '+JSON.stringify({choices:[{delta:{content:String.fromCharCode(0xD800)}}]})+'\n\n'+
    'data: '+JSON.stringify({choices:[{delta:{},finish_reason:'stop'}]})+'\n\n'+
    'data: [DONE]\n\n';
  const rejected=await run(false,[Buffer.from(broken)]);
  assert.equal(rejected.cdp_consistent,false);
  assert.equal(rejected.ttft_sse_verified,false);
  assert.equal(rejected.turns[1].sse_output_codepoints,null);
  assert.equal(rejected.turns[1].sse_text_event_gap_p95_ms,null);
  assert.equal(rejected.turns[1].sse_codepoints_per_second,null);
});

test('largest nonempty SSE event gap witnesses true CDP stall separately from coalesced burst',async()=>{
  const delta=text=>'data: '+JSON.stringify({choices:[{delta:{content:text}}]})+'\n\n';
  const terminal='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n';
  // Same CDP chunk: two visible deltas, no observed interval between them.
  const burst=await run(false,[Buffer.from(delta('A')+delta('B')+terminal)]);
  assert.equal(burst.ttft_sse_verified,true);
  assert.equal(burst.turns[1].sse_text_event_max_gap_ms,0);
  assert.equal(burst.turns[1].sse_text_event_max_gap_after_event,1);
  assert.equal(burst.turns[1].sse_text_event_max_gap_cross_chunk,false);
  assert.equal(burst.turns[1].sse_text_event_same_chunk_pairs,1);
  assert.equal(burst.turns[1].sse_text_event_cross_chunk_pairs,0);
  assert.equal(burst.turns[1].sse_text_event_max_gap_from_ms,10);
  assert.equal(burst.turns[1].sse_text_event_max_gap_to_ms,10);
  // Independent chunks: a 235 ms observed interarrival gap after event #2.
  const stall=await run(false,[Buffer.from(delta('A')),Buffer.from(delta('B')),
    Buffer.from(delta('C')+terminal)],null,null,{
      chunkTimestamps:[101.010,101.015,101.250],closeTimestamp:101.270
    });
  assert.equal(stall.cdp_consistent,true);
  assert.equal(stall.ttft_sse_verified,true);
  assert.equal(stall.turns[1].sse_text_event_count,3);
  assert.equal(stall.turns[1].sse_text_event_max_gap_ms,235);
  assert.equal(stall.turns[1].sse_text_event_max_gap_after_event,2);
  assert.equal(stall.turns[1].sse_text_event_max_gap_from_ms,15);
  assert.equal(stall.turns[1].sse_text_event_max_gap_to_ms,250);
  assert.equal(stall.turns[1].sse_text_event_max_gap_cross_chunk,true);
  assert.equal(stall.turns[1].sse_text_event_same_chunk_pairs,0);
  assert.equal(stall.turns[1].sse_text_event_cross_chunk_pairs,2);
  assert.equal(stall.turns[1].sse_text_event_gap_p95_ms,235);
  assert.equal(stall.turns[0].sse_text_event_max_gap_ms,null);
  // Out-of-order CDP chunk timestamps cannot be reinterpreted as zero latency.
  const reversed=await run(false,[Buffer.from(delta('A')),Buffer.from(delta('B')+terminal)],null,null,{
    chunkTimestamps:[101.250,101.010],closeTimestamp:101.270
  });
  assert.equal(reversed.cdp_consistent,false);
  assert.equal(reversed.ttft_sse_verified,false);
  assert.equal(reversed.turns[1].sse_text_event_max_gap_ms,null);
  assert.equal(reversed.turns[1].sse_text_event_cross_chunk_pairs,null);
  assert.doesNotMatch(JSON.stringify(stall),/secret|data:/);
});

test('SSE tail-to-stop and tail-to-DONE witness separates delayed terminal chunks and empty text',async()=>{
  const delta=s=>'data: '+JSON.stringify({choices:[{delta:{content:s}}]})+'\n\n';
  const finish='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n';
  const done='data: [DONE]\n\n';
  const same=await run(false,[Buffer.from(delta('A')+finish+done)]);
  assert.equal(same.ttft_sse_verified,true);
  assert.equal(same.turns[1].sse_first_text_event_ms,10);
  assert.equal(same.turns[1].sse_last_text_event_ms,10);
  assert.equal(same.turns[1].sse_last_text_to_finish_stop_ms,0);
  assert.equal(same.turns[1].sse_last_text_to_done_ms,0);
  assert.equal(same.turns[1].sse_last_text_to_done_cross_chunk,false);
  assert.equal(same.turns[1].sse_finish_stop_to_done_ms,0);
  assert.equal(same.turns[1].sse_finish_stop_to_done_cross_chunk,false);

  const delayed=await run(false,[Buffer.from(delta('A')),Buffer.from(finish),Buffer.from(done)],null,null,{
    chunkTimestamps:[101.010,101.020,101.250],closeTimestamp:101.270
  });
  assert.equal(delayed.cdp_consistent,true);
  assert.equal(delayed.ttft_sse_verified,true);
  const tail=delayed.turns[1];
  assert.equal(tail.sse_first_text_event_ms,10);
  assert.equal(tail.sse_last_text_event_ms,10);
  assert.equal(tail.sse_last_text_to_finish_stop_ms,10);
  assert.equal(tail.sse_last_text_to_done_ms,240);
  assert.equal(tail.sse_last_text_to_done_cross_chunk,true);
  assert.equal(tail.sse_finish_stop_to_done_ms,230);
  assert.equal(tail.sse_finish_stop_to_done_cross_chunk,true);
  assert.equal(delayed.turns[0].sse_last_text_to_done_ms,0);

  const noText=await run(false,[Buffer.from(finish+done)]);
  assert.equal(noText.cdp_consistent,true);
  assert.equal(noText.ttft_sse_verified,false,'no text event cannot prove TTFT');
  for(const key of ['sse_first_text_event_ms','sse_last_text_event_ms',
    'sse_last_text_to_finish_stop_ms','sse_last_text_to_done_ms',
    'sse_last_text_to_done_cross_chunk','sse_finish_stop_to_done_ms',
    'sse_finish_stop_to_done_cross_chunk'])assert.equal(noText.turns[1][key],null,key);

  const badClock=await run(false,[Buffer.from(delta('A')),Buffer.from(finish),Buffer.from(done)],null,null,{
    chunkTimestamps:[101.250,101.010,101.015],closeTimestamp:101.270
  });
  assert.equal(badClock.cdp_consistent,false);
  assert.equal(badClock.ttft_sse_verified,false);
  assert.equal(badClock.turns[1].sse_last_text_to_done_ms,null);
  assert.equal(badClock.turns[1].sse_last_text_to_done_cross_chunk,null);
  assert.doesNotMatch(JSON.stringify(delayed),/secret|data:/);
});

test('SSE DONE to CDP loadingFinished measures network-tail, not TCP close',async()=>{
  const delta='data: {"choices":[{"delta":{"content":"A"}}]}\n\n';
  const finish='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n';
  const done='data: [DONE]\n\n';
  const delayed=await run(false,[Buffer.from(delta),Buffer.from(finish),Buffer.from(done)],null,null,{
    chunkTimestamps:[101.010,101.020,101.250],closeTimestamp:101.280
  });
  assert.equal(delayed.cdp_consistent,true);
  assert.equal(delayed.ttft_sse_verified,true);
  assert.equal(delayed.turns[1].sse_done_to_loading_finished_ms,30);
  assert.equal(delayed.turns[1].sse_done_to_loading_finished_source,'CDP:Network.loadingFinished');
  assert.equal(delayed.turns[0].sse_done_to_loading_finished_ms,10);
  // Distinct from last-visible-text gap: even a textless SSE can have terminal-to-close.
  const textless=await run(false,[Buffer.from(finish+done)],null,null,{
    chunkTimestamps:[101.250],closeTimestamp:101.280
  });
  assert.equal(textless.cdp_consistent,true);
  assert.equal(textless.ttft_sse_verified,false);
  assert.equal(textless.turns[1].sse_last_text_to_done_ms,null);
  assert.equal(textless.turns[1].sse_done_to_loading_finished_ms,30);
  const incomplete=await run(false,[Buffer.from(delta+finish)]);
  assert.equal(incomplete.cdp_consistent,true,'decoded body can be internally consistent without final SSE');
  assert.equal(incomplete.ttft_sse_verified,false,'missing [DONE] is not complete');
  assert.equal(incomplete.turns[1].sse_done_to_loading_finished_ms,null);
  assert.equal(incomplete.turns[1].sse_done_to_loading_finished_source,null);
  const failed=await run(false,[Buffer.from(delta+finish+done)],null,null,{loadingFailed:true});
  assert.equal(failed.cdp_consistent,false);
  assert.equal(failed.turns[1].sse_done_to_loading_finished_ms,null);
  const reversed=await run(false,[Buffer.from(delta+finish+done)],null,null,{closeTimestamp:101.005});
  assert.equal(reversed.cdp_consistent,false);
  assert.equal(reversed.ttft_sse_verified,false);
  assert.equal(reversed.turns[1].sse_done_to_loading_finished_ms,null);
  assert.equal(reversed.turns[1].sse_done_to_loading_finished_source,null);
  assert.doesNotMatch(JSON.stringify(delayed),/secret|data:/);
});

test('getResponseBody ACK latency is bounded observer-only monotonic time, never model TTFT',async()=>{
  const control=await run();
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.equal(control.turns[1].sse_done_ms,10);
  assert.equal(control.turns[1].cdp_response_body_ack_latency_source,
    'LOCAL_MONOTONIC:Network.getResponseBody');
  const delayed=await run(false,null,null,null,{responseBodyDelay:{'2':65}});
  assert.equal(delayed.cdp_consistent,true);
  assert.equal(delayed.ttft_sse_verified,true);
  assert.equal(delayed.turns[1].ttft_ms,control.turns[1].ttft_ms);
  assert.equal(delayed.turns[1].sse_done_ms,control.turns[1].sse_done_ms);
  assert.ok(delayed.turns[1].cdp_response_body_ack_latency_ms>=45);
  assert.ok(delayed.turns[1].cdp_response_body_ack_latency_ms<=750);
  assert.ok(delayed.turns[1].cdp_response_body_ack_latency_ms>
    delayed.turns[0].cdp_response_body_ack_latency_ms);
  for(const options of [
    {responseBodyReject:['2']},
    {responseBodyHang:['2'],responseBodyAckTimeoutMs:45},
    {responseBodyDelay:{'2':100},responseBodyAckTimeoutMs:45}
  ]){
    const failed=await run(false,null,null,null,options);
    assert.equal(failed.cdp_consistent,false,JSON.stringify(Object.keys(options)));
    assert.equal(failed.ttft_sse_verified,false);
    assert.equal(failed.turns[1].cdp_response_body_ack_latency_ms,null);
    assert.equal(failed.turns[1].cdp_response_body_ack_latency_source,null);
    assert.equal(failed.turns[1].ttft_ms,null);
    assert.equal(failed.turns[1].sse_done_ms,null);
  }
  // If the FIRST turn's ACK clock is invalid, the second POST must be
  // rejected outright, because causal two-turn certification cannot proceed.
  for(const badClock of [
    ()=>NaN,
    (()=>{let t=100;return ()=>--t;})()
  ]){
    await assert.rejects(run(false,null,null,null,{bodyAckClock:badClock}),
      /CDP_NON_SERIAL_CHAT_POST/);
  }
  assert.doesNotMatch(JSON.stringify(delayed),/secret|Hello/);
});

test('pending first-turn response-body ACK stays isolated from second SSE and request ID',async()=>{
  const baseline=await run();
  const delayed=await run(false,null,null,null,{responseBodyDelay:{'1':110}});
  assert.equal(delayed.cdp_consistent,true);
  assert.equal(delayed.ttft_sse_verified,true);
  assert.deepEqual(delayed.turns.map(t=>t.cdp_request_id),['1','2']);
  assert.deepEqual(delayed.turns.map(t=>t.request_sha256),baseline.turns.map(t=>t.request_sha256));
  assert.equal(delayed.turns[0].cdp_previous_turn_body_ack_pending_at_post_start,null);
  assert.equal(delayed.turns[1].cdp_previous_turn_body_ack_pending_at_post_start,true);
  assert.equal(baseline.turns[1].cdp_previous_turn_body_ack_pending_at_post_start,false);
  assert.equal(delayed.turns[1].ttft_ms,baseline.turns[1].ttft_ms);
  assert.equal(delayed.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms);
  assert.equal(delayed.turns[1].cdp_decoded_body_sha256,baseline.turns[1].cdp_decoded_body_sha256);
  assert.ok(delayed.turns[0].cdp_response_body_ack_latency_ms>=75);
  assert.ok(delayed.turns[1].cdp_response_body_ack_latency_ms<
    delayed.turns[0].cdp_response_body_ack_latency_ms);
  // A first-turn ACK that never arrives cannot certify the two-turn capture,
  // even though the second SSE itself remained independently observed.
  const stalled=await run(false,null,null,null,{
    responseBodyHang:['1'],responseBodyAckTimeoutMs:45
  });
  assert.equal(stalled.cdp_consistent,false);
  assert.equal(stalled.ttft_sse_verified,false);
  assert.equal(stalled.turns[0].cdp_response_body_ack_latency_ms,null);
  assert.equal(stalled.turns[1].cdp_previous_turn_body_ack_pending_at_post_start,true);
  assert.equal(stalled.turns[1].cdp_request_id,'2');
  assert.equal(stalled.turns[1].ttft_ms,baseline.turns[1].ttft_ms);
  assert.equal(stalled.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms);
  // Rejection before turn 2 is observed must not be silently reclassified
  // as a valid pair with only the first ACK missing.
  await assert.rejects(run(false,null,null,null,{responseBodyReject:['1']}),
    /CDP_NON_SERIAL_CHAT_POST/);
  assert.doesNotMatch(JSON.stringify(delayed),/secret|Hello|data:/);
});

test('post-timeout first body lookup late resolve/reject cannot alter final two-turn witness',async()=>{
  const baseline=await run();
  for(const rejectAfterDelay of [false,true]){
    let ackSettled;
    const lateAck=new Promise(resolve=>{ackSettled=resolve;});
    const result=await run(false,null,null,null,{
      responseBodyAckTimeoutMs:40,
      responseBodyDelay:{'1':300},
      responseBodyRejectAfterDelay:rejectAfterDelay?['1']:[],
      responseBodySettled:(id,outcome)=>{if(id==='1')ackSettled(outcome);}
    });
    // A complete second SSE is not equivalent to a verified two-turn capture
    // when the first turn's body witness has already timed out.
    assert.equal(result.cdp_consistent,false);
    assert.equal(result.ttft_sse_verified,false);
    assert.deepEqual(result.turns.map(t=>t.cdp_request_id),['1','2']);
    assert.equal(result.turns[0].cdp_response_body_ack_latency_ms,null);
    assert.equal(result.turns[1].cdp_previous_turn_body_ack_pending_at_post_start,true);
    assert.equal(result.turns[1].ttft_ms,baseline.turns[1].ttft_ms);
    assert.equal(result.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms);
    assert.equal(result.turns[1].request_sha256,baseline.turns[1].request_sha256);
    assert.equal(result.turns[1].cdp_decoded_body_sha256,
      baseline.turns[1].cdp_decoded_body_sha256);
    const beforeLate=JSON.stringify(result);
    assert.equal(await lateAck,rejectAfterDelay?'rejected':'resolved');
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(JSON.stringify(result),beforeLate,'stale ACK cannot rewrite finalized digest or timing');
    assert.doesNotMatch(beforeLate,/secret|Hello|data:/);
  }
});


test('getRequestPostData late resolve or reject stays sealed after guard, quiet window and browser snapshot',async()=>{
  const clean=await run(false,null,null,null,{postDataMode:'lateCustom',
    postDataText:'{"message":"настоящий ответ 🐈"}',requestPostDataAckTimeoutMs:80});
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  assert.match(clean.turns[1].request_sha256,/^[a-f0-9]{64}$/);
  for(const mode of ['lateAfterGuard','rejectAfterGuard']){
    let settle;
    const late=new Promise(resolve=>{settle=resolve;});
    const observed=await run(false,null,null,null,{
      postDataMode:mode,postDataText:'{"message":"too late"}',
      requestPostDataAckTimeoutMs:40,postDataDelayMs:280,
      postDataSettled:(id,status)=>{if(id==='2')settle(status);}
    });
    assert.equal(observed.cdp_consistent,false,mode);
    assert.equal(observed.ttft_sse_verified,false,mode);
    assert.equal(observed.turns[0].request_sha256,clean.turns[0].request_sha256);
    assert.equal(observed.turns[1].request_sha256,null,mode);
    assert.equal(observed.turns[1].ttft_ms,null,mode);
    assert.equal(observed.turns[1].visible_text_sha256,null,mode);
    const frozen=JSON.stringify(observed);
    assert.equal(await late,mode==='rejectAfterGuard'?'rejected':'resolved');
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(JSON.stringify(observed),frozen,'late metadata cannot mutate released witness');
  }
  const hung=await run(false,null,null,null,{
    postDataMode:'hang',requestPostDataAckTimeoutMs:40
  });
  assert.equal(hung.cdp_consistent,false);
  assert.equal(hung.ttft_sse_verified,false);
  assert.equal(hung.turns[1].request_sha256,null);
});

test('unresolved first POST-data ACK cannot rebind a serial second-turn SSE request',async()=>{
  const baseline=await run();
  const early=await run(false,null,null,null,{
    firstPostDataMode:'lateCustom',firstPostDataText:'{"first":"verified"}',
    requestPostDataAckTimeoutMs:90
  });
  assert.equal(early.cdp_consistent,true);
  assert.equal(early.ttft_sse_verified,true);
  assert.notEqual(early.turns[0].request_sha256,baseline.turns[0].request_sha256);
  assert.equal(early.turns[1].request_sha256,baseline.turns[1].request_sha256);
  assert.equal(early.turns[1].ttft_ms,baseline.turns[1].ttft_ms);
  assert.equal(early.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms);
  for(const mode of ['lateAfterGuard','rejectAfterGuard','hang']){
    let didSettle;
    const settled=new Promise(resolve=>{didSettle=resolve;});
    const observation=await run(false,null,null,null,{
      firstPostDataMode:mode,firstPostDataText:'{"first":"too late"}',
      firstPostDataDelayMs:260,requestPostDataAckTimeoutMs:40,
      postDataSettled:(id,outcome)=>{if(id==='1')didSettle(outcome);}
    });
    assert.equal(observation.cdp_consistent,false,mode);
    assert.equal(observation.ttft_sse_verified,false,mode);
    assert.deepEqual(observation.turns.map(t=>t.cdp_request_id),['1','2'],mode);
    assert.equal(observation.turns[0].request_sha256,null,mode);
    assert.equal(observation.turns[0].ttft_ms,null,mode);
    // The independent second-turn observation remains attributable, but it
    // cannot certify a valid two-turn exchange with missing first provenance.
    assert.equal(observation.turns[1].request_sha256,baseline.turns[1].request_sha256,mode);
    assert.equal(observation.turns[1].cdp_decoded_body_sha256,
      baseline.turns[1].cdp_decoded_body_sha256,mode);
    assert.equal(observation.turns[1].ttft_ms,baseline.turns[1].ttft_ms,mode);
    assert.equal(observation.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms,mode);
    const sealed=JSON.stringify(observation);
    if(mode!=='hang'){
      assert.equal(await settled,mode==='rejectAfterGuard'?'rejected':'resolved');
      await new Promise(resolve=>setImmediate(resolve));
      assert.equal(JSON.stringify(observation),sealed,'stale first-turn POST ACK is sealed');
    }
    assert.doesNotMatch(sealed,/secret|Hello|data:/);
  }
});

test('expired first POST metadata guard precedes second POST without hiding valid second SSE evidence',async()=>{
  const baseline=await run();
  assert.equal(baseline.cdp_consistent,true);
  for(const mode of ['lateAfterGuard','rejectAfterGuard','hang']){
    let didSettle;
    const settled=new Promise(resolve=>{didSettle=resolve;});
    // First guard expires in 40 ms; only after a 90 ms browser inter-turn
    // delay does a causally serial second POST begin. No source module stubs.
    const observed=await run(false,null,null,null,{
      firstPostDataMode:mode,firstPostDataText:'{"secret":"late first request"}',
      firstPostDataDelayMs:300,requestPostDataAckTimeoutMs:40,
      delaySecondPostMs:90,
      postDataSettled:(id,outcome)=>{if(id==='1')didSettle(outcome);}
    });
    assert.equal(observed.cdp_consistent,false,mode);
    assert.equal(observed.ttft_sse_verified,false,mode);
    assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2'],mode);
    assert.equal(observed.turns[0].request_sha256,null,mode);
    assert.equal(observed.turns[0].ttft_ms,null,mode);
    assert.equal(observed.turns[1].request_sha256,baseline.turns[1].request_sha256,mode);
    assert.equal(observed.turns[1].cdp_decoded_body_sha256,
      baseline.turns[1].cdp_decoded_body_sha256,mode);
    assert.equal(observed.turns[1].visible_text_sha256,
      baseline.turns[1].visible_text_sha256,mode);
    assert.equal(observed.turns[1].ttft_ms,baseline.turns[1].ttft_ms,mode);
    assert.equal(observed.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms,mode);
    assert.equal(observed.turns[1].sse_done_to_loading_finished_ms,
      baseline.turns[1].sse_done_to_loading_finished_ms,mode);
    const frozen=JSON.stringify(observed);
    if(mode!=='hang'){
      assert.equal(await settled,mode==='rejectAfterGuard'?'rejected':'resolved');
      await new Promise(resolve=>setImmediate(resolve));
      assert.equal(JSON.stringify(observed),frozen,'expired first ACK cannot mutate second');
    }
    assert.doesNotMatch(frozen,/secret|Hello|data:/,'only digests and timings may escape');
  }
  // Moving a legitimate second request later must not excuse a separate
  // overlap that appeared before the first response finished.
  await assert.rejects(run(false,null,null,null,{
    firstPostDataMode:'hang',requestPostDataAckTimeoutMs:40,
    delaySecondPostMs:90,overlapPostBeforeFirstClose:true
  }),/CDP_NON_SERIAL_CHAT_POST/);
});



test('first post-DONE SSE error cannot certify the pair or contaminate a valid second turn',async()=>{
  const control=await run();
  assert.equal(control.cdp_consistent,true);
  const firstPostDoneError=body+'event: error\\ndata: {"error":"post-terminal"}\\n\\n'.replaceAll('\\n','\n');
  // First-turn SSE fault is separate from a missing/expired first POST
  // metadata ACK; neither may turn the valid second stream into aggregate PASS.
  for(const extra of [
    {},
    {firstPostDataMode:'hang',requestPostDataAckTimeoutMs:40,delaySecondPostMs:90}
  ]){
    const observed=await run(false,null,null,null,{...extra,firstBody:firstPostDoneError});
    assert.equal(observed.cdp_consistent,false);
    assert.equal(observed.ttft_sse_verified,false);
    assert.deepEqual(observed.turns.map(x=>x.cdp_request_id),['1','2']);
    assert.equal(observed.turns[0].stream_timing_complete,false);
    assert.equal(observed.turns[0].ttft_ms,null);
    assert.equal(observed.turns[1].request_sha256,control.turns[1].request_sha256);
    assert.equal(observed.turns[1].cdp_decoded_body_sha256,
      control.turns[1].cdp_decoded_body_sha256);
    assert.equal(observed.turns[1].visible_text_sha256,
      control.turns[1].visible_text_sha256);
    assert.equal(observed.turns[1].ttft_ms,control.turns[1].ttft_ms);
    assert.equal(observed.turns[1].sse_done_ms,control.turns[1].sse_done_ms);
    assert.equal(observed.turns[1].stream_timing_complete,true);
    assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|post-terminal|data:/);
  }
  // A genuine overlapping POST or incomplete first finality is still
  // a hard seriality violation, not a salvageable diagnostic.
  await assert.rejects(run(false,null,null,null,{
    firstBody:firstPostDoneError,overlapPostBeforeFirstClose:true
  }),/CDP_NON_SERIAL_CHAT_POST/);
  await assert.rejects(run(false,null,null,null,{
    firstBody:body.replace('data: [DONE]\\n\\n'.replaceAll('\\n','\n'),'')+
      'event: error\\ndata: {"error":"post-terminal"}\\n\\n'.replaceAll('\\n','\n')
  }),/CDP_NON_SERIAL_CHAT_POST/);
});

test('expired first POST metadata cannot mask another first-stream fault or certify second turn',async()=>{
  const baseline=await run();
  assert.equal(baseline.cdp_consistent,true);
  // A duplicate terminal is a separate FIRST-turn SSE integrity failure.
  // Its combination with expired POST metadata must not yield aggregate PASS.
  const duplicatedFirstDone=body+'data: [DONE]\\n\\n'.replaceAll('\\n','\n');
  const observed=await run(false,null,null,null,{
    firstBody:duplicatedFirstDone,
    firstPostDataMode:'hang',requestPostDataAckTimeoutMs:40,
    delaySecondPostMs:90
  });
  assert.equal(observed.cdp_consistent,false);
  assert.equal(observed.ttft_sse_verified,false);
  assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2']);
  assert.equal(observed.turns[0].request_sha256,null);
  assert.equal(observed.turns[0].ttft_ms,null);
  assert.equal(observed.turns[0].stream_timing_complete,false);
  // The valid serial SECOND SSE is diagnostic only; its clock and digest
  // remain independent of the first turn's two simultaneous faults.
  assert.equal(observed.turns[1].request_sha256,baseline.turns[1].request_sha256);
  assert.equal(observed.turns[1].cdp_decoded_body_sha256,
    baseline.turns[1].cdp_decoded_body_sha256);
  assert.equal(observed.turns[1].ttft_ms,baseline.turns[1].ttft_ms);
  assert.equal(observed.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms);
  // Absence of the genuine first SSE terminal is never excused by a
  // coincident expired metadata lookup, despite a later valid second POST.
  for(const invalidFirst of [
    body.replace('data: [DONE]\\n\\n'.replaceAll('\\n','\n'),''),
    body.replace('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\\n\\n'.replaceAll('\\n','\n'),'')
  ]){
    await assert.rejects(run(false,null,null,null,{
      firstBody:invalidFirst,firstPostDataMode:'hang',
      requestPostDataAckTimeoutMs:40,delaySecondPostMs:90
    }),/CDP_NON_SERIAL_CHAT_POST/);
  }
  await assert.rejects(run(false,null,null,null,{
    firstBody:duplicatedFirstDone,firstPostDataMode:'hang',
    requestPostDataAckTimeoutMs:40,delaySecondPostMs:90,
    overlapPostBeforeFirstClose:true
  }),/CDP_NON_SERIAL_CHAT_POST/);
  assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/);
});


test('post-DONE first-turn error plus failed, reversed or absent network close rejects second POST',async()=>{
  const baseline=await run();
  assert.equal(baseline.cdp_consistent,true);
  const invalidFirst=body+'event: error\n'+'data: {"error":"after done"}\n\n';
  // A successfully closed first network request allows attribution of a
  // second stream for diagnostics, but not aggregate acceptance of the pair.
  const control=await run(false,null,null,null,{firstBody:invalidFirst});
  assert.equal(control.cdp_consistent,false);
  assert.equal(control.ttft_sse_verified,false);
  assert.deepEqual(control.turns.map(t=>t.cdp_request_id),['1','2']);
  assert.equal(control.turns[0].stream_timing_complete,false);
  assert.equal(control.turns[0].ttft_ms,null);
  assert.equal(control.turns[1].request_sha256,baseline.turns[1].request_sha256);
  assert.equal(control.turns[1].cdp_decoded_body_sha256,
    baseline.turns[1].cdp_decoded_body_sha256);
  assert.equal(control.turns[1].ttft_ms,baseline.turns[1].ttft_ms);
  assert.equal(control.turns[1].sse_done_ms,baseline.turns[1].sse_done_ms);
  assert.equal(control.turns[1].stream_timing_complete,true);
  // An apparent SSE stop+[DONE] never substitutes for a valid first
  // Network.loadingFinished before the second browser POST.
  for(const [scenario,flags] of [
    ['first network loadingFailed',{firstLoadingFailed:true}],
    ['first close before data',{firstCloseTimestamp:100.009}],
    ['first close missing',{omitFirstClose:true}]
  ]){
    await assert.rejects(run(false,null,null,null,{firstBody:invalidFirst,...flags}),
      /CDP_NON_SERIAL_CHAT_POST/,scenario);
  }
  assert.doesNotMatch(JSON.stringify(control),/after done|secret|Hello|data:/);
});

test('second post-DONE error plus failed or invalid network close never certifies second turn',async()=>{
  const baseline=await run();
  assert.equal(baseline.cdp_consistent,true);
  assert.equal(baseline.ttft_sse_verified,true);
  const invalidSecond=body+'event: error\n'+'data: {"error":"after-second-done"}\n\n';
  const first=baseline.turns[0];
  const keepFirst=(observed,label)=>{
    assert.equal(observed.cdp_consistent,false,label);
    assert.equal(observed.ttft_sse_verified,false,label);
    assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2'],label);
    assert.equal(observed.turns[0].request_sha256,first.request_sha256,label);
    assert.equal(observed.turns[0].cdp_decoded_body_sha256,first.cdp_decoded_body_sha256,label);
    assert.equal(observed.turns[0].visible_text_sha256,first.visible_text_sha256,label);
    assert.equal(observed.turns[0].ttft_ms,first.ttft_ms,label);
    assert.equal(observed.turns[0].sse_done_ms,first.sse_done_ms,label);
    assert.equal(observed.turns[0].stream_timing_complete,true,label);
    assert.equal(observed.turns[1].ttft_ms,null,label);
    assert.equal(observed.turns[1].sse_done_ms,null,label);
    assert.equal(observed.turns[1].stream_timing_complete,false,label);
    assert.doesNotMatch(JSON.stringify(observed),/after-second-done|secret|Hello|data:/,label);
  };
  // The second POST was serial and network-closed; a second post-DONE
  // SSE fault alone must reject pair acceptance but not damage first evidence.
  const faultOnly=await run(false,[Buffer.from(invalidSecond)]);
  keepFirst(faultOnly,'second late event with valid close');
  for(const [label,flags] of [
    ['second Network.loadingFailed',{loadingFailed:true}],
    ['second network close before decoded data',{closeTimestamp:101.009}]
  ]){
    const observed=await run(false,[Buffer.from(invalidSecond)],null,null,flags);
    keepFirst(observed,label);
    assert.equal(observed.turns[1].sse_done_to_loading_finished_ms,null,label);
  }
  // No Network.loadingFinished/Failed for second POST: no fabricated
  // completion, regardless of decoded stop or [DONE].
  await assert.rejects(
    run(false,[Buffer.from(invalidSecond)],null,null,{omitSecondClose:true}),
    /CDP_TIMEOUT/);
});

test('late second response-body ACK cannot revive failed or reversed network-close SSE proof',async()=>{
  const baseline=await run();
  assert.equal(baseline.cdp_consistent,true);
  assert.equal(baseline.ttft_sse_verified,true);
  const first=baseline.turns[0];
  const firstKeys=['cdp_request_id','request_sha256','cdp_decoded_body_sha256',
    'cdp_streamed_body_sha256','visible_text_sha256','ttft_ms','sse_done_ms',
    'stream_timing_complete'];
  const assertFirst=(observed,label)=>{
    for(const key of firstKeys)
      assert.deepEqual(observed.turns[0][key],first[key],label+': first '+key);
  };
  // A legitimate second Network.loadingFinished + immediate ACK is the
  // positive control. Its decoded-body witness MUST remain verifiable.
  const healthy=await run(false,null,null,null,{responseBodyAckTimeoutMs:40,quiescenceMs:50});
  assert.equal(healthy.cdp_consistent,true);
  assert.equal(healthy.ttft_sse_verified,true);
  assertFirst(healthy,'healthy');
  assert.equal(healthy.turns[1].cdp_decoded_body_matches_stream,true);

  // In all six crossed cases, a late rejected or resolved ACK is observer
  // metadata, never a repair for failed/reversed second network finality.
  // A hung ACK must also fail boundedly without reviving any digest.
  for(const [closeLabel,closeFlags] of [
    ['second loadingFailed',{loadingFailed:true}],
    ['second close before data',{closeTimestamp:101.009}]
  ]){
    for(const ackMode of ['late-resolve','late-reject','hang']){
      const label=closeLabel+' / '+ackMode, settled=[];
      const flags={...closeFlags,responseBodyAckTimeoutMs:40,quiescenceMs:50,
        responseBodySettled:(id,kind)=>settled.push([id,kind]),
        ...(ackMode==='hang'?{responseBodyHang:['2']}:
          {responseBodyDelay:{'2':200},
           ...(ackMode==='late-reject'?{responseBodyRejectAfterDelay:['2']}: {})})};
      const observed=await run(false,null,null,null,flags);
      const sealed=JSON.stringify(observed);
      assert.equal(observed.cdp_consistent,false,label);
      assert.equal(observed.ttft_sse_verified,false,label);
      assertFirst(observed,label);
      assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2'],label);
      assert.equal(observed.turns[1].request_sha256,baseline.turns[1].request_sha256,label);
      assert.equal(observed.turns[1].cdp_streamed_body_sha256,
        baseline.turns[1].cdp_streamed_body_sha256,label);
      assert.equal(observed.turns[1].cdp_decoded_body_sha256,null,label);
      assert.equal(observed.turns[1].cdp_decoded_body_matches_stream,false,label);
      assert.equal(observed.turns[1].visible_text_sha256,null,label);
      assert.equal(observed.turns[1].ttft_ms,null,label);
      assert.equal(observed.turns[1].sse_done_ms,null,label);
      assert.equal(observed.turns[1].sse_done_to_loading_finished_ms,null,label);
      assert.equal(observed.turns[1].cdp_response_body_ack_latency_ms,null,label);
      assert.equal(observed.turns[1].stream_timing_complete,false,label);
      if(ackMode!=='hang'){
        // The body lookup completes AFTER capture's timeout and final
        // snapshot, so no unsealed mutable state can leak into the result.
        await new Promise(resolve=>setTimeout(resolve,215));
        assert.deepEqual(settled,[['1','resolved'],['2',ackMode==='late-reject'?'rejected':'resolved']],label);
      }
      assert.equal(JSON.stringify(observed),sealed,label+' late ACK mutated sealed receipt');
      assert.doesNotMatch(sealed,/secret|Hello|data:/,label);
    }
  }
  // A correctly closed second stream with a late ACK is also unverified;
  // the same observer cannot recover PASS by ignoring the ACK guard.
  const lateControl=await run(false,null,null,null,{
    responseBodyDelay:{'2':200},responseBodyAckTimeoutMs:40,quiescenceMs:50
  });
  assert.equal(lateControl.cdp_consistent,false);
  assert.equal(lateControl.ttft_sse_verified,false);
  assertFirst(lateControl,'valid close, late body ACK');
  assert.equal(lateControl.turns[1].cdp_decoded_body_sha256,null);
  assert.equal(lateControl.turns[1].ttft_ms,null);
});

test('second duplicate or contradictory close during post-ACK quiescence fails closed',async()=>{
  // CDP is observed for a finite window after the second body ACK.
  // These are late NETWORK events, not extra SSE data or model requests.
  const firstKeys=['cdp_request_id','request_sha256','cdp_decoded_body_sha256',
    'cdp_streamed_body_sha256','visible_text_sha256','ttft_ms','sse_done_ms',
    'stream_timing_complete'];
  const control=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  for(const method of ['Network.loadingFinished','Network.loadingFailed']){
    let observedLateClose=0;
    const observed=await run(false,null,null,null,{
      quiescenceMs:80,
      // Stub schedules postAckEvent 25ms after successful second
      // Network.getResponseBody, before the 80ms quiet window expires.
      postAckEvent:session=>{
        observedLateClose++;
        session.emit(method,{requestId:'2',timestamp:101.03});
      }
    });
    assert.equal(observedLateClose,1,method+' delivered inside quiescence');
    assert.equal(observed.cdp_consistent,false,method);
    assert.equal(observed.ttft_sse_verified,false,method);
    assert.deepEqual(observed.turns.map(x=>x.cdp_request_id),['1','2']);
    for(const key of firstKeys)
      assert.deepEqual(observed.turns[0][key],control.turns[0][key],method+' first '+key);
    assert.equal(observed.turns[1].request_sha256,control.turns[1].request_sha256);
    assert.equal(observed.turns[1].cdp_streamed_body_sha256,
      control.turns[1].cdp_streamed_body_sha256);
    assert.equal(observed.turns[1].cdp_decoded_body_matches_stream,false);
    assert.equal(observed.turns[1].visible_text_sha256,null);
    assert.equal(observed.turns[1].ttft_ms,null);
    assert.equal(observed.turns[1].sse_done_ms,null);
    assert.equal(observed.turns[1].stream_timing_complete,false);
    assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/);
  }
  // This proves the observation boundary, NOT an unlimited guarantee:
  // an event emitted only after capture returns cannot retroactively alter
  // the returned snapshot. The real CDP connection is closed at this point.
  let beyondWindow=0;
  const limited=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      beyondWindow++;
      session.emit('Network.loadingFailed',{requestId:'2',timestamp:101.04});
    },90)
  });
  assert.equal(beyondWindow,0,'late event not present in the bounded observation');
  assert.equal(limited.cdp_consistent,true);
  assert.equal(limited.ttft_sse_verified,true);
  const sealed=JSON.stringify(limited);
  await new Promise(resolve=>setTimeout(resolve,110));
  assert.equal(beyondWindow,1,'fixture deliberately emits after capture');
  assert.equal(JSON.stringify(limited),sealed,'post-capture event cannot alter returned evidence');
});


test('late second CDP data chunk after body ACK fails closed within bounded quiescence',async()=>{
  const firstKeys=['cdp_request_id','request_sha256','cdp_decoded_body_sha256',
    'cdp_streamed_body_sha256','visible_text_sha256','ttft_ms','sse_done_ms',
    'stream_timing_complete'];
  const control=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  // Network.dataReceived after loadingFinished must not update a finalized
  // crypto hash or turn an already ACK-matched stream into a false PASS.
  for(const data of [
    Buffer.from('data: [DONE]\n\n').toString('base64'),
    Buffer.from('unexpected extra bytes').toString('base64'),
    ''
  ]){
    let delivered=0;
    const observed=await run(false,null,null,null,{
      quiescenceMs:80,
      postAckEvent:session=>{
        delivered++;
        session.emit('Network.dataReceived',{requestId:'2',timestamp:101.03,data});
      }
    });
    assert.equal(delivered,1,'event reached attached observer before seal');
    assert.equal(observed.cdp_consistent,false,'late chunk revokes stream/body match');
    assert.equal(observed.ttft_sse_verified,false);
    for(const key of firstKeys)
      assert.deepEqual(observed.turns[0][key],control.turns[0][key],key);
    assert.equal(observed.turns[1].request_sha256,control.turns[1].request_sha256);
    assert.equal(observed.turns[1].cdp_streamed_body_sha256,
      control.turns[1].cdp_streamed_body_sha256);
    assert.equal(observed.turns[1].cdp_decoded_body_matches_stream,false);
    assert.equal(observed.turns[1].ttft_ms,null);
    assert.equal(observed.turns[1].sse_done_ms,null);
    assert.equal(observed.turns[1].visible_text_sha256,null);
    assert.equal(observed.turns[1].stream_timing_complete,false);
  }
  // Explicit finite-boundary limitation: events outside the capture window
  // cannot alter a returned snapshot; no unlimited delivery guarantee.
  let outOfWindow=0;
  const limited=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      outOfWindow++;
      session.emit('Network.dataReceived',{requestId:'2',timestamp:101.04,
        data:Buffer.from('late').toString('base64')});
    },90)
  });
  assert.equal(outOfWindow,0);
  assert.equal(limited.cdp_consistent,true);
  const sealed=JSON.stringify(limited);
  await new Promise(resolve=>setTimeout(resolve,110));
  assert.equal(outOfWindow,1);
  assert.equal(JSON.stringify(limited),sealed);
});

test('late second HTTP ExtraInfo after body ACK revokes stream proof, first turn isolated',async()=>{
  const firstKeys=['cdp_request_id','request_sha256','cdp_decoded_body_sha256',
    'cdp_streamed_body_sha256','visible_text_sha256','ttft_ms','sse_done_ms',
    'stream_timing_complete'];
  const control=await run(false,null,null,null,{
    hasExtraInfo:true,extraBefore:true,quiescenceMs:80
  });
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.equal(control.turns[1].cdp_decoded_body_matches_stream,true);
  // All arrive 25ms AFTER second getResponseBody ACK, while capture is attached.
  for(const [name,info] of [
    ['duplicate',{statusCode:200,headers:{}}],
    ['cache-status-alias',{statusCode:304,headers:{}}],
    ['compressed-encoding',{statusCode:200,headers:{'Content-Encoding':'gzip'}}],
    ['cache-provenance',{statusCode:200,headers:{},fromDiskCache:true}]
  ]){
    let delivered=0;
    const observed=await run(false,null,null,null,{
      hasExtraInfo:true,extraBefore:true,quiescenceMs:80,
      postAckEvent:session=>{
        delivered++;
        session.emit('Network.responseReceivedExtraInfo',{requestId:'2',...info});
      }
    });
    assert.equal(delivered,1,name+' ExtraInfo reached live observer');
    assert.equal(observed.cdp_consistent,false,name);
    assert.equal(observed.ttft_sse_verified,false,name);
    assert.deepEqual(observed.turns.map(x=>x.cdp_request_id),['1','2']);
    for(const key of firstKeys)
      assert.deepEqual(observed.turns[0][key],control.turns[0][key],name+' first '+key);
    assert.equal(observed.turns[1].request_sha256,control.turns[1].request_sha256);
    assert.equal(observed.turns[1].cdp_streamed_body_sha256,
      control.turns[1].cdp_streamed_body_sha256);
    assert.equal(observed.turns[1].cdp_decoded_body_matches_stream,false,name);
    assert.equal(observed.turns[1].visible_text_sha256,null,name);
    assert.equal(observed.turns[1].ttft_ms,null,name);
    assert.equal(observed.turns[1].sse_done_ms,null,name);
    assert.equal(observed.turns[1].stream_timing_complete,false,name);
    assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/);
  }
  // Bounded capture limitation: an event emitted after return cannot rewrite
  // the returned digest receipt. No indefinite CDP delivery is claimed.
  let beyond=0;
  const limited=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      beyond++;
      session.emit('Network.responseReceivedExtraInfo',{
        requestId:'2',statusCode:304,headers:{}});
    },90)
  });
  assert.equal(limited.cdp_consistent,true);
  assert.equal(beyond,0);
  const sealed=JSON.stringify(limited);
  await new Promise(resolve=>setTimeout(resolve,110));
  assert.equal(beyond,1);
  assert.equal(JSON.stringify(limited),sealed);
});

test('second responseReceived replay after body ACK fails closed without first-turn contamination',async()=>{
  const firstKeys=['cdp_request_id','request_sha256','cdp_decoded_body_sha256',
    'cdp_streamed_body_sha256','visible_text_sha256','ttft_ms','sse_done_ms',
    'stream_timing_complete'];
  const control=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  // A duplicate responseReceived after loadingFinished and successful body ACK
  // cannot re-certify the same response, regardless of its reported status.
  for(const [name,response] of [
    ['identical',{status:200,mimeType:'text/event-stream',url:'http://localhost/api/nox/chat',headers:{}}],
    ['contradictory-status',{status:503,mimeType:'text/event-stream',url:'http://localhost/api/nox/chat',headers:{}}],
    ['contradictory-encoding',{status:200,mimeType:'text/event-stream',url:'http://localhost/api/nox/chat',headers:{'Content-Encoding':'gzip'}}],
    ['cached-replay',{status:200,mimeType:'text/event-stream',url:'http://localhost/api/nox/chat',headers:{},fromDiskCache:true}]
  ]){
    let delivered=0;
    const result=await run(false,null,null,null,{
      quiescenceMs:80,
      postAckEvent:session=>{
        delivered++;
        session.emit('Network.responseReceived',{
          requestId:'2',timestamp:101.03,frameId:'fixture-frame',
          loaderId:'fixture-loader',response,hasExtraInfo:false});
      }
    });
    assert.equal(delivered,1,name+' replay must be observed during quiescence');
    assert.equal(result.cdp_consistent,false,name+' cannot keep cdp_consistent');
    assert.equal(result.ttft_sse_verified,false,name);
    assert.deepEqual(result.turns.map(t=>t.cdp_request_id),['1','2']);
    for(const key of firstKeys)
      assert.deepEqual(result.turns[0][key],control.turns[0][key],name+' first '+key);
    assert.equal(result.turns[1].request_sha256,control.turns[1].request_sha256);
    assert.equal(result.turns[1].cdp_streamed_body_sha256,
      control.turns[1].cdp_streamed_body_sha256);
    assert.equal(result.turns[1].cdp_decoded_body_matches_stream,false,name);
    assert.equal(result.turns[1].ttft_ms,null,name);
    assert.equal(result.turns[1].sse_done_ms,null,name);
    assert.equal(result.turns[1].visible_text_sha256,null,name);
    assert.equal(result.turns[1].stream_timing_complete,false,name);
    assert.doesNotMatch(JSON.stringify(result),/secret|Hello|data:/);
  }
  // An event outside the finite observer window is not retrospectively attested.
  let beyond=0;
  const boundary=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      beyond++;
      session.emit('Network.responseReceived',{
        requestId:'2',timestamp:101.03,frameId:'fixture-frame',
        loaderId:'fixture-loader',hasExtraInfo:false,
        response:{status:503,mimeType:'text/event-stream',
          url:'http://localhost/api/nox/chat',headers:{}}});
    },90)
  });
  assert.equal(boundary.cdp_consistent,true);
  assert.equal(beyond,0);
  const sealed=JSON.stringify(boundary);
  await new Promise(resolve=>setTimeout(resolve,110));
  assert.equal(beyond,1);
  assert.equal(JSON.stringify(boundary),sealed);
});


test('late second requestServedFromCache after ACK revokes matched SSE body only within bounded CDP capture',async()=>{
  const firstKeys=['cdp_request_id','request_sha256','cdp_decoded_body_sha256',
    'cdp_streamed_body_sha256','visible_text_sha256','ttft_ms','sse_done_ms',
    'stream_timing_complete'];
  const control=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(control.cdp_consistent,true);
  assert.equal(control.ttft_sse_verified,true);
  assert.equal(control.turns[1].cdp_decoded_body_matches_stream,true);
  // The second body ACK succeeded, then a contradictory cache provenance
  // event appears during the finite post-ACK observation interval.
  for(const [name,event] of [
    ['cache-provenance',{requestId:'2'}],
    ['cache-provenance-with-ignored-protocol-time',{requestId:'2',timestamp:101.03}]
  ]){
    let delivered=0;
    const result=await run(false,null,null,null,{
      quiescenceMs:80,
      postAckEvent:session=>{
        delivered++;
        session.emit('Network.requestServedFromCache',event);
      }
    });
    assert.equal(delivered,1,name+' observed inside post-ACK quiescence');
    assert.equal(result.cdp_consistent,false,name+' cannot certify second body');
    assert.equal(result.ttft_sse_verified,false,name);
    assert.deepEqual(result.turns.map(t=>t.cdp_request_id),['1','2']);
    for(const key of firstKeys)
      assert.deepEqual(result.turns[0][key],control.turns[0][key],name+' first '+key);
    assert.equal(result.turns[1].request_sha256,control.turns[1].request_sha256);
    assert.equal(result.turns[1].cdp_streamed_body_sha256,
      control.turns[1].cdp_streamed_body_sha256);
    assert.equal(result.turns[1].cdp_decoded_body_matches_stream,false,name);
    assert.equal(result.turns[1].ttft_ms,null,name);
    assert.equal(result.turns[1].sse_done_ms,null,name);
    assert.equal(result.turns[1].visible_text_sha256,null,name);
    assert.equal(result.turns[1].stream_timing_complete,false,name);
    assert.doesNotMatch(JSON.stringify(result),/secret|Hello|data:/);
  }
  // After capture returns, a later notification cannot retroactively certify
  // or mutate its sealed digest-only observation; it is not attested either.
  let beyond=0;
  const sealed=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      beyond++;
      session.emit('Network.requestServedFromCache',{requestId:'2'});
    },90)
  });
  assert.equal(sealed.cdp_consistent,true);
  assert.equal(beyond,0);
  const snapshot=JSON.stringify(sealed);
  await new Promise(resolve=>setTimeout(resolve,110));
  assert.equal(beyond,1);
  assert.equal(JSON.stringify(sealed),snapshot);
});


test('late FIRST cache provenance during second POST revokes first only, retaining second SSE proof',async()=>{
  const clean=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  let firstBodyAck=false,ackBeforeSecond=null,cacheEvents=0;
  const observed=await run(false,null,null,null,{
    quiescenceMs:80,
    responseBodySettled:(id,status)=>{
      if(id==='1'&&status==='resolved')firstBodyAck=true;
    },
    lifecycleDuringSecond:session=>{
      // This executes after second requestWillBeSent but BEFORE its SSE
      // response/data/DONE/loadingFinished events.
      ackBeforeSecond=firstBodyAck;
      cacheEvents++;
      session.emit('Network.requestServedFromCache',{requestId:'1'});
    }
  });
  assert.equal(ackBeforeSecond,true,'first getResponseBody ACK before second POST');
  assert.equal(cacheEvents,1,'first cache event observed while second was in flight');
  assert.equal(observed.cdp_consistent,false,'uncertain first provenance revokes pair');
  assert.equal(observed.ttft_sse_verified,false);
  assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2']);
  const first=observed.turns[0],second=observed.turns[1];
  assert.equal(first.request_sha256,clean.turns[0].request_sha256);
  assert.equal(first.cdp_streamed_body_sha256,clean.turns[0].cdp_streamed_body_sha256);
  assert.equal(first.cdp_decoded_body_sha256,clean.turns[0].cdp_decoded_body_sha256);
  assert.equal(first.cdp_decoded_body_matches_stream,false);
  assert.equal(first.ttft_ms,null);assert.equal(first.sse_done_ms,null);
  assert.equal(first.stream_timing_complete,false);
  assert.equal(first.visible_text_sha256,null);
  for(const key of ['cdp_request_id','request_sha256','cdp_decoded_body_sha256',
    'cdp_streamed_body_sha256','visible_text_sha256','ttft_ms','sse_done_ms',
    'sse_done_to_loading_finished_ms','stream_timing_complete',
    'cdp_decoded_body_matches_stream']){
    assert.deepEqual(second[key],clean.turns[1][key],'independent second '+key);
  }
  assert.equal(second.stream_timing_complete,true);
  assert.equal(second.ttft_ms,10);
  assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/);

  // The observer has a finite capture interval. A first-turn cache event
  // after capture cannot retroactively alter the returned sealed snapshot.
  let afterCapture=0;
  const sealed=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      afterCapture++;
      session.emit('Network.requestServedFromCache',{requestId:'1'});
    },90)
  });
  assert.equal(sealed.cdp_consistent,true);
  assert.equal(afterCapture,0);
  const snapshot=JSON.stringify(sealed);
  await new Promise(resolve=>setTimeout(resolve,130));
  assert.equal(afterCapture,1);
  assert.equal(JSON.stringify(sealed),snapshot);
});


test('late FIRST data after body ACK during SECOND stream cannot poison independent second SSE',async()=>{
  const clean=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  assert.deepEqual(clean.turns.map(t=>t.cdp_request_id),['1','2']);
  // The first body lookup must have resolved before the second logical POST.
  // The CDP listener still receives events for BOTH request IDs.
  for(const [name,data] of [
    ['duplicate-DONE',Buffer.from('data: [DONE]\n\n').toString('base64')],
    ['altered-bytes',Buffer.from('unexpected late SSE payload').toString('base64')],
    ['empty-data','']
  ]){
    let firstAck=false,ackBeforeSecond=false,delivered=0;
    const observed=await run(false,null,null,null,{
      quiescenceMs:80,
      responseBodySettled:(id,status)=>{
        if(id==='1'&&status==='resolved')firstAck=true;
      },
      lifecycleDuringSecond:session=>{
        ackBeforeSecond=firstAck;
        delivered++;
        // FIRST closed at 100.02; SECOND request started at 101.
        // The event is delivered while the second stream remains in flight.
        session.emit('Network.dataReceived',{requestId:'1',timestamp:100.03,data});
      }
    });
    assert.equal(ackBeforeSecond,true,name+' first body ACK before second');
    assert.equal(delivered,1,name+' late first chunk reached attached CDP listener');
    assert.equal(observed.cdp_consistent,false,name+' pair cannot certify');
    assert.equal(observed.ttft_sse_verified,false,name);
    assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2']);
    const first=observed.turns[0],second=observed.turns[1];
    assert.equal(first.request_sha256,clean.turns[0].request_sha256,name);
    assert.equal(first.cdp_streamed_body_sha256,clean.turns[0].cdp_streamed_body_sha256,name);
    assert.equal(first.cdp_decoded_body_sha256,clean.turns[0].cdp_decoded_body_sha256,name);
    assert.equal(first.cdp_decoded_body_matches_stream,false,name);
    assert.equal(first.ttft_ms,null,name);
    assert.equal(first.sse_done_ms,null,name);
    assert.equal(first.visible_text_sha256,null,name);
    assert.equal(first.stream_timing_complete,false,name);
    for(const key of ['cdp_request_id','request_sha256',
      'cdp_decoded_body_sha256','cdp_streamed_body_sha256','visible_text_sha256',
      'ttft_ms','sse_done_ms','sse_done_to_loading_finished_ms',
      'stream_timing_complete','cdp_decoded_body_matches_stream']){
      assert.deepEqual(second[key],clean.turns[1][key],name+' second '+key);
    }
    assert.equal(second.stream_timing_complete,true,name);
    assert.equal(second.ttft_ms,10,name);
    assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/,name);
  }
  // An event beyond the finite CDP capture is NOT retrospectively attested.
  let afterCapture=0;
  const sealed=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      afterCapture++;
      session.emit('Network.dataReceived',{
        requestId:'1',timestamp:100.04,
        data:Buffer.from('late after observer seal').toString('base64')});
    },90)
  });
  assert.equal(sealed.cdp_consistent,true);
  assert.equal(afterCapture,0);
  const snapshot=JSON.stringify(sealed);
  await new Promise(resolve=>setTimeout(resolve,125));
  assert.equal(afterCapture,1);
  assert.equal(JSON.stringify(sealed),snapshot);
});

test('late FIRST ExtraInfo after its body ACK during SECOND SSE revokes first only',async()=>{
  const clean=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  for(const [name,statusCode,headers,duplicate] of [
    ['unexpected-late-identity',200,{'Content-Encoding':'identity'},false],
    ['cached-304-after-200',304,{'X-Cache':'HIT'},false],
    ['conflicting-compression',200,{'content-encoding':'gzip','Cache-Control':'public'},false],
    ['duplicate-late-extra-info',200,{'Content-Encoding':'identity'},true],
  ]){
    let firstBodyAck=false,ackBeforeSecond=false,delivered=0;
    const observed=await run(false,null,null,null,{
      quiescenceMs:80,
      responseBodySettled:(id,status)=>{
        if(id==='1'&&status==='resolved')firstBodyAck=true;
      },
      lifecycleDuringSecond:session=>{
        // FIRST loadingFinished and body ACK preceded SECOND requestWillBeSent.
        // The second HTTP/SSE body has not yet been delivered.
        ackBeforeSecond=firstBodyAck;
        const event={requestId:'1',statusCode,headers};
        session.emit('Network.responseReceivedExtraInfo',event);
        delivered++;
        if(duplicate){
          session.emit('Network.responseReceivedExtraInfo',event);
          delivered++;
        }
      }
    });
    assert.equal(ackBeforeSecond,true,name+' first body ACK precedes second');
    assert.equal(delivered,duplicate?2:1,name+' first HTTP event delivered');
    assert.equal(observed.cdp_consistent,false,name+' pair must not certify');
    assert.equal(observed.ttft_sse_verified,false,name);
    assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2']);
    const first=observed.turns[0],second=observed.turns[1];
    for(const key of ['request_sha256','cdp_streamed_body_sha256',
      'cdp_decoded_body_sha256']){
      assert.deepEqual(first[key],clean.turns[0][key],name+' first digest '+key);
    }
    assert.equal(first.cdp_decoded_body_matches_stream,false,name);
    assert.equal(first.ttft_ms,null,name);
    assert.equal(first.sse_done_ms,null,name);
    assert.equal(first.visible_text_sha256,null,name);
    assert.equal(first.stream_timing_complete,false,name);
    for(const key of ['cdp_request_id','request_sha256','cdp_streamed_body_sha256',
      'cdp_decoded_body_sha256','cdp_decoded_body_matches_stream',
      'visible_text_sha256','ttft_ms','sse_done_ms',
      'sse_done_to_loading_finished_ms','stream_timing_complete']){
      assert.deepEqual(second[key],clean.turns[1][key],name+' second '+key);
    }
    assert.equal(second.stream_timing_complete,true,name);
    assert.equal(second.ttft_ms,10,name);
    assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/,name);
  }
  // Only a finite observation interval can be certified. Later notifications
  // do not amend a returned snapshot or prove lifetime-long absence.
  let beyondCapture=0;
  const sealed=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      beyondCapture++;
      session.emit('Network.responseReceivedExtraInfo',{
        requestId:'1',statusCode:304,headers:{'X-Cache':'HIT'}});
    },90)
  });
  assert.equal(sealed.cdp_consistent,true);
  assert.equal(beyondCapture,0);
  const snapshot=JSON.stringify(sealed);
  await new Promise(resolve=>setTimeout(resolve,125));
  assert.equal(beyondCapture,1);
  assert.equal(JSON.stringify(sealed),snapshot);
});

test('late FIRST responseReceived replay during SECOND SSE revokes first only',async()=>{
  // Each request ID has independent provenance; a terminal FIRST response
  // must not be revived or attributed to the still-open SECOND SSE stream.
  const clean=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  assert.deepEqual(clean.turns.map(t=>t.cdp_request_id),['1','2']);
  for(const [name,response] of [
    ['identical-replay',{status:200,mimeType:'text/event-stream',
      url:'http://localhost/api/nox/chat',headers:{}}],
    ['contradictory-503',{status:503,mimeType:'text/event-stream',
      url:'http://localhost/api/nox/chat',headers:{}}],
    ['compressed-replay',{status:200,mimeType:'text/event-stream',
      url:'http://localhost/api/nox/chat',headers:{'Content-Encoding':'gzip'}}],
    ['cached-replay',{status:200,mimeType:'text/event-stream',
      url:'http://localhost/api/nox/chat',headers:{},fromDiskCache:true}]
  ]){
    let firstAck=false,ackBeforeSecond=false,delivered=0;
    const observed=await run(false,null,null,null,{
      quiescenceMs:80,
      responseBodySettled:(id,status)=>{
        if(id==='1'&&status==='resolved')firstAck=true;
      },
      lifecycleDuringSecond:session=>{
        ackBeforeSecond=firstAck;
        delivered++;
        session.emit('Network.responseReceived',{
          requestId:'1',timestamp:100.04,frameId:'fixture-frame',
          loaderId:'fixture-loader',response,hasExtraInfo:false});
      }
    });
    assert.equal(ackBeforeSecond,true,name+' FIRST response body ACK precedes SECOND');
    assert.equal(delivered,1,name+' FIRST replay reached CDP while SECOND in flight');
    assert.equal(observed.cdp_consistent,false,name+' pair must fail closed');
    assert.equal(observed.ttft_sse_verified,false,name);
    assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2']);
    const first=observed.turns[0],second=observed.turns[1];
    for(const key of ['request_sha256','cdp_streamed_body_sha256',
      'cdp_decoded_body_sha256'])
      assert.deepEqual(first[key],clean.turns[0][key],name+' first '+key);
    assert.equal(first.cdp_decoded_body_matches_stream,false,name);
    assert.equal(first.ttft_ms,null,name);
    assert.equal(first.sse_done_ms,null,name);
    assert.equal(first.visible_text_sha256,null,name);
    assert.equal(first.stream_timing_complete,false,name);
    for(const key of ['cdp_request_id','request_sha256','cdp_streamed_body_sha256',
      'cdp_decoded_body_sha256','cdp_decoded_body_matches_stream',
      'visible_text_sha256','ttft_ms','sse_done_ms',
      'sse_done_to_loading_finished_ms','stream_timing_complete'])
      assert.deepEqual(second[key],clean.turns[1][key],name+' second '+key);
    assert.equal(second.stream_timing_complete,true,name);
    assert.equal(second.ttft_ms,10,name+' synthetic CDP only');
    assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/,name);
  }
  // The returned witness is sealed: a later Chrome notification cannot
  // retroactively certify or poison it, and no lifetime guarantee is made.
  let afterCapture=0;
  const sealed=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      afterCapture++;
      session.emit('Network.responseReceived',{
        requestId:'1',timestamp:100.04,frameId:'fixture-frame',
        loaderId:'fixture-loader',hasExtraInfo:false,
        response:{status:503,mimeType:'text/event-stream',
          url:'http://localhost/api/nox/chat',headers:{}}});
    },90)
  });
  assert.equal(sealed.cdp_consistent,true);
  assert.equal(afterCapture,0);
  const snapshot=JSON.stringify(sealed);
  await new Promise(resolve=>setTimeout(resolve,125));
  assert.equal(afterCapture,1);
  assert.equal(JSON.stringify(sealed),snapshot);
});

test('late FIRST terminal-close replay during SECOND SSE revokes first only',async()=>{
  // A first-turn network close cannot be repeated once its getResponseBody ACK
  // has settled, even when Chrome is already streaming the second chat POST.
  const clean=await run(false,null,null,null,{quiescenceMs:80});
  assert.equal(clean.cdp_consistent,true);
  assert.equal(clean.ttft_sse_verified,true);
  assert.deepEqual(clean.turns.map(t=>t.cdp_request_id),['1','2']);
  for(const [name,method] of [
    ['duplicate-loadingFinished','Network.loadingFinished'],
    ['contradictory-loadingFailed','Network.loadingFailed']
  ]){
    let acked=false,ackBeforeSecond=false,delivered=0;
    const observed=await run(false,null,null,null,{
      quiescenceMs:80,
      responseBodySettled:(id,status)=>{
        if(id==='1'&&status==='resolved')acked=true;
      },
      lifecycleDuringSecond:session=>{
        ackBeforeSecond=acked;
        delivered++;
        session.emit(method,{requestId:'1',timestamp:100.04});
      }
    });
    assert.equal(ackBeforeSecond,true,name+' FIRST body ACK preceded SECOND');
    assert.equal(delivered,1,name+' late FIRST close reached observer during SECOND');
    assert.deepEqual(observed.turns.map(t=>t.cdp_request_id),['1','2'],name);
    assert.equal(observed.cdp_consistent,false,name+' pair integrity revoked');
    assert.equal(observed.ttft_sse_verified,false,name+' pair timing revoked');
    const [first,second]=observed.turns;
    for(const key of ['request_sha256','cdp_streamed_body_sha256',
      'cdp_decoded_body_sha256'])
      assert.deepEqual(first[key],clean.turns[0][key],name+' FIRST diagnostic '+key);
    assert.equal(first.cdp_decoded_body_matches_stream,false,name);
    assert.equal(first.ttft_ms,null,name);
    assert.equal(first.sse_done_ms,null,name);
    assert.equal(first.visible_text_sha256,null,name);
    assert.equal(first.stream_timing_complete,false,name);
    for(const key of ['cdp_request_id','request_sha256','cdp_streamed_body_sha256',
      'cdp_decoded_body_sha256','cdp_decoded_body_matches_stream',
      'visible_text_sha256','ttft_ms','sse_done_ms',
      'sse_done_to_loading_finished_ms','stream_timing_complete'])
      assert.deepEqual(second[key],clean.turns[1][key],name+' SECOND independent '+key);
    assert.equal(second.stream_timing_complete,true,name);
    assert.equal(second.ttft_ms,10,name+' fixture CDP TTFT, not real model');
    assert.doesNotMatch(JSON.stringify(observed),/secret|Hello|data:/,name);
  }
  // A returned snapshot is immutable; finite quiescence is not proof that
  // Chrome can never emit a later contradictory notification.
  let afterCapture=0;
  const sealed=await run(false,null,null,null,{
    quiescenceMs:50,
    postAckEvent:session=>setTimeout(()=>{
      afterCapture++;
      session.emit('Network.loadingFailed',{requestId:'1',timestamp:100.05});
    },90)
  });
  assert.equal(sealed.cdp_consistent,true);
  assert.equal(afterCapture,0);
  const snapshot=JSON.stringify(sealed);
  await new Promise(resolve=>setTimeout(resolve,125));
  assert.equal(afterCapture,1);
  assert.equal(JSON.stringify(sealed),snapshot);
});
