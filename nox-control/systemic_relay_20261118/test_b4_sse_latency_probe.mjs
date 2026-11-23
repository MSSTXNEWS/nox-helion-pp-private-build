import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {setTimeout as sleep} from 'node:timers/promises';
import {performance} from 'node:perf_hooks';
import {measureSseResponse,measureSseFetch} from './b4_sse_latency_probe.mjs';

const hash=s=>createHash('sha256').update(s).digest('hex');
const event=x=>'data: '+JSON.stringify({choices:[x]})+'\n\n';
const messages=['Привет 🌍','Hola 🌈','三番目 ✨'];
const clean=i=>[ ': heartbeat\n\n',event({delta:{content:' \u0301'}}),
  event({delta:{content:messages[i]}}),event({delta:{},finish_reason:'stop'}),'data: [DONE]\n\n' ];

async function withFixture(handler){
  const requests=[];
  const server=createServer(async(req,res)=>{
    if(req.url!=='/nox/chat'||req.method!=='POST'){res.writeHead(404).end();return;}
    let input='';for await(const chunk of req)input+=chunk;
    const {turn,scenario='clean'}=JSON.parse(input);
    requests.push({turn,scenario,body_sha256:hash(input)});
    res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store'});
    res.flushHeaders();
    try{
      const chunks=clean(turn-1);
      if(['cr_only','crlf_split','multiline','unframed_cr','unframed_crlf'].includes(scenario)){
        const base=chunks.join('');
        if(scenario==='multiline'){
          const parts=[': heartbeat\r\n\r\n','data\r\n\r\n',
            'data: {"choices":[\r\n',
            'data: {"delta":{"content":'+JSON.stringify(messages[turn-1])+'}}]}\r\n\r\n',
            event({delta:{},finish_reason:'stop'}).replaceAll('\n','\r\n'),
            'data: [DONE]\r\n\r\n'];
          for(const part of parts){res.write(part);await sleep(2);}
        }else if(scenario==='crlf_split'){
          // Split each CRLF across successive HTTP writes, not just JS strings.
          for(const part of base.replaceAll('\n','\r\n').split(/(?<=\r)(?=\n)/u)){
            res.write(part);await sleep(2);
          }
        }else{
          let body=base.replaceAll('\n',scenario==='unframed_crlf'?'\r\n':'\r');
          if(scenario==='unframed_cr')body=body.slice(0,-1);
          if(scenario==='unframed_crlf')body=body.slice(0,-2);
          for(const part of [body.slice(0,10),body.slice(10)]){
            res.write(part);await sleep(2);
          }
        }
        res.end();return;
      }
      for(let i=0;i<chunks.length;i++){
        if(scenario==='abort'&&i===3){res.destroy();return;}
        if(scenario==='stall'&&i===1){await sleep(100);res.destroy();return;}
        if(scenario==='repeat'&&i===4)chunks[i]+='data: [DONE]\n\n';
        if(scenario==='broken'&&i===3){res.end();return;}
        // Real HTTP chunk boundaries may split a UTF-8 emoji.
        const bytes=Buffer.from(chunks[i]);
        if(i===2){const p=bytes.length-3;res.write(bytes.subarray(0,p));await sleep(8);res.write(bytes.subarray(p));}
        else res.write(bytes);
        await sleep(6);
      }
      res.end();
    }catch{try{res.destroy();}catch{}}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port+'/nox/chat';
  try{return await handler(url,requests);}finally{
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
  }
}
const send=(url,turn,scenario='clean')=>{
  const startedAt=performance.now();
  return fetch(url,{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({turn,scenario})}).then(response=>({response,startedAt}));
};

test('R24 real loopback HTTP three sequential turns: Unicode, independent SHA and true EOF completion',async()=>{
  await withFixture(async(url,requests)=>{
    const proofs=[];
    for(let turn=1;turn<=3;turn++){
      const {response,startedAt}=await send(url,turn);
      const result=await measureSseResponse(response,{startedAt});proofs.push(result);
      assert.equal(result.verified,true);
      assert.ok(result.first_byte_ms>=0);
      assert.ok(result.ttft_ms>=result.first_byte_ms);
      assert.ok(result.completion_ms>=result.sse_done_ms);
      assert.ok(result.sse_done_ms>=result.ttft_ms);
      assert.equal(result.visible_text_sha256,hash(' \u0301'+messages[turn-1]));
      assert.equal(result.native_verified,false);
      assert.equal(result.browser_authenticated,false);
      assert.equal(result.canonical_s03_verified,false);
      assert.equal(result.model_tokens_per_second,null);
      assert.doesNotMatch(JSON.stringify(result),/Привет|Hola|三番目|data:/);
    }
    assert.equal(requests.length,3);
    assert.deepEqual(requests.map(p=>p.turn),[1,2,3]);
    assert.equal(new Set(proofs.map(p=>p.body_sha256)).size,3);
    assert.equal(new Set(proofs.map(p=>p.visible_text_sha256)).size,3);
  });
});

test('R24 third-turn abort, unframed EOF, duplicate DONE, and stalled SSE fail closed',async()=>{
  await withFixture(async(url,requests)=>{
    for(const [scenario,pattern] of [
      ['abort',/B4_INCOMPLETE_SSE|terminated|fetch failed/],
      ['broken',/B4_INCOMPLETE_SSE/],
      ['repeat',/B4_POST_DONE_EVENT/],
      ['stall',/B4_IDLE_TIMEOUT|terminated/]
    ]){
      const {response,startedAt}=await send(url,3,scenario);
      await assert.rejects(measureSseResponse(response,{startedAt,idleTimeoutMs:35}),pattern);
    }
    assert.equal(requests.length,4);
  });
});


test('R25 real HTTP loopback: lone CR, split CRLF, multiline SSE; incomplete terminal framing fails closed',async()=>{
  await withFixture(async(url,requests)=>{
    for(const [i,scenario] of ['cr_only','crlf_split','multiline'].entries()){
      const {response,startedAt}=await send(url,i+1,scenario);
      const result=await measureSseResponse(response,{startedAt});
      assert.equal(result.verified,true,scenario);
      assert.ok(result.first_byte_ms>=0 && result.ttft_ms>=result.first_byte_ms,scenario);
      assert.ok(result.completion_ms>=result.sse_done_ms && result.sse_done_ms>=result.ttft_ms,scenario);
      assert.equal(result.visible_text_sha256,hash(scenario==='multiline'?messages[i]:' \u0301'+messages[i]));
      assert.equal(result.browser_authenticated,false);
      assert.equal(result.native_verified,false);
      assert.equal(result.canonical_s03_verified,false);
    }
    for(const scenario of ['unframed_cr','unframed_crlf']){
      const {response,startedAt}=await send(url,3,scenario);
      await assert.rejects(measureSseResponse(response,{startedAt}),/B4_UNFRAMED_EOF/,scenario);
    }
    assert.deepEqual(requests.map(x=>x.scenario),
      ['cr_only','crlf_split','multiline','unframed_cr','unframed_crlf']);
  });
});


// R26: a noncompliant, never-settling cancellation cannot hide the
// original timeout or retain the standard ReadableStream reader lock.
const responseFor=reader=>({status:200,headers:new Headers({'content-type':'text/event-stream'}),body:{getReader:()=>reader}});
async function wallBound(promise,ms=180){
  let handle;
  try{return await Promise.race([promise,new Promise((_,reject)=>{handle=setTimeout(()=>reject(new Error('B4_TEST_HUNG_CANCEL')),ms);})]);}
  finally{clearTimeout(handle);}
}

test('R26 stuck ReadableStream.cancel settles idle/total deadline, releases real reader lock',async()=>{
  for(const [idle,total,code] of [[20,200,'B4_IDLE_TIMEOUT'],[120,20,'B4_TOTAL_TIMEOUT']]){
    const stream=new ReadableStream({start(){}});
    const reader=stream.getReader();
    const originalRead=reader.read.bind(reader);
    let pendingRead,cancelCount=0,releaseCount=0;
    reader.read=()=>{pendingRead=originalRead();return pendingRead;};
    reader.cancel=()=>{cancelCount++;return new Promise(()=>{});};
    const originalRelease=reader.releaseLock.bind(reader);
    reader.releaseLock=()=>{releaseCount++;return originalRelease();};
    const startedAt=performance.now();
    await assert.rejects(wallBound(measureSseResponse(responseFor(reader),{startedAt,idleTimeoutMs:idle,totalTimeoutMs:total})),e=>e.code===code);
    assert.equal(cancelCount,1);assert.equal(releaseCount,1);
    await assert.rejects(pendingRead,{name:'TypeError'});
    assert.doesNotThrow(()=>stream.getReader().releaseLock());
  }
});

test('R26 cancellation rejection/synchronous throw and lock exception preserve original error',async()=>{
  for(const cancelStyle of ['reject','throw']){
    let cancelCount=0,releaseCount=0;
    const reader={
      read:()=>new Promise(()=>{}),
      cancel:()=>{cancelCount++;if(cancelStyle==='throw')throw new Error('cancel-sync');return Promise.reject(new Error('cancel-reject'));},
      releaseLock:()=>{releaseCount++;throw new Error('release-failed');}
    };
    const startedAt=performance.now();
    await assert.rejects(wallBound(measureSseResponse(responseFor(reader),{startedAt,idleTimeoutMs:20,totalTimeoutMs:200})),e=>e.code==='B4_IDLE_TIMEOUT');
    assert.equal(cancelCount,1);assert.equal(releaseCount,1);
  }
});


// R27: settle a raced read AFTER the deadline and lock release. Even a
// complete, printable third SSE payload cannot revive an expired response.
test('R27 quarantines late reader success/rejection after idle/total deadline; third SSE turn never revives',async()=>{
  const unhandled=[];
  const onUnhandled=error=>unhandled.push(error);
  process.on('unhandledRejection',onUnhandled);
  try{
    const validThird=Buffer.from([
      'data: '+JSON.stringify({choices:[{delta:{content:'Третий ответ ✨'},finish_reason:null}]})+'\n\n',
      'data: '+JSON.stringify({choices:[{delta:{},finish_reason:'stop'}]})+'\n\n',
      'data: [DONE]\n\n'
    ].join(''));
    for(const [idle,total,expected,lateOutcome] of [
      [20,200,'B4_IDLE_TIMEOUT','resolve'],
      [20,200,'B4_IDLE_TIMEOUT','reject'],
      [200,20,'B4_TOTAL_TIMEOUT','resolve'],
      [200,20,'B4_TOTAL_TIMEOUT','reject']
    ]){
      let settleRead,readCount=0,cancelCount=0,releaseCount=0;
      const pending=new Promise((resolve,reject)=>{settleRead={resolve,reject};});
      const reader={
        read:()=>{readCount++;return pending;},
        cancel:()=>{cancelCount++;return Promise.resolve();},
        releaseLock:()=>{releaseCount++;}
      };
      const events=[];
      const measurement=measureSseResponse(responseFor(reader),{
        startedAt:performance.now(),idleTimeoutMs:idle,totalTimeoutMs:total
      }).then(value=>events.push({kind:'verified',value}),error=>events.push({kind:'failed',code:error.code}));
      await measurement;
      assert.deepEqual(events,[{kind:'failed',code:expected}],lateOutcome);
      assert.equal(cancelCount,1);assert.equal(releaseCount,1);
      assert.equal(readCount,1);
      if(lateOutcome==='resolve')settleRead.resolve({done:false,value:validThird});
      else settleRead.reject(new Error('R27_LATE_READ_FAILURE'));
      await sleep(0);await sleep(0);
      assert.deepEqual(events,[{kind:'failed',code:expected}],lateOutcome);
      assert.equal(readCount,1,'late data must not trigger a second read');
      assert.equal(cancelCount,1);assert.equal(releaseCount,1);
    }
    assert.deepEqual(unhandled,[],'raced late read reject must be observed');
  }finally{process.off('unhandledRejection',onUnhandled);}
});


// R28: heartbeat events repeatedly settle reads but must NEVER renew the
// absolute total deadline. A visible answer with STOP/DONE before the budget
// is still unverified if the transport EOF exceeds the same total deadline.
test('R28 total deadline survives heartbeat trickle; terminal/EOF boundary is fail-closed',async()=>{
  const sse=choice=>'data: '+JSON.stringify({choices:[choice]})+'\n\n';
  const printable=sse({delta:{content:'Третий ответ ✨'},finish_reason:null});
  const stop=sse({delta:{},finish_reason:'stop'});
  const done='data: [DONE]\n\n';
  const bytes=s=>Buffer.from(s);
  const slowReader=stages=>{
    let count=0,cancelCount=0,releaseCount=0;
    return {
      reader:{
        async read(){
          count++;
          const stage=stages.shift();
          if(!stage)return new Promise(()=>{});
          if(stage.delay)await sleep(stage.delay);
          return stage.value===null?{done:true}:{done:false,value:bytes(stage.value)};
        },
        cancel(){cancelCount++;return Promise.resolve();},
        releaseLock(){releaseCount++;}
      },
      stats:()=>({count,cancelCount,releaseCount})
    };
  };

  const heartbeats={count:0,cancel:0,release:0};
  const heartbeatReader={
    async read(){heartbeats.count++;await sleep(14);return {done:false,value:bytes(': heartbeat\n\n')};},
    cancel(){heartbeats.cancel++;return Promise.resolve();},
    releaseLock(){heartbeats.release++;}
  };
  await assert.rejects(measureSseResponse(responseFor(heartbeatReader),{
    startedAt:performance.now(),idleTimeoutMs:300,totalTimeoutMs:95
  }),e=>e.code==='B4_TOTAL_TIMEOUT');
  assert.ok(heartbeats.count>=3,'several heartbeats must arrive faster than idle budget');
  assert.equal(heartbeats.cancel,1);
  assert.equal(heartbeats.release,1);

  for(const [scenario,stages] of [
    ['DONE before deadline but EOF never delivered',[
      {delay:10,value:printable},{delay:10,value:stop},{delay:10,value:done}
    ]],
    ['STOP before deadline but DONE arrives after total deadline',[
      {delay:10,value:printable},{delay:10,value:stop},{delay:160,value:done}
    ]]
  ]){
    const {reader,stats}=slowReader(stages);
    await assert.rejects(measureSseResponse(responseFor(reader),{
      startedAt:performance.now(),idleTimeoutMs:300,totalTimeoutMs:95
    }),e=>e.code==='B4_TOTAL_TIMEOUT',scenario);
    assert.equal(stats().cancelCount,1,scenario);
    assert.equal(stats().releaseCount,1,scenario);
  }

  const {reader,stats}=slowReader([
    {delay:10,value:printable},{delay:10,value:stop},{delay:10,value:done},{delay:10,value:null}
  ]);
  const proof=await measureSseResponse(responseFor(reader),{
    startedAt:performance.now(),idleTimeoutMs:300,totalTimeoutMs:240
  });
  assert.equal(proof.verified,true);
  assert.ok(proof.first_byte_ms<=proof.ttft_ms);
  assert.ok(proof.ttft_ms<=proof.sse_done_ms);
  assert.ok(proof.sse_done_ms<=proof.completion_ms);
  assert.equal(proof.native_verified,false);
  assert.equal(proof.browser_authenticated,false);
  assert.equal(proof.canonical_s03_verified,false);
  assert.deepEqual(stats(),{count:4,cancelCount:0,releaseCount:1});
});

// R29: fetch() may hang before it yields HTTP headers. Bound that phase by
// the same request-start deadline as streaming. A late resolution is not proof.
test('R29 pre-header absolute deadline rejects stall/late settle; real loopback succeeds without replay',async()=>{
  let calls=0,aborts=0,cancels=0;
  await assert.rejects(measureSseFetch('http://fixture',{method:'POST'}, {
    totalTimeoutMs:20,fetchImpl:(_url,init)=>{
      calls++;init.signal.addEventListener('abort',()=>aborts++);
      return new Promise(()=>{});
    }
  }),e=>e.code==='B4_TOTAL_TIMEOUT');
  assert.equal(calls,1);assert.equal(aborts,1);
  const unhandled=[];const onUnhandled=e=>unhandled.push(e);
  process.on('unhandledRejection',onUnhandled);
  try{
    for(const kind of ['resolve','reject']){
      let settle;
      const pending=new Promise((resolve,reject)=>{settle={resolve,reject};});
      const measurement=measureSseFetch('http://fixture',{method:'POST'}, {
        totalTimeoutMs:20,fetchImpl:()=>pending
      });
      await assert.rejects(measurement,e=>e.code==='B4_TOTAL_TIMEOUT');
      if(kind==='resolve')settle.resolve({body:{cancel(){cancels++;return Promise.resolve();}}});
      else settle.reject(new Error('R29_LATE_HEADERS_FAILED'));
      await sleep(5);
    }
    assert.equal(cancels,1,'late headers must discard their body');
    assert.deepEqual(unhandled,[],'late reject must be observed');
  }finally{process.off('unhandledRejection',onUnhandled);}

  let requests=0;
  const server=createServer(async(req,res)=>{
    requests++;
    for await(const chunk of req){};
    if(req.url==='/slow')await sleep(100);
    if(res.destroyed)return;
    res.writeHead(200,{'content-type':'text/event-stream'});res.flushHeaders();
    res.write(event({delta:{content:'Третий ✨'},finish_reason:null}));
    res.write(event({delta:{},finish_reason:'stop'}));
    res.write('data: [DONE]\n\n');
    await sleep(5);res.end();
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try{
    const url='http://127.0.0.1:'+server.address().port;
    await assert.rejects(measureSseFetch(url+'/slow',{method:'POST',body:'{}'}, {
      totalTimeoutMs:30
    }),e=>e.code==='B4_TOTAL_TIMEOUT');
    const startedAt=performance.now();
    const proof=await measureSseFetch(url+'/good',{method:'POST',body:'{}'}, {
      startedAt,totalTimeoutMs:1500,idleTimeoutMs:900
    });
    assert.equal(proof.verified,true);
    assert.ok(proof.ttft_ms>=proof.first_byte_ms);
    assert.ok(proof.completion_ms>=proof.sse_done_ms);
    assert.equal(proof.browser_authenticated,false);
    assert.equal(proof.native_verified,false);
    assert.equal(requests,2,'no request replay after timeout');
  }finally{
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
  }
});

// R30: isolated regression for external AbortSignal and upstream fetch errors.
// Deliberately use a scope to keep helper symbols separate from earlier rounds.
{
const event=x=>'data: '+JSON.stringify({choices:[x]})+'\n\n';
const healthy=()=>new Response(new ReadableStream({start(c){
  c.enqueue(new TextEncoder().encode(event({delta:{content:'Привет!'},finish_reason:null})+
    event({delta:{},finish_reason:'stop'})+'data: [DONE]\n\n'));c.close();
}}),{status:200,headers:{'content-type':'text/event-stream'}});
const opts=fetchImpl=>({fetchImpl,totalTimeoutMs:400,idleTimeoutMs:120,startedAt:performance.now()});
const rejectedCode=(promise,code)=>assert.rejects(promise,e=>e?.code===code);
const freshWait=()=>sleep(0);

test('R30 external abort before/during headers and SSE, HTTP cleanup, transport rejection and success',async()=>{
  let calls=0;
  const before=new AbortController();before.abort();
  await rejectedCode(measureSseFetch('loopback',{signal:before.signal},opts(()=>{calls++;return healthy();})),'B4_FETCH_ABORTED');
  assert.equal(calls,0,'pre-aborted request never sends POST');
  await rejectedCode(measureSseFetch('loopback',{}, {...opts(()=>{calls++;return healthy();}),startedAt:performance.now()-1000,totalTimeoutMs:50}),'B4_TOTAL_TIMEOUT');
  assert.equal(calls,0,'stale-startedAt request never sends POST');

  const ctrl=new AbortController();
  let resolveHeaders,seenSignal,bodyCanceled=0;
  const headers=new Promise(resolve=>{resolveHeaders=resolve;});
  const duringHeaders=measureSseFetch('loopback',{method:'POST',signal:ctrl.signal},opts((_url,init)=>{
    calls++;seenSignal=init.signal;return headers;
  }));
  await freshWait();assert.equal(calls,1);
  assert.notEqual(seenSignal,ctrl.signal,'composed signal passed to fetch');
  ctrl.abort();
  await rejectedCode(duringHeaders,'B4_FETCH_ABORTED');
  assert.equal(seenSignal.aborted,true);
  resolveHeaders({body:{cancel(){bodyCanceled++;return Promise.resolve();}}});
  await freshWait();await freshWait();
  assert.equal(bodyCanceled,1,'late fetch body disposed exactly once');

  const mid=new AbortController();let canceled=0,released=0;
  let startedFetch=false;
  const streaming=measureSseFetch('loopback',{signal:mid.signal},opts(()=>{
    startedFetch=true;
    return {status:200,headers:new Headers({'content-type':'text/event-stream'}),body:{
      getReader(){return {read:()=>new Promise(()=>{}),cancel(){canceled++;return Promise.resolve();},releaseLock(){released++;}};},
      cancel(){return Promise.reject(new TypeError('locked'));}
    }};
  }));
  await freshWait();assert.equal(startedFetch,true);
  mid.abort();
  await rejectedCode(streaming,'B4_FETCH_ABORTED');

  for(const kind of ['throw','reject']){
    let count=0;
    const fetchImpl=()=>{count++;if(kind==='throw')throw new Error('transport');return Promise.reject(new Error('network'));};
    await rejectedCode(measureSseFetch('loopback',{},opts(fetchImpl)),'B4_FETCH_FAILED');
    assert.equal(count,1,'no automatic replay on transport error');
  }
  for(const [status,contentType] of [[503,'text/event-stream'],[200,'text/plain']]){
    let cleaned=0,count=0;
    const response={status,headers:new Headers({'content-type':contentType}),body:{
      getReader(){throw new Error('reader should not be called');},
      cancel(){cleaned++;return Promise.resolve();}
    }};
    await rejectedCode(measureSseFetch('loopback',{},opts(()=>{count++;return response;})),'B4_NOT_SSE_200');
    assert.equal(count,1);assert.equal(cleaned,1,'non-SSE body canceled');
  }
  const active=new AbortController();let successCalls=0;
  const measured=await measureSseFetch('loopback',{signal:active.signal},opts(()=>{successCalls++;return healthy();}));
  assert.equal(successCalls,1);assert.equal(measured.verified,true);
  assert.ok(measured.completion_ms>=measured.sse_done_ms);
  assert.ok(measured.sse_done_ms>=measured.ttft_ms);
  assert.equal(measured.native_verified,false);
  assert.equal(measured.browser_authenticated,false);
  assert.equal(measured.canonical_s03_verified,false);
  assert.equal(measured.model_tokens_per_second,null);
  await sleep(125); // let nonsettling fake SSE reader hit its OWN idle bound
  assert.equal(canceled,1);assert.equal(released,1);
});
}


// R31: Real TCP loopback HTTP, not synthetic ReadableStream/HTTP fixtures.
// A canceled second request (preheaders) or third request (mid UTF-8 frame)
// must NEVER produce an accepted answer, conceal socket failure, or replay POST.
const r31Event=choice=>'data: '+JSON.stringify({choices:[choice]})+'\n\n';
function r31Gate(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
async function r31Bound(p,ms=900){
  let timer;
  try{return await Promise.race([
    p,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('B4_R31_SOCKET_TIMEOUT')),ms);})
  ]);}finally{clearTimeout(timer);}
}
test('R31 true TCP HTTP second preheader abort and third mid-UTF8 SSE abort: no false completion, no replay',async()=>{
  const secondArrived=r31Gate(),thirdStarted=r31Gate(),secondClosed=r31Gate(),thirdClosed=r31Gate();
  const received=[];const unhandled=[];
  const onUnhandled=e=>unhandled.push(e);
  process.on('unhandledRejection',onUnhandled);
  const server=createServer(async(req,res)=>{
    if(req.method!=='POST'||req.url!=='/nox/chat'){res.writeHead(404).end();return;}
    let body='';for await(const chunk of req)body+=chunk;
    const {turn}=JSON.parse(body);received.push(turn);
    if(turn===2){res.once('close',()=>secondClosed.resolve());secondArrived.resolve();return;}
    res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store'});res.flushHeaders();
    if(turn===1){
      res.end(r31Event({delta:{content:'Привет 🌍'},finish_reason:null})+
        r31Event({delta:{},finish_reason:'stop'})+'data: [DONE]\n\n');
      return;
    }
    if(turn===3){
      res.once('close',()=>thirdClosed.resolve());
      res.write(r31Event({delta:{content:'Hola 🌈'},finish_reason:null}));
      const emoji=Buffer.from(r31Event({delta:{content:'Третий ✨'},finish_reason:null}));
      const cut=emoji.indexOf(Buffer.from('✨'));
      assert.ok(cut>0);
      res.write(emoji.subarray(0,cut+1)); // incomplete multibyte UTF-8 in actual TCP response
      thirdStarted.resolve();
      return; // no stop, no DONE, no EOF until caller aborts
    }
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port+'/nox/chat';
  const post=(turn,signal)=>measureSseFetch(url,{
    method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({turn}),signal
  },{startedAt:performance.now(),totalTimeoutMs:700,idleTimeoutMs:450});
  try{
    const first=await r31Bound(post(1));
    assert.equal(first.verified,true);
    assert.equal(first.browser_authenticated,false);
    assert.equal(first.native_verified,false);
    assert.equal(first.canonical_s03_verified,false);

    const before=new AbortController();
    const p2=post(2,before.signal);
    await r31Bound(secondArrived.promise);
    before.abort();
    await assert.rejects(r31Bound(p2),e=>e?.code==='B4_FETCH_ABORTED');
    await r31Bound(secondClosed.promise);

    const during=new AbortController();
    const p3=post(3,during.signal);
    await r31Bound(thirdStarted.promise);
    await sleep(15);
    during.abort();
    await assert.rejects(r31Bound(p3),e=>e?.code==='B4_FETCH_ABORTED');
    await r31Bound(thirdClosed.promise);
    await sleep(0);await sleep(0);
    assert.deepEqual(received,[1,2,3],'one POST per turn, no retry');
    assert.deepEqual(unhandled,[],'no late uncaught Promise rejection');
  }finally{
    server.closeAllConnections();
    await new Promise(resolve=>server.close(resolve));
    process.off('unhandledRejection',onUnhandled);
  }
});


// R32: real Node 22 HTTP/TCP Content-Length mismatch, not synthetic SSE read().
// STOP + [DONE] do NOT prove transport completion when advertised body is short.
const r32Hash=s=>createHash('sha256').update(s).digest('hex');
const r32Event=choice=>'data: '+JSON.stringify({choices:[choice]})+'\n\n';
const r32Visible=['Привет 🌍','Hola, мир 🌈','Третий ответ ✨'];
function r32Gate(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
async function r32Bound(p,ms=1500){
  let timer;
  try{return await Promise.race([p,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('B4_R32_HUNG')),ms);})]);}
  finally{clearTimeout(timer);}
}

test('R32 real TCP truncated Content-Length after stop+DONE cannot verify second/third SSE; healthy, deadlines, abort, size',async()=>{
  const arrived=r32Gate();
  const observed=[];
  const unhandled=[];
  const onUnhandled=e=>unhandled.push(e);
  process.on('unhandledRejection',onUnhandled);
  const server=createServer(async(req,res)=>{
    if(req.method!=='POST'||req.url!=='/nox/chat'){res.writeHead(404).end();return;}
    let input='';for await(const part of req)input+=part;
    const {turn,mode}=JSON.parse(input);
    observed.push({turn,mode});
    const body=Buffer.from(r32Event({delta:{content:r32Visible[turn-1]},finish_reason:null})+
      r32Event({delta:{},finish_reason:'stop'})+'data: [DONE]\n\n');
    res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store',
      'content-length':body.length+(mode==='healthy'||mode==='oversize'?0:37)});
    res.write(body,()=>{
      if(mode==='truncated')setTimeout(()=>res.destroy(),12);
      if(mode==='abort')arrived.resolve();
    });
    if(mode==='healthy'||mode==='oversize')res.end();
    // 'stall' and 'abort' deliberately never end: [DONE] is not TCP EOF.
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port+'/nox/chat';
  const post=(turn,mode,signal,options={})=>measureSseFetch(url,{
    method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({turn,mode}),signal
  },{startedAt:performance.now(),totalTimeoutMs:1000,idleTimeoutMs:650,...options});
  try{
    const healthy=await r32Bound(post(1,'healthy'));
    assert.equal(healthy.verified,true);
    assert.equal(healthy.visible_text_sha256,r32Hash(r32Visible[0]));
    assert.ok(healthy.first_byte_ms<=healthy.ttft_ms);
    assert.ok(healthy.ttft_ms<=healthy.sse_done_ms);
    assert.ok(healthy.sse_done_ms<=healthy.completion_ms);
    assert.equal(healthy.native_verified,false);
    assert.equal(healthy.browser_authenticated,false);
    assert.equal(healthy.canonical_s03_verified,false);

    for(const turn of [2,3]){
      await assert.rejects(r32Bound(post(turn,'truncated')),
        e=>e?.code==='B4_FETCH_FAILED',`turn ${turn} must reject truncated declared Content-Length`);
    }
    await assert.rejects(r32Bound(post(3,'stall',undefined,{totalTimeoutMs:105,idleTimeoutMs:700})),
      e=>e?.code==='B4_TOTAL_TIMEOUT','DONE without declared-length EOF cannot defeat absolute deadline');

    const aborter=new AbortController();
    const aborting=post(3,'abort',aborter.signal);
    await r32Bound(arrived.promise);
    aborter.abort();
    await assert.rejects(r32Bound(aborting),e=>e?.code==='B4_FETCH_ABORTED');

    await assert.rejects(r32Bound(post(2,'oversize',undefined,{maxTotalBytes:128})),
      e=>e?.code==='B4_STREAM_TOO_LARGE','body size cap still applies when HTTP Content-Length is correct');
    await sleep(10);await sleep(0);
    assert.deepEqual(observed,[
      {turn:1,mode:'healthy'},{turn:2,mode:'truncated'},
      {turn:3,mode:'truncated'},{turn:3,mode:'stall'},
      {turn:3,mode:'abort'},{turn:2,mode:'oversize'}
    ],'exactly one network POST for each explicit action; never replay');
    assert.deepEqual(unhandled,[],'no late uncaught errors on truncated transport');
  }finally{
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
    process.off('unhandledRejection',onUnhandled);
  }
});


// R33: HTTP/1.1 chunked framing is not complete until a real 0-chunk + EOF.
// A printable third turn with stop and [DONE] but a broken TCP transfer is NOT accepted.
const r33Event=choice=>'data: '+JSON.stringify({choices:[choice]})+'\n\n';
const r33Visible=['Привет 🌍','Hola, мир 🌈','Третий ответ ✨'];
const r33Hash=s=>createHash('sha256').update(s).digest('hex');
function r33Gate(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
async function r33Bound(p,ms=1500){
  let timer;try{return await Promise.race([p,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('B4_R33_HUNG')),ms);})]);}
  finally{clearTimeout(timer);}
}

test('R33 real TCP chunked missing zero terminator cannot verify second/third SSE; healthy, total deadline, abort, no replay',async()=>{
  const chunkSent=r33Gate();
  const observed=[];const unhandled=[];
  const onUnhandled=e=>unhandled.push(e);
  process.on('unhandledRejection',onUnhandled);
  const server=createServer(async(req,res)=>{
    if(req.method!=='POST'||req.url!=='/nox/chat'){res.writeHead(404).end();return;}
    let input='';for await(const part of req)input+=part;
    const {turn,mode}=JSON.parse(input);observed.push({turn,mode});
    const body=r33Event({delta:{content:r33Visible[turn-1]},finish_reason:null})+
      r33Event({delta:{},finish_reason:'stop'})+'data: [DONE]\n\n';
    res.writeHead(200,{'content-type':'text/event-stream',
      'cache-control':'no-store','transfer-encoding':'chunked'});
    res.flushHeaders();
    res.write(body,()=>{
      if(mode==='truncated')setTimeout(()=>res.destroy(),18); // NO terminating 0\r\n\r\n
      if(mode==='healthy')res.end(); // Node actually writes the zero chunk and EOF
      if(mode==='abort')chunkSent.resolve();
      // stall/abort keep the transfer open even after stop and [DONE]
    });
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port+'/nox/chat';
  const post=(turn,mode,signal,options={})=>measureSseFetch(url,{
    method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({turn,mode}),signal
  },{startedAt:performance.now(),totalTimeoutMs:950,idleTimeoutMs:600,...options});
  try{
    const proof=await r33Bound(post(1,'healthy'));
    assert.equal(proof.verified,true);
    assert.equal(proof.visible_text_sha256,r33Hash(r33Visible[0]));
    assert.ok(proof.first_byte_ms<=proof.ttft_ms&&proof.ttft_ms<=proof.sse_done_ms);
    assert.ok(proof.sse_done_ms<=proof.completion_ms);
    assert.equal(proof.native_verified,false);
    assert.equal(proof.browser_authenticated,false);
    assert.equal(proof.canonical_s03_verified,false);
    for(const turn of [2,3]){
      await assert.rejects(r33Bound(post(turn,'truncated')),
        e=>e?.code==='B4_FETCH_FAILED','turn '+turn+': stop+[DONE] must not override missing chunked terminal');
    }
    await assert.rejects(r33Bound(post(3,'stall',undefined,{totalTimeoutMs:105,idleTimeoutMs:500})),
      e=>e?.code==='B4_TOTAL_TIMEOUT','[DONE] cannot defeat request-start deadline while TCP has no 0-chunk');
    const controller=new AbortController();
    const aborted=post(3,'abort',controller.signal);
    await r33Bound(chunkSent.promise);
    controller.abort();
    await assert.rejects(r33Bound(aborted),e=>e?.code==='B4_FETCH_ABORTED');
    await new Promise(resolve=>setTimeout(resolve,12));
    assert.deepEqual(observed,[
      {turn:1,mode:'healthy'},{turn:2,mode:'truncated'},
      {turn:3,mode:'truncated'},{turn:3,mode:'stall'},
      {turn:3,mode:'abort'}
    ],'one POST per explicit action, no implicit replay');
    assert.deepEqual(unhandled,[],'no unhandled late transport rejection');
  }finally{
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
    process.off('unhandledRejection',onUnhandled);
  }
});
