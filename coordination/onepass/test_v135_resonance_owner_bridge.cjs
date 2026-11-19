/* Real-browser API contract fixture. Native OneHost itself is NOT simulated as proven live. */
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const file='coordination/onepass/nox-v135-resonance-owner-bridge.js';
const JS=fs.readFileSync(file,'utf8');
const id='abcd1234abcd1234abcd1234abcd1234';
const answer='Живой поток NOX';
const prompt='Привет, NOX';
function fake(owner=true,pathname='/nox-web-v29/pc/resonance.html',rejectReceipt=false,reply=answer,revision=3,raf,legacyIntl=false,firstDeltaAt=5,onHistory,historyExchangeId='verified-exchange-01',historyTail=[],stallHistoryBody=false,stallCreateBody=false,expectedQuestion=prompt,customIntl,presentation){
  const calls=[];
  let old=async (path,opts={})=>{
    const u=new URL(String(path),'https://nox.local');
    calls.push({path:u.pathname+u.search,method:opts.method||'GET',credentials:opts.credentials,signal:opts.signal});
    if(u.pathname==='/api/ui/memory/dialogs/create'){
      const body=JSON.parse(opts.body||'{}');
      assert.equal(body.confirmed,true);
      if(stallCreateBody)return new Response(new ReadableStream({start(){}}));
      return Response.json({dialog_id:id,title:body.title});
    }
    if(u.pathname==='/api/ui/memory/dialogs'){
      return Response.json({status:'READY',dialogs:[{dialog_id:id,title:'Тест',revision:2}]});
    }
    if(u.pathname==='/api/ui/memory/dialogs/history'){
      onHistory?.();
      if(stallHistoryBody)return new Response(new ReadableStream({start(){}}));
      return Response.json({status:'READY',dialog_id:id,messages:[
        {role:'user',exchange_id:historyExchangeId,content:expectedQuestion,ts:'2026-11-15T00:00:00Z'},
        {role:'assistant',exchange_id:historyExchangeId,content:reply,ts:'2026-11-15T00:00:01Z'}, ...historyTail]});
    }
    if(u.pathname==='/api/ui/memory/dialogs/update'){
      const b=JSON.parse(opts.body);
      assert.equal(b.revision,2);
      assert.equal(b.confirmed,true);
      return Response.json({dialog_id:id,title:b.title,revision});
    }
    if(u.pathname==='/api/nox/chat/stream'){
      const b=JSON.parse(opts.body);
      assert.equal(b.message,expectedQuestion);
      assert.equal(b.dialog_id,id);
      assert.deepEqual(b.history,[]);
      assert.equal(opts.credentials,'same-origin');
      const bytes=new TextEncoder();
      const stream=new ReadableStream({async start(ctrl){
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'})+'\n'));
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'start',model:'NOX HELION'})+'\n'));
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'delta',text:reply.slice(0,firstDeltaAt)})+'\n'));
        await new Promise(ok=>setTimeout(ok,110));
        if(opts.signal?.aborted){ctrl.close();return;}
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'delta',text:reply.slice(firstDeltaAt)})+'\n'));
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'done',saved:!rejectReceipt,
          s03_integrated:true,dialog_id:id,exchange_id:'verified-exchange-01',
          native_model_label:presentation?.receiptModelLabel})+'\n'));
        ctrl.close();
      }});
      return new Response(stream,{headers:{'content-type':'application/x-ndjson'}});
    }
    return new Response('NOT_NATIVE_ROUTE',{status:404});
  };
  const window={NOX_NATIVE_OWNER:owner,fetch:old};
  const location={pathname,href:'https://nox.local'+pathname,origin:'https://nox.local'};
  const context={window,location,URL,Request,Response,ReadableStream,
    TextDecoder,TextEncoder,AbortController,performance,console,requestAnimationFrame:raf};
  if(raf&&typeof raf==='object'){
    context.requestAnimationFrame=raf.requestAnimationFrame;
    context.cancelAnimationFrame=raf.cancelAnimationFrame;
    context.setTimeout=raf.setTimeout;
    context.clearTimeout=raf.clearTimeout;
  }
  if(legacyIntl)context.Intl={}; // emulate old browsers with no Intl.Segmenter
  if(customIntl)context.Intl=customIntl;
  if(presentation){context.document=presentation.document||{visibilityState:presentation.hidden?'hidden':'visible'};
    window.matchMedia=()=>({matches:!!presentation.reduced});}
  if(presentation?.onPhase){
    window.dispatchEvent=e=>presentation.onPhase(e.detail.phase);
    context.CustomEvent=class{constructor(type,opts){this.detail=opts.detail;}};
  }
  vm.runInNewContext(JS,context,{filename:file});
  return {fetch:(...args)=>window.fetch(...args),calls,window};
}
async function events(response){
  const rd=response.body.getReader(),decoder=new TextDecoder();let buf='',seen=[];
  while(true){
    const x=await rd.read();if(x.done)break;
    buf+=decoder.decode(x.value,{stream:true});
    let p;while((p=buf.indexOf('\n\n'))>=0){
      const e=buf.slice(0,p);buf=buf.slice(p+2);
      if(e.startsWith('data: '))seen.push(JSON.parse(e.slice(6)));
    }
  }
  return seen;
}
test('native V24 main Resonance streams tokens, only after S03 readback reports done',async()=>{
  const f=fake();
  const r=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:null,request_id:'v24-1'})});
  assert.equal(r.headers.get('content-type'),'text/event-stream');
  const reader=r.body.getReader();
  const d=new TextDecoder(),first=await reader.read();
  assert.equal(JSON.parse(d.decode(first.value).slice(6).trim()).type,'meta');
  const second=await reader.read();
  assert.equal(JSON.parse(d.decode(second.value).slice(6).trim()).type,'token');
  const list=[];
  while(true){const e=await reader.read();if(e.done)break;list.push(JSON.parse(d.decode(e.value).slice(6).trim()));}
  assert.equal(list.find(e=>e.type==='done').status,'done');
  assert.equal(list.find(e=>e.type==='done').history_persisted,true);
  assert.equal(list.filter(e=>e.type==='error').length,0);
  assert(f.calls.some(e=>e.path==='/api/nox/chat/stream'));
  assert(f.calls.some(e=>e.path.includes('/api/ui/memory/dialogs/history')));
});
test('native V24 fails closed on unverified S03 receipt, no false done',async()=>{
  const f=fake(true,'/nox-web-v29/pc/resonance.html',true);
  const r=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v24-2'})});
  const ev=await events(r);
  assert.equal(ev.filter(x=>x.type==='done').length,0);
  assert.equal(ev.filter(x=>x.type==='error').length,1);
});
test('legacy dialogs use original real owner S03 and no invented message counts',async()=>{
  const f=fake();
  const list=await (await f.fetch('/api/nox/history')).json();
  assert.equal(list.dialogs[0].id,id);
  assert.equal(list.dialogs[0].messages,'—');
  const h=await(await f.fetch('/api/nox/history?dialog_id='+id)).json();
  assert.equal(h.messages[1].content,answer);
  const c=await(await f.fetch('/api/nox/dialogs/new',{
    method:'POST',body:JSON.stringify({title:'Тест'})})).json();
  assert.equal(c.dialog_id,id);
  const n=await(await f.fetch('/api/nox/dialog/rename',{method:'POST',
    body:JSON.stringify({dialog_id:id,title:'Новое имя'})})).json();
  assert.equal(n.dialog_id,id);
  assert.equal(n.status,'READY','original V24 requires READY');
  assert.equal(n.revision,3);
});
test('V24 rename rejects unchanged S03 revision and never reports false READY',async()=>{
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,2);
  const r=await f.fetch('/api/nox/dialog/rename',{method:'POST',body:JSON.stringify({dialog_id:id,title:'Новое имя'})});
  assert.equal(r.status,503);
  const j=await r.json();
  assert.equal(j.status,'HOLD');
  assert.match(j.error,/HOLD_RENAME_RECEIPT/);
  assert.equal(f.calls.filter(x=>x.path==='/api/ui/memory/dialogs/update').length,1);
});

test('not installed for anonymous pages, foreign origin, or non-Resonance',async()=>{
  for(const [owner,path] of [[false,'/nox-web-v29/pc/resonance.html'],[true,'/pc/resonance.html'],[true,'/nox-web-v29/chat.html']]){
    const f=fake(owner,path);
    const r=await f.fetch('/api/nox/chat',{method:'POST',body:'{}'});
    assert.equal(r.status,404);
    assert.equal(f.window.__NOX_V135_OWNER_RESONANCE,undefined);
  }
  const f=fake();
  const r=await f.fetch('https://other.host/api/nox/chat',{method:'POST',body:'{}'});
  assert.equal(r.status,404);
});
test('invalid dialog scope cannot leak into another existing owner dialog',async()=>{
  const f=fake();
  const r=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:'old-browser-id',request_id:'v24-3'})});
  const ev=await events(r);
  assert.equal(ev.filter(x=>x.type==='done').length,0);
  assert(ev.some(x=>x.type==='error'&&/HOLD_INVALID_DIALOG_SCOPE/.test(x.error)));
  assert(!f.calls.some(x=>x.path==='/api/nox/chat/stream'));
});
test('SSE bytes arrive before terminal event, without buffering full reply',async()=>{
  const f=fake();
  const t=performance.now();
  const resp=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v24-4'})});
  const rd=resp.body.getReader();
  const first=await rd.read(),second=await rd.read();
  assert(first.value&&second.value);
  assert(performance.now()-t<95,'must emit actual delta before delayed model completion');
  await rd.cancel();
});

test('V135 SSE user cancel aborts the SAME native stream (no global STOP)',async()=>{
  const f=fake();
  const response=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'cancel-01'})});
  const reader=response.body.getReader();
  assert((await reader.read()).value,'real owner meta');
  assert((await reader.read()).value,'first delta before completion');
  const calls=f.calls.filter(c=>c.path==='/api/nox/chat/stream');
  assert.equal(calls.length,1);
  assert(calls[0].signal && !calls[0].signal.aborted);
  await reader.cancel('user closed Resonance stream');
  assert.equal(calls[0].signal.aborted,true,'native fetch must abort on downstream cancel');
  assert.equal(f.calls.some(c=>c.path==='/api/nox/stop'),false,
    'never send global stop for scoped browser stream');
});
test('V135 already-aborted caller never starts a native inference',async()=>{
  const f=fake(),abort=new AbortController();
  abort.abort();
  const response=await f.fetch('/api/nox/chat',{method:'POST',signal:abort.signal,
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'cancel-02'})});
  const frames=await events(response);
  assert.equal(frames.filter(e=>e.type==='done').length,0);
  assert(frames.some(e=>e.type==='error'&&e.error==='STREAM_STOP_REQUESTED'));
  assert(!f.calls.some(c=>c.path==='/api/nox/chat/stream'));
});

test('V136 received long model delta is emitted in small ordered real pieces', async () => {
  const actual='Ж'.repeat(300)+'🧠'+'NOX'.repeat(105);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,actual);
  const r=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v136-pieces'})});
  const eventsRead=await events(r);
  const parts=eventsRead.filter(e=>e.type==='token').map(e=>e.t);
  assert(parts.length>8,'large native delta must not render as a single full answer');
  assert(parts.every(s=>Array.from(s).length<=24),'split should keep small actual pieces');
  assert.equal(parts.join(''),actual,'no lost, duplicated or fabricated text');
  assert.equal(eventsRead.filter(e=>e.type==='done').length,1);
  assert.equal(eventsRead.at(-1).type,'done');
});

test('V137 received pieces appear across real paint frames, not only at done',async()=>{
  let frames=0;
  const render=cb=>{frames++;setTimeout(()=>cb(performance.now()),2);};
  const text='Z'.repeat(300);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,text,3,render);
  const r=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'progressive-frames'})});
  const reader=r.body.getReader(),dec=new TextDecoder();
  const initial=await reader.read(),first=await reader.read();
  assert.equal(JSON.parse(dec.decode(initial.value).slice(6).trim()).type,'meta');
  assert.equal(JSON.parse(dec.decode(first.value).slice(6).trim()).type,'token');
  const others=[];
  while(true){
    const chunk=await reader.read();if(chunk.done)break;
    others.push(JSON.parse(dec.decode(chunk.value).slice(6).trim()));
  }
  assert(frames>=2&&frames<=7,'bounded animation frames are used only for actual native pieces');
  const pieces=[JSON.parse(dec.decode(first.value).slice(6).trim()),...others].filter(x=>x.type==='token');
  assert.equal(pieces.map(x=>x.t).join(''),text);
  assert.equal(others.at(-1).type,'done');
});

test('V141 Request-object POST still reaches original owner SSE + durable S03 gate',async()=>{
  const f=fake();
  const req=new Request('https://nox.local/api/nox/chat',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'request-object-01'})
  });
  const response=await f.fetch(req);
  assert.equal(response.headers.get('content-type'),'text/event-stream');
  const frames=await events(response);
  assert.equal(frames.filter(x=>x.type==='done').length,1);
  assert(f.calls.some(x=>x.path==='/api/nox/chat/stream'));
  assert(!f.calls.some(x=>x.path==='/api/nox/chat'));
});
test('V141 Request-object GET history and non-owner routes remain scoped',async()=>{
  const f=fake();
  const response=await f.fetch(new Request('https://nox.local/api/nox/history'));
  assert.equal(response.status,200);
  const data=await response.json();
  assert.equal(data.dialogs[0].id,id);
  assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs?')));
  assert(!f.calls.some(x=>x.path==='/api/nox/history'));
  const unrelated=await f.fetch(new Request('https://nox.local/api/not-nox'));
  assert.equal(unrelated.status,404);
});
test('V141 Request-object aborted input cannot start native inference',async()=>{
  const f=fake(),controller=new AbortController();
  const req=new Request('https://nox.local/api/nox/chat',{
    method:'POST',signal:controller.signal,
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'request-object-02'})
  });
  controller.abort();
  const response=await f.fetch(req);
  const frames=await events(response);
  assert.equal(frames.filter(x=>x.type==='done').length,0);
  assert(!f.calls.some(x=>x.path==='/api/nox/chat/stream'));
});

test('V153 SSE tokens preserve real grapheme boundaries in original owner stream',async()=>{
  // The fixture streams five ASCII characters, then emoji ZWJ and accent
  // clusters. Splitting by codepoint visibly tears both during paint.
  const combined='abcde'+('e\u0301'+'👨‍👩‍👧‍👦').repeat(13);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,combined);
  const r=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v153-grapheme'})});
  const read=await events(r);
  const pieces=read.filter(e=>e.type==='token').map(e=>e.t);
  assert(pieces.length>=2,'must deliver actual pieces before S03 done');
  assert.equal(pieces.join(''),combined,'never change or fabricate the reply');
  let offset=0;
  const boundaries=new Set();
  for(const g of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(combined)){
    offset+=g.segment.length;
    boundaries.add(offset);
  }
  let cumulative=0;
  for(const part of pieces){
    cumulative+=part.length;
    assert(boundaries.has(cumulative),'a visual token ended inside a grapheme');
  }
  assert.equal(read.filter(e=>e.type==='done').length,1);
  assert(f.calls.some(c=>c.path.startsWith('/api/ui/memory/dialogs/history?')),
    'real S03 readback must still gate success');
});

test('V154 without Intl.Segmenter never splits a native delta within a grapheme',async()=>{
  // E1 V153 protected Segmenter browsers. Its old codepoint fallback still
  // tears compound ZWJ emoji and combining accents in legacy browsers.
  const combined='abcde'+('e\u0301'+'👨‍👩‍👧‍👦').repeat(13);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,combined,3,undefined,true);
  const response=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v154-legacy-intl'})});
  const read=await events(response);
  const pieces=read.filter(x=>x.type==='token').map(x=>x.t);
  assert.equal(pieces.join(''),combined,'native answer must remain unaltered');
  // Without a segmenter, native Unicode clusters remain buffered, but
  // guaranteed ASCII prefixes may be streamed safely before completion.
  assert(pieces.length>=2,'legacy stream shows a safe ASCII prefix before terminal done');
  assert.equal(pieces[0],'abcd','boundary-adjacent ASCII glyph must remain buffered');
  let offset=0;
  const boundaries=new Set();
  for(const g of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(combined)){
    offset+=g.segment.length;
    boundaries.add(offset);
  }
  offset=0;
  for(const piece of pieces){
    offset+=piece.length;
    assert(boundaries.has(offset),'legacy visual token ends inside a grapheme');
  }
  assert.equal(read.filter(x=>x.type==='done').length,1);
  assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')),
    'S03 owner history readback must still gate done');
});

test('V155 grapheme may span native NDJSON delta boundary; never tear at that edge',async()=>{
  const combined='prefix👨‍👩‍👧‍👦suffix e\u0301 done';
  const split=combined.indexOf('👨')+3; // first native frame ends with man+ZWJ
  for(const legacyIntl of [false,true]){
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,combined,3,undefined,legacyIntl,split);
    const response=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v155-cross-delta'})});
    const read=await events(response);
    const tokens=read.filter(x=>x.type==='token').map(x=>x.t);
    assert.equal(tokens.join(''),combined,'native text must stay byte-for-byte identical');
    const boundaries=new Set();let offset=0;
    for(const s of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(combined)){
      offset+=s.segment.length;boundaries.add(offset);
    }
    offset=0;
    for(const token of tokens){offset+=token.length;
      assert(boundaries.has(offset),'token ended inside a native cross-delta grapheme');
    }
    if(legacyIntl){
      assert(tokens.length>=2,'legacy streams only a guaranteed ASCII prefix');
      assert.equal(tokens[0],'prefi','retain ASCII boundary character before uncertain Unicode');
    }
    else assert(tokens.length>=2,'modern browser still streams genuine prefix before native done');
    assert.equal(read.filter(x=>x.type==='done').length,1);
    assert.equal(read.find(x=>x.type==='done').history_persisted,true);
    assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
  }
});

test('V170 legacy browser emits genuine safe ASCII delta before native done and S03',async()=>{
  const text='ASCII stream with two native fragments';
  let historyReached=false;
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,text,3,undefined,true,8,
    ()=>{historyReached=true;});
  const response=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v170-legacy-stream'})});
  const reader=response.body.getReader(),decoder=new TextDecoder();
  const frame=async()=>{
    const part=await reader.read();
    assert.equal(part.done,false,'genuine upstream event expected');
    return JSON.parse(decoder.decode(part.value).slice(6).trim());
  };
  assert.equal((await frame()).type,'meta');
  const first=await frame();
  assert.equal(first.type,'token','legacy browser must not buffer entire answer');
  assert.equal(first.t,text.slice(0,7),'emit only safe seven-char prefix');
  assert.equal(historyReached,false,'first token must precede exact S03 history readback');
  const tail=[];
  for(;;){
    const part=await reader.read();
    if(part.done)break;
    tail.push(JSON.parse(decoder.decode(part.value).slice(6).trim()));
  }
  assert.equal([first,...tail].filter(e=>e.type==='token').map(e=>e.t).join(''),text);
  assert.equal(tail.filter(e=>e.type==='done').length,1);
  assert.equal(tail.at(-1).history_persisted,true);
  assert.equal(historyReached,true,'terminal done still gated by S03 history');
  assert.equal(f.calls.filter(e=>e.path==='/api/nox/chat/stream').length,1);
});

test('V156 coalesced native NDJSON keeps valid short frames and rejects one oversized frame',async()=>{
  const id='abcd1234abcd1234abcd1234abcd1234';
  const piece='Ж'.repeat(22),count=7000,prompt='Coalesced native frame audit';
  const answer=piece.repeat(count);
  const upstreamStart=JSON.stringify({type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'})+'\n'+
    JSON.stringify({type:'start',model:'NOX HELION'})+'\n';
  const valid=upstreamStart+Array.from({length:count},()=>JSON.stringify({type:'delta',text:piece})+'\n').join('')+
    JSON.stringify({type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:'coalesced-qa-01'})+'\n';
  assert(valid.length>300000&&answer.length<200000,'valid source-level stress fixture');
  const tooLong=upstreamStart+JSON.stringify({type:'delta',text:'small',unused:'x'.repeat(300100)})+'\n';
  async function run(nativeFrames){
    const calls=[];
    const upstream=async path=>{
      const u=new URL(String(path),'https://nox.local');calls.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')
        return Response.json({dialog_id:id,title:'QA'});
      if(u.pathname==='/api/ui/memory/dialogs/history')
        return Response.json({status:'READY',dialog_id:id,messages:[
          {role:'user',exchange_id:'coalesced-qa-01',content:prompt},{role:'assistant',exchange_id:'coalesced-qa-01',content:answer}]});
      if(u.pathname==='/api/nox/chat/stream'){
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(nativeFrames));c.close();
        }}),{headers:{'content-type':'application/x-ndjson'}});
      }
      return new Response('NOT_NATIVE_ROUTE',{status:404});
    };
    const win={NOX_NATIVE_OWNER:true,fetch:upstream};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',
      href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
    vm.runInNewContext(JS,{window:win,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout,
      requestAnimationFrame:cb=>cb(performance.now())});
    const response=await win.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt})});
    return {response,json:await response.json(),calls};
  }
  const good=await run(valid);
  assert.equal(good.response.status,200,'coalesced valid frames are not oversized frames');
  assert.equal(good.json.answer,answer,'lossless native answer');
  assert.equal(good.json.history_persisted,true,'native S03 history still gates completion');
  assert(good.calls.includes('/api/ui/memory/dialogs/history'));
  const bad=await run(tooLong);
  assert.equal(bad.response.status,503,'one oversized native frame must fail closed');
  assert.match(bad.json.error,/HOLD_NATIVE_FRAME_TOO_LARGE/);
  assert(!bad.calls.includes('/api/ui/memory/dialogs/history'),'no S03 success on oversized frame');
});


test('V157 native done is terminal: reject trailing control frame before S03 READY',async()=>{
  const did='abcd1234abcd1234abcd1234abcd1234',prompt='V157 terminal NDJSON audit';
  const answer='Native verified reply';
  const delta=JSON.stringify({type:'delta',text:answer})+'\n';
  const done=JSON.stringify({type:'done',saved:true,s03_integrated:true,
    dialog_id:did,exchange_id:'v157-receipt-001'})+'\n';
  const unexpected=JSON.stringify({type:'start',model:'unexpected after commit'})+'\n';
  async function attempt(payload){
    const called=[];
    const original=async path=>{
      const u=new URL(String(path),'https://nox.local');called.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')
        return Response.json({dialog_id:did,title:'V157'});
      if(u.pathname==='/api/ui/memory/dialogs/history')
        return Response.json({status:'READY',dialog_id:did,messages:[
          {role:'user',exchange_id:'v157-receipt-001',content:prompt},{role:'assistant',exchange_id:'v157-receipt-001',content:answer}]});
      if(u.pathname==='/api/nox/chat/stream')
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(payload));c.close();
        }}),{headers:{'content-type':'application/x-ndjson'}});
      return new Response('NO_MATCH',{status:404});
    };
    const w={NOX_NATIVE_OWNER:true,fetch:original};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',
      href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout,
      requestAnimationFrame:cb=>cb(performance.now())});
    const r=await w.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt})});
    return {status:r.status,body:await r.json(),called};
  }
  const start=JSON.stringify({type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'})+'\n'+
    JSON.stringify({type:'start',model:'NOX HELION'})+'\n';
  const clean=await attempt(start+delta+done+'\n');
  assert.equal(clean.status,200,'native done plus blank line is permitted');
  assert.equal(clean.body.history_persisted,true);
  assert(clean.called.includes('/api/ui/memory/dialogs/history'));
  const bad=await attempt(start+delta+done+unexpected);
  assert.equal(bad.status,503,'a control frame after done must fail closed');
  assert.match(bad.body.error,/HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE/);
  assert.equal(bad.body.history_persisted,false,'never claim persisted on invalid protocol');
  assert(!bad.called.includes('/api/ui/memory/dialogs/history'),
    'reject before accepting an invalid terminal receipt');
});


test('V158 unknown or missing native event before done cannot report persisted S03',async()=>{
  const p='V158 unexpected protocol event',a='Verifiable original reply';
  const good=[
    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
    {type:'start',model:'NOX HELION'},
    {type:'delta',text:a},
    {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:'v158-receipt-001'}
  ];
  async function run(frames){
    const calls=[];
    const original=async path=>{
      const u=new URL(String(path),'https://nox.local');calls.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')return Response.json({dialog_id:id,title:'V158'});
      if(u.pathname==='/api/ui/memory/dialogs/history')return Response.json({
        status:'READY',dialog_id:id,messages:[{role:'user',exchange_id:'v158-receipt-001',content:p},{role:'assistant',exchange_id:'v158-receipt-001',content:a}]
      });
      if(u.pathname==='/api/nox/chat/stream')
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(frames.map(x=>JSON.stringify(x)+'\n').join('')));
          c.close();
        }}),{headers:{'content-type':'application/x-ndjson'}});
      return new Response('NO_MATCH',{status:404});
    };
    const w={NOX_NATIVE_OWNER:true,fetch:original};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',
      href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const r=await w.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({message:p})});
    return {status:r.status,result:await r.json(),calls};
  }
  const valid=await run(good);
  assert.equal(valid.status,200,'documented preparing/start frames remain valid');
  assert.equal(valid.result.history_persisted,true);
  assert(valid.calls.includes('/api/ui/memory/dialogs/history'));
  for(const unexpected of [{type:'unexpected_native_admin'}, {payload:'missing type'}]){
    const bad=await run([good[0],unexpected,...good.slice(1)]);
    assert.equal(bad.status,503,'unknown native event must fail closed');
    assert.match(bad.result.error,/HOLD_NATIVE_UNKNOWN_FRAME/);
    assert.equal(bad.result.history_persisted,false);
    assert(!bad.calls.includes('/api/ui/memory/dialogs/history'),
      'never perform S03 acceptance on unrecognized native event');
  }
});

test('V159 require real native start before delta/done and reject duplicate start',async()=>{
  // Existing V112 OneHost emits preparing -> start -> delta -> done.
  // A fake/incomplete startless sequence must never become an S03 success.
  const p='V159 start contract',a='Valid upstream answer';
  const good=[
    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
    {type:'start',model:'NOX HELION'},
    {type:'delta',text:a},
    {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:'v159-real-start-001'}
  ];
  async function run(frames){
    const called=[];
    const original=async path=>{
      const u=new URL(String(path),'https://nox.local');called.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')
        return Response.json({dialog_id:id,title:'V159'});
      if(u.pathname==='/api/ui/memory/dialogs/history')
        return Response.json({status:'READY',dialog_id:id,messages:[
          {role:'user',exchange_id:'v159-real-start-001',content:p},{role:'assistant',exchange_id:'v159-real-start-001',content:a}]});
      if(u.pathname==='/api/nox/chat/stream')
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(frames.map(x=>JSON.stringify(x)+'\n').join('')));
          c.close();
        }}),{headers:{'content-type':'application/x-ndjson'}});
      return new Response('NO_NATIVE_ROUTE',{status:404});
    };
    const w={NOX_NATIVE_OWNER:true,fetch:original};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',
      href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const r=await w.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:p})});
    return {status:r.status,result:await r.json(),called};
  }
  const valid=await run(good);
  assert.equal(valid.status,200,'original OneHost start sequence must pass');
  assert.equal(valid.result.history_persisted,true);
  assert(valid.called.includes('/api/ui/memory/dialogs/history'));
  const invalid=[
    {frames:[good[2],good[3]],error:/HOLD_NATIVE_START_REQUIRED/},
    {frames:[good[0],good[2],good[3]],error:/HOLD_NATIVE_START_REQUIRED/},
    {frames:[good[0],good[3]],error:/HOLD_NATIVE_START_REQUIRED/},
    {frames:[good[0],good[1],good[1],good[2],good[3]],
     error:/HOLD_DUPLICATE_NATIVE_START/}
  ];
  for(const x of invalid){
    const bad=await run(x.frames);
    assert.equal(bad.status,503,'invalid native start contract must fail closed');
    assert.match(bad.result.error,x.error);
    assert.equal(bad.result.history_persisted,false);
    assert(!bad.called.includes('/api/ui/memory/dialogs/history'),
      'reject before S03 acceptance on invalid protocol');
  }
});


test('V160 preparing is unique and precedes native start; reject before S03 readback',async()=>{
  const prompt='V160 preparing order',answer='Upstream token';
  const good=[
    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
    {type:'start',model:'NOX HELION',stream_mode:'NATIVE_TOKEN_STREAM'},
    {type:'delta',text:answer},
    {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:'v160-order-001'}
  ];
  async function attempt(events){
    const calls=[];
    const original=async path=>{
      const u=new URL(String(path),'https://nox.local');calls.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')
        return Response.json({dialog_id:id,title:'V160'});
      if(u.pathname==='/api/ui/memory/dialogs/history')
        return Response.json({status:'READY',dialog_id:id,messages:[
          {role:'user',exchange_id:'v160-order-001',content:prompt},{role:'assistant',exchange_id:'v160-order-001',content:answer}]});
      if(u.pathname==='/api/nox/chat/stream')
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(events.map(e=>JSON.stringify(e)+'\n').join('')));
          c.close();
        }}),{headers:{'content-type':'application/x-ndjson'}});
      return new Response('NO_NATIVE_ROUTE',{status:404});
    };
    const w={NOX_NATIVE_OWNER:true,fetch:original};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',
      href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const r=await w.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt})});
    return {status:r.status,result:await r.json(),calls};
  }
  const normal=await attempt(good);
  assert.equal(normal.status,200,'original V112 sequence accepted');
  assert.equal(normal.result.history_persisted,true);
  assert(normal.calls.includes('/api/ui/memory/dialogs/history'));
  const invalid=[
    [good[0],good[0],good[1],good[2],good[3]],
    [good[0],good[1],good[0],good[2],good[3]],
    [good[0],good[1],good[2],good[0],good[3]],
  ];
  for(const frames of invalid){
    const bad=await attempt(frames);
    assert.equal(bad.status,503,'invalid native preparing order must HOLD');
    assert.match(bad.result.error,/HOLD_NATIVE_PREPARING_ORDER/);
    assert.equal(bad.result.history_persisted,false);
    assert(!bad.calls.includes('/api/ui/memory/dialogs/history'),
      'invalid stream must never enter owner S03 acceptance');
  }
});


test('V161 missing native preparing cannot become persisted S03 success',async()=>{
  // The original V112 producer ALWAYS sends preparing before start.
  // Missing preparing is not evidence of a valid original OneHost stream.
  const p='V161 native preparing requirement',a='Verified upstream';
  const full=[
    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
    {type:'start',model:'NOX HELION'},
    {type:'delta',text:a},
    {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:'v161-native-receipt'}
  ];
  async function check(frames){
    const calls=[];
    const old=async path=>{
      const u=new URL(String(path),'https://nox.local');calls.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')
        return Response.json({dialog_id:id,title:'V161'});
      if(u.pathname==='/api/ui/memory/dialogs/history')
        return Response.json({status:'READY',dialog_id:id,messages:[
          {role:'user',exchange_id:'v161-native-receipt',content:p},{role:'assistant',exchange_id:'v161-native-receipt',content:a}]});
      if(u.pathname==='/api/nox/chat/stream')
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(frames.map(x=>JSON.stringify(x)+'\n').join('')));
          c.close();
        }}),{headers:{'content-type':'application/x-ndjson'}});
      return new Response('NO_ROUTE',{status:404});
    };
    const w={NOX_NATIVE_OWNER:true,fetch:old};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',
      href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const response=await w.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:p})});
    return {status:response.status,json:await response.json(),calls};
  }
  const good=await check(full);
  assert.equal(good.status,200);
  assert.equal(good.json.history_persisted,true);
  assert(good.calls.includes('/api/ui/memory/dialogs/history'));
  for(const frames of [full.slice(1),[full[1],full[3]]]){
    const bad=await check(frames);
    assert.equal(bad.status,503,'missing native preparing must HOLD');
    assert.match(bad.json.error,/HOLD_NATIVE_PREPARING_REQUIRED/);
    assert.equal(bad.json.history_persisted,false);
    assert(!bad.calls.includes('/api/ui/memory/dialogs/history'),
      'no original S03 acceptance after missing native preparing');
  }
});


test('V162 original native preparing mode must match V112 before S03 acceptance',async()=>{
  const question='V162 strict original stream mode',answer='Original native response';
  async function run(mode){
    const calls=[];
    const frames=[
      mode===undefined?{type:'preparing'}:{type:'preparing',stream_mode:mode},
      {type:'start',model:'NOX HELION',stream_mode:'NATIVE_TOKEN_STREAM'},
      {type:'delta',text:answer},
      {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:'v162-mode-001'}
    ];
    const native=async path=>{
      const u=new URL(String(path),'https://nox.local');
      calls.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')
        return Response.json({dialog_id:id,title:'V162'});
      if(u.pathname==='/api/ui/memory/dialogs/history')
        return Response.json({status:'READY',dialog_id:id,messages:[
          {role:'user',exchange_id:'v162-mode-001',content:question},{role:'assistant',exchange_id:'v162-mode-001',content:answer}]});
      if(u.pathname==='/api/nox/chat/stream')
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(frames.map(e=>JSON.stringify(e)+'\n').join('')));
          c.close();
        }}),{headers:{'content-type':'application/x-ndjson'}});
      return new Response('NO_NATIVE_ROUTE',{status:404});
    };
    const w={NOX_NATIVE_OWNER:true,fetch:native};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',
      href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const r=await w.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:question})});
    return {status:r.status,json:await r.json(),calls};
  }
  const good=await run('NATIVE_TOKEN_STREAM');
  assert.equal(good.status,200,'documented V112 mode must remain accepted');
  assert.equal(good.json.history_persisted,true);
  assert(good.calls.includes('/api/ui/memory/dialogs/history'));
  for(const mode of [undefined,null,'SSE_FALLBACK','NATIVE_BUFFER_ONLY']){
    const bad=await run(mode);
    assert.equal(bad.status,503,'invalid V112 stream mode must HOLD');
    assert.match(bad.json.error,/HOLD_NATIVE_STREAM_MODE/);
    assert.equal(bad.json.history_persisted,false);
    assert(!bad.calls.includes('/api/ui/memory/dialogs/history'),
      'no S03 success/readback for missing or incorrect original native mode');
  }
});

test('V163 JSON cancellation during S03 readback never reports persisted success',async()=>{
  // Original jsonChat path has no dialog_id or request_id: it creates a dialog.
  // Abort exactly when the native owner history route is consulted, after
  // model output and receipt have arrived. This reproduces the stale success.
  const ctrl=new AbortController();
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,
    undefined,false,5,()=>ctrl.abort());
  const response=await f.fetch('/api/nox/chat',{
    method:'POST',signal:ctrl.signal,body:JSON.stringify({message:prompt})
  });
  assert.equal(response.status,503,'a canceled JSON request cannot report durable success');
  const result=await response.json();
  assert.equal(result.history_persisted,false);
  assert.equal(result.s03_integrated,false);
  assert.match(result.error,/STREAM_STOP_REQUESTED/);
  assert(f.calls.some(c=>c.path.startsWith('/api/ui/memory/dialogs/history?')),
    'race must occur at real history readback boundary');
  assert(!f.calls.some(c=>c.path==='/api/nox/stop'),
    'do not send global STOP for a JSON request abort');
});


test('V164 S03 readback must bind BOTH saved rows to the native receipt exchange ID',async()=>{
  // A previously committed identical prompt and answer cannot prove THIS
  // generation was durably written. Missing IDs also fail closed.
  for(const staleExchange of ['previous-exchange-01',null]){
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,
      undefined,false,5,undefined,staleExchange);
    const json=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt})});
    assert.equal(json.status,503,'JSON cannot accept stale or untagged S03 rows');
    const failed=await json.json();
    assert.equal(failed.history_persisted,false);
    assert.equal(failed.s03_integrated,false);
    assert.match(failed.error,/HOLD_DIALOG_HISTORY_READBACK/);
    const stream=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v164-s03-identity'})});
    const frames=await events(stream);
    assert(!frames.some(x=>x.type==='done'),'SSE cannot claim a stale exchange');
    assert(frames.some(x=>x.type==='error'&&/HOLD_DIALOG_HISTORY_READBACK/.test(x.error)));
    assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
    assert(!f.calls.some(x=>x.path==='/api/nox/stop'),'do not send global STOP');
  }
});

test('V166 exact S03 receipt survives newer independent rows in the same dialog',async()=>{
  // Concurrent owner requests can finish after this exchange is persisted.
  // Readback must search bounded history for the exact exchange_id; never
  // accept a different exchange, even with identical prompt and answer.
  const newer=[
    {role:'user',exchange_id:'newer-exchange-02',content:'Другой вопрос'},
    {role:'assistant',exchange_id:'newer-exchange-02',content:'Другой ответ'}
  ];
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,
    undefined,false,5,undefined,'verified-exchange-01',newer);
  const json=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt})});
  assert.equal(json.status,200,'a verified earlier exchange remains persisted');
  assert.equal((await json.json()).history_persisted,true);
  const stream=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v166-concurrent-01'})});
  const frames=await events(stream);
  assert.equal(frames.filter(e=>e.type==='done').length,1);
  assert.equal(frames.at(-1).history_persisted,true);
  assert(f.calls.filter(c=>c.path.startsWith('/api/ui/memory/dialogs/history?')).length>=2);
});

test('V166 duplicate receipt rows and stale exchange still fail closed',async()=>{
  for(const badTail of [
    [{role:'user',exchange_id:'verified-exchange-01',content:'Forged duplicate'}],
    [{role:'assistant',exchange_id:'verified-exchange-01',content:'Forged duplicate'}]
  ]){
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,
      undefined,false,5,undefined,'verified-exchange-01',badTail);
    const r=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt})});
    assert.equal(r.status,503,'duplicate receipt ID cannot prove unique S03 write');
    const j=await r.json();
    assert.equal(j.history_persisted,false);
    assert.match(j.error,/HOLD_DIALOG_HISTORY_READBACK/);
  }
});

test('V165 abort dislodges stalled native stream and never reports S03 done',async()=>{
  let upstreamCancelled=false;const calls=[];
  const old=async (path,opts={})=>{
    const url=new URL(String(path),'https://nox.local');
    calls.push({path:url.pathname,signal:opts.signal});
    if(url.pathname==='/api/nox/chat/stream'){
      // Native transport deliberately ignores fetch AbortSignal: the source
      // emits its first genuine delta but NEVER closes or produces [done].
      return new Response(new ReadableStream({
        start(ctrl){
          for(const x of [
            {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
            {type:'start',model:'NOX HELION'},
            {type:'delta',text:'Настоящий ответ продолжится'}
          ])ctrl.enqueue(new TextEncoder().encode(JSON.stringify(x)+'\n'));
        },
        cancel(){upstreamCancelled=true;}
      }),{headers:{'content-type':'application/x-ndjson'}});
    }
    return new Response('NOT_NATIVE_ROUTE',{status:404});
  };
  const window={NOX_NATIVE_OWNER:true,fetch:old};
  const location={pathname:'/nox-web-v29/pc/resonance.html',
    href:'https://nox.local/nox-web-v29/pc/resonance.html',origin:'https://nox.local'};
  vm.runInNewContext(JS,{window,location,URL,Request,Response,ReadableStream,
    TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
  const controller=new AbortController();
  const response=await window.fetch('/api/nox/chat',{method:'POST',
    signal:controller.signal,
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v165-stalled-native'})});
  const reader=response.body.getReader(),decoder=new TextDecoder();
  const meta=JSON.parse(decoder.decode((await reader.read()).value).slice(6).trim());
  const token=JSON.parse(decoder.decode((await reader.read()).value).slice(6).trim());
  assert.equal(meta.type,'meta');
  assert.equal(token.type,'token');
  assert(token.t.length>0,'first real model delta must be visible');
  controller.abort();
  // V139's optional transport patch may already have enqueued several
  // genuine visual token pieces BEFORE STOP. Drain those buffered pieces,
  // but demand a bounded terminal abort error, never a forged S03 done.
  let stopped=null;
  for(let n=0;n<64;n++){
    const next=await Promise.race([
      reader.read(),new Promise(resolve=>setTimeout(()=>resolve({timeout:true}),400))
    ]);
    assert.notEqual(next.timeout,true,'STOP must unblock a hung native read');
    assert.equal(next.done,false,'STOP must report the reason, not an S03 done');
    const frame=JSON.parse(decoder.decode(next.value).slice(6).trim());
    assert.notEqual(frame.type,'done','aborted generation cannot be committed');
    if(frame.type==='error'){stopped=frame;break;}
    assert.equal(frame.type,'token','only prebuffered genuine tokens may precede STOP');
  }
  assert(stopped,'bounded STOP must eventually return a terminal abort error');
  assert.equal(stopped.error,'STREAM_STOP_REQUESTED');
  assert.equal(upstreamCancelled,true,'only this native reader is cancelled');
  assert.equal(calls.filter(c=>c.path==='/api/nox/chat/stream').length,1);
  assert.equal(calls.some(c=>c.path==='/api/nox/stop'),false,
    'must not send unsafe global GPU STOP');
  assert.equal(calls.some(c=>c.path==='/api/ui/memory/dialogs/history'),false,
    'no S03 success readback for a cancelled generation');
});


test('V166 native provenance: model is PENDING until a meaningful upstream SSE delta',async()=>{
  const f=fake();
  const response=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v166-native-provenance'})});
  const frames=await events(response);
  const pending=frames[0];
  assert.equal(pending.type,'meta');
  assert.equal(pending.answer_source,'NATIVE_PENDING');
  assert.equal(pending.model_label,'UNKNOWN');
  assert.equal(pending.model_identity_verified,false);
  // Preserve original WEB29 one-meta -> token -> done SSE contract.
  // A stream only becomes verified LIVE after native S03 receipt/readback.
  assert.equal(frames.filter(e=>e.type==='meta').length,1);
  assert(frames.some(e=>e.type==='token'&&e.t.trim()));
  const completed=frames.find(e=>e.type==='done');
  assert(completed,'native done plus exact S03 readback required');
  assert.equal(completed.answer_source,'LIVE_NOX');
  assert.equal(completed.model_label,'NOX HELION');
  assert.equal(completed.model_identity_verified,false,'native label cannot prove exact weights SHA');
  assert.equal(frames.filter(e=>e.type==='done').length,1);
  assert.equal(frames.find(e=>e.type==='done').history_persisted,true);
});

test('V166 JSON provenance: relay returns actual native-reported label but not verified weights ID',async()=>{
  const f=fake();
  const response=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt})});
  const data=await response.json();
  assert.equal(response.status,200);
  assert.equal(data.model,'NOX HELION');
  assert.equal(data.model_identity_verified,false);
  assert.equal(data.history_persisted,true);
  assert(f.calls.some(c=>c.path.includes('/api/ui/memory/dialogs/history')));
});


test('V167 done on an open native keepalive completes JSON and SSE with S03 proof',async()=>{
  for(const streamed of [false,true]){
    let cancelled=0,reads=0;
    const q='V167 ответ без EOF',a='Живой ответ',exchange='v167-keepalive-001';
    const native=async path=>{
      const u=new URL(String(path),'https://nox.local');
      if(u.pathname==='/api/ui/memory/dialogs/create')return Response.json({dialog_id:id});
      if(u.pathname==='/api/ui/memory/dialogs/history'){
        reads++;
        return Response.json({status:'READY',dialog_id:id,messages:[
          {role:'user',content:q,exchange_id:exchange},
          {role:'assistant',content:a,exchange_id:exchange}]});
      }
      if(u.pathname==='/api/nox/chat/stream'){
        const frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
          {type:'start',model:'NOX HELION'},{type:'delta',text:a},
          {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:exchange}];
        return new Response(new ReadableStream({
          start(c){c.enqueue(new TextEncoder().encode(frames.map(x=>JSON.stringify(x)+'\n').join('')));},
          cancel(){cancelled++;}
        }),{headers:{'content-type':'application/x-ndjson'}});
      }
      return new Response('NO_NATIVE_ROUTE',{status:404});
    };
    const w={NOX_NATIVE_OWNER:true,fetch:native};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',origin:'https://nox.local',
      href:'https://nox.local/nox-web-v29/pc/resonance.html'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const data={message:q,...(streamed?{dialog_id:id,request_id:'v167'}:{})};
    const res=await Promise.race([w.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify(data)}),
      new Promise((_,rej)=>setTimeout(()=>rej(Error('HOLD_NATIVE_EOF')),1500))]);
    if(streamed){
      const frames=await Promise.race([events(res),
        new Promise((_,rej)=>setTimeout(()=>rej(Error('HOLD_SSE_EOF')),1500))]);
      assert(frames.some(x=>x.type==='token'&&x.t.trim()));
      assert.equal(frames.filter(x=>x.type==='done').length,1);
      assert.equal(frames.find(x=>x.type==='done').history_persisted,true);
    }else{
      assert.equal(res.status,200);
      assert.equal((await res.json()).history_persisted,true);
    }
    assert.equal(reads,1);
    assert.equal(cancelled,1);
  }
});

test('V167 same-chunk native frames after done remain fail-closed',async()=>{
  let readback=0;
  const native=async path=>{
    const u=new URL(String(path),'https://nox.local');
    if(u.pathname==='/api/ui/memory/dialogs/create')return Response.json({dialog_id:id});
    if(u.pathname==='/api/ui/memory/dialogs/history'){
      readback++;return Response.json({status:'READY',dialog_id:id,messages:[]});
    }
    if(u.pathname==='/api/nox/chat/stream'){
      const frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
        {type:'start',model:'NOX HELION'},{type:'delta',text:'Ответ'},
        {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:'v167-duplicate'},
        {type:'delta',text:'FORGED'}];
      return new Response(new ReadableStream({start(c){
        c.enqueue(new TextEncoder().encode(frames.map(x=>JSON.stringify(x)+'\n').join('')));
      }}),{headers:{'content-type':'application/x-ndjson'}});
    }
    return new Response('NO_NATIVE_ROUTE',{status:404});
  };
  const w={NOX_NATIVE_OWNER:true,fetch:native};
  const loc={pathname:'/nox-web-v29/pc/resonance.html',origin:'https://nox.local',
    href:'https://nox.local/nox-web-v29/pc/resonance.html'};
  vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
    TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
  const r=await w.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({message:'V167'})});
  assert.equal(r.status,503);
  assert.match((await r.json()).error,/HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE/);
  assert.equal(readback,0);
});

test('V168 pending native POST must unblock after scoped STOP even if transport ignores signal',async()=>{
  for(const streamed of [false,true]){
    const calls=[],abort=new AbortController(),question='V168 POST pending';
    const native=async path=>{
      const u=new URL(String(path),'https://nox.local');calls.push(u.pathname);
      if(u.pathname==='/api/ui/memory/dialogs/create')return Response.json({dialog_id:id});
      if(u.pathname==='/api/nox/chat/stream')return new Promise(()=>{});
      throw Error('UNEXPECTED_NATIVE_ROUTE');
    };
    const w={NOX_NATIVE_OWNER:true,fetch:native};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',origin:'https://nox.local',
      href:'https://nox.local/nox-web-v29/pc/resonance.html'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const data={message:question,...(streamed?{dialog_id:id,request_id:'v168-stop'}:{})};
    const pending=w.fetch('/api/nox/chat',{method:'POST',signal:abort.signal,body:JSON.stringify(data)});
    if(streamed){
      const response=await pending,reader=response.body.getReader(),dec=new TextDecoder();
      const meta=JSON.parse(dec.decode((await reader.read()).value).slice(6).trim());
      assert.equal(meta.type,'meta');
      abort.abort();
      const next=await Promise.race([reader.read(),
        new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_STALLED_POST_ABORT')),500))]);
      assert.equal(next.done,false);
      const error=JSON.parse(dec.decode(next.value).slice(6).trim());
      assert.equal(error.type,'error');assert.equal(error.error,'STREAM_STOP_REQUESTED');
      assert.equal((await reader.read()).done,true);
    }else{
      await new Promise(ok=>setTimeout(ok,5));abort.abort();
      const response=await Promise.race([pending,
        new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_STALLED_JSON_ABORT')),500))]);
      assert.equal(response.status,503);
      const error=await response.json();
      assert.equal(error.error,'STREAM_STOP_REQUESTED');
      assert.equal(error.history_persisted,false);
    }
    assert(calls.includes('/api/nox/chat/stream'));
    assert(!calls.includes('/api/ui/memory/dialogs/history'));
    assert(!calls.includes('/api/nox/stop'));
  }
});

test('V168 SSE first-visible-token metric only appears after true upstream text',async()=>{
  const f=fake(),response=await f.fetch('/api/nox/chat',{
    method:'POST',body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v168-timing'})
  });
  const all=await events(response);
  assert.equal(all[0].type,'meta');
  assert.equal(all[0].answer_source,'NATIVE_PENDING');
  assert(all.some(x=>x.type==='token'&&x.t.trim()));
  const done=all.find(x=>x.type==='done');
  assert(done&&done.history_persisted===true);
  assert(Number.isInteger(done.first_visible_token_ms));
  assert(done.first_visible_token_ms>=0);
  assert.equal(done.model_identity_verified,false);
});


test('V171 abort interrupts stalled owner S03 history JSON body after HTTP headers',async()=>{
  const abort=new AbortController();
  let didRead=false;
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,undefined,
    false,5,()=>{didRead=true;setTimeout(()=>abort.abort(),10);},
    'verified-exchange-01',[],true);
  const response=await f.fetch('/api/nox/chat',{method:'POST',signal:abort.signal,
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v171-s03-stall'})});
  const frames=await Promise.race([
    events(response),
    new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_STALLED_S03_BODY')),500))
  ]);
  assert(didRead,'readback really started');
  assert(frames.some(e=>e.type==='error'&&e.error==='STREAM_STOP_REQUESTED'));
  assert.equal(frames.filter(e=>e.type==='done').length,0);
  assert.equal(f.calls.filter(c=>c.path==='/api/nox/chat/stream').length,1);
});
test('V171 abort interrupts stalled dialog-create JSON body without inference',async()=>{
  const abort=new AbortController();
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,undefined,
    false,5,undefined,'verified-exchange-01',[],false,true);
  const response=await f.fetch('/api/nox/chat',{method:'POST',signal:abort.signal,
    body:JSON.stringify({message:prompt,dialog_id:null,request_id:'v171-create-stall'})});
  setTimeout(()=>abort.abort(),15);
  const frames=await Promise.race([
    events(response),
    new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_STALLED_CREATE_BODY')),500))
  ]);
  assert(frames.some(e=>e.type==='error'&&e.error==='STREAM_STOP_REQUESTED'));
  assert.equal(frames.filter(e=>e.type==='done').length,0);
  assert(!f.calls.some(c=>c.path==='/api/nox/chat/stream'));
});


test('V172 aborts stalled non-2xx owner error bodies on create, model and S03',async()=>{
  for(const stage of ['create','model','history']){
    const abort=new AbortController(),calls=[];
    const stalled=()=>new Response(new ReadableStream({start(){}}),{status:503});
    const native=async path=>{
      const p=new URL(String(path),'https://nox.local').pathname;
      calls.push(p);
      if(stage==='create'&&p==='/api/ui/memory/dialogs/create')return stalled();
      if(p==='/api/ui/memory/dialogs/create')return Response.json({dialog_id:id});
      if(stage==='model'&&p==='/api/nox/chat/stream')return stalled();
      if(p==='/api/nox/chat/stream'){
        const frames=[
          {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
          {type:'start',model:'NOX HELION'},
          {type:'delta',text:answer},
          {type:'done',saved:true,s03_integrated:true,dialog_id:id,
           exchange_id:'v172-owner-error-body'}
        ];
        return new Response(new ReadableStream({start(c){
          c.enqueue(new TextEncoder().encode(frames.map(x=>JSON.stringify(x)+'\n').join('')));
          c.close();
        }}));
      }
      if(stage==='history'&&p==='/api/ui/memory/dialogs/history')return stalled();
      if(p==='/api/ui/memory/dialogs/history')return Response.json({status:'READY',
        dialog_id:id,messages:[]});
      throw Error('UNEXPECTED_NATIVE_ROUTE_'+p);
    };
    const w={NOX_NATIVE_OWNER:true,fetch:native};
    const loc={pathname:'/nox-web-v29/pc/resonance.html',origin:'https://nox.local',
      href:'https://nox.local/nox-web-v29/pc/resonance.html'};
    vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
      TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
    const data={message:prompt,dialog_id:stage==='create'?null:id,request_id:'v172-'+stage};
    const response=await w.fetch('/api/nox/chat',{method:'POST',signal:abort.signal,
      body:JSON.stringify(data)});
    setTimeout(()=>abort.abort(),20);
    const frames=await Promise.race([events(response),
      new Promise((_,reject)=>setTimeout(()=>reject(Error('STALLED_ERROR_BODY_'+stage)),600))]);
    assert(frames.some(e=>e.type==='error'&&e.error==='STREAM_STOP_REQUESTED'),
      'scoped STOP must work even after HTTP error headers for '+stage);
    assert.equal(frames.some(e=>e.type==='done'),false);
    assert.equal(calls.includes('/api/nox/stop'),false);
    if(stage==='create')assert.equal(calls.includes('/api/nox/chat/stream'),false);
    if(stage==='history')assert(calls.includes('/api/ui/memory/dialogs/history'));
  }
});


test('V174 owner SSE preserves RU and ES prompts through verified terminal receipts',async()=>{
  for(const [question,reply] of [
    ['Какой следующий шаг по NOX?','Сначала проверить память и ответить по-русски.'],
    ['¿Cuál es el siguiente paso de NOX?','Primero comprobar la memoria y responder en español.']
  ]){
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
      undefined,false,6,undefined,'verified-exchange-01',[],false,false,question);
    const response=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:question,dialog_id:id,request_id:'v174-ru-es'})});
    assert.equal(response.headers.get('content-type'),'text/event-stream');
    const reader=response.body.getReader(),decoder=new TextDecoder();
    const first=await reader.read();
    const meta=JSON.parse(decoder.decode(first.value).slice(6).trim());
    assert.equal(meta.type,'meta');
    const initial=await Promise.race([
      reader.read(),
      new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_V174_BUFFERED_DELTA')),90))
    ]);
    const firstEvent=JSON.parse(decoder.decode(initial.value).slice(6).trim());
    assert.equal(firstEvent.type,'token');
    assert(reply.startsWith(firstEvent.t));
    const frames=[firstEvent];
    for(;;){
      const chunk=await reader.read();
      if(chunk.done)break;
      frames.push(JSON.parse(decoder.decode(chunk.value).slice(6).trim()));
    }
    assert.equal(frames.filter(x=>x.type==='done').length,1);
    assert.equal(frames.at(-1).type,'done','terminal success must be the final event');
    const done=frames.at(-1);
    assert.equal(done.saved,true);
    assert.equal(done.s03_integrated,true);
    assert.equal(done.history_persisted,true);
    assert.notEqual(done.gpu_stop_verified,true);
    assert.equal(frames.filter(x=>x.type==='token').map(x=>x.t).join(''),reply);
    assert(f.calls.some(x=>x.path==='/api/nox/chat/stream'));
    assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
    assert.equal(f.calls.some(x=>x.path==='/api/nox/stop'),false);
  }
});

test('V174 abort before model headers cancels the same POST and keeps GPU stop unverified',async()=>{
  const calls=[],caller=new AbortController();
  let modelSignal=null;
  const native=async(path,opts={})=>{
    const u=new URL(String(path),'https://nox.local');
    calls.push({path:u.pathname+u.search,method:opts.method||'GET',signal:opts.signal});
    if(u.pathname==='/api/ui/memory/dialogs/history')
      return Response.json({status:'READY',dialog_id:id,messages:[]});
    if(u.pathname==='/api/nox/chat/stream'){
      modelSignal=opts.signal;
      return new Promise(()=>{}); // fetch hangs before response headers
    }
    return new Response('UNEXPECTED_ROUTE',{status:404});
  };
  const window={NOX_NATIVE_OWNER:true,fetch:native};
  const pathname='/nox-web-v29/pc/resonance.html';
  const location={pathname,href:'https://nox.local'+pathname,origin:'https://nox.local'};
  vm.runInNewContext(JS,{window,location,URL,Request,Response,ReadableStream,
    TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout});
  const response=await window.fetch('/api/nox/chat',{method:'POST',signal:caller.signal,
    body:JSON.stringify({message:'Отмени до HTTP headers',dialog_id:id,request_id:'v174-stop-before-headers'})});
  const reader=response.body.getReader(),decoder=new TextDecoder();
  const first=await reader.read();
  assert.equal(JSON.parse(decoder.decode(first.value).slice(6).trim()).type,'meta');
  for(let i=0;i<40&&!modelSignal;i++)await new Promise(resolve=>setTimeout(resolve,0));
  assert(modelSignal,'the original native stream request must be pending before abort');
  caller.abort();
  let rest='',frames=[];
  for(;;){
    const chunk=await Promise.race([reader.read(),
      new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_V174_STOP_BEFORE_HEADERS')),500))]);
    if(chunk.done)break;
    rest+=decoder.decode(chunk.value,{stream:true});
    let boundary;
    while((boundary=rest.indexOf('\n\n'))>=0){
      const raw=rest.slice(0,boundary);rest=rest.slice(boundary+2);
      if(raw.startsWith('data: '))frames.push(JSON.parse(raw.slice(6)));
    }
  }
  assert.equal(frames.filter(x=>x.type==='done').length,0);
  assert.equal(frames.filter(x=>x.type==='error').length,1);
  const stopped=frames.at(-1);
  assert.equal(stopped.error,'STREAM_STOP_REQUESTED');
  assert.equal(stopped.gpu_stop_verified,false);
  assert.equal(modelSignal.aborted,true);
  assert.equal(calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
  assert.equal(calls.some(x=>x.path==='/api/nox/stop'),false);
  assert.equal(calls.some(x=>x.path==='/api/ui/memory/dialogs/history'),false);
});

test('V173 legacy RU ES first meaningful delta precedes delayed native done, S03 verified',async()=>{
  for(const [reply,firstDeltaAt] of [
    ['Привет, NOX — я отвечаю по-русски.',6],
    ['¡Hola, señor! ¿Cómo estás?',6]
  ]){
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,
      3,undefined,true,firstDeltaAt);
    const response=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v173-legacy-ru-es'})});
    const reader=response.body.getReader(),decoder=new TextDecoder();
    const meta=JSON.parse(decoder.decode((await reader.read()).value).slice(6).trim());
    assert.equal(meta.answer_source,'NATIVE_PENDING');
    const first=await Promise.race([
      reader.read(),
      new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_LEGACY_RU_ES_BUFFERED')),95))
    ]);
    assert.equal(first.done,false);
    const initial=JSON.parse(decoder.decode(first.value).slice(6).trim());
    assert.equal(initial.type,'token');
    assert(initial.t.length>0 && reply.startsWith(initial.t));
    const frames=[initial];
    for(;;){
      const chunk=await reader.read();
      if(chunk.done)break;
      frames.push(JSON.parse(decoder.decode(chunk.value).slice(6).trim()));
    }
    const tokens=frames.filter(x=>x.type==='token');
    assert.equal(tokens.map(x=>x.t).join(''),reply,'no invented/truncated text');
    let offset=0;const boundaries=new Set();
    for(const g of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(reply)){
      offset+=g.segment.length;boundaries.add(offset);
    }
    offset=0;for(const t of tokens){offset+=t.t.length;assert(boundaries.has(offset));}
    const done=frames.find(x=>x.type==='done');
    assert(done && done.history_persisted===true && Number.isInteger(done.first_visible_token_ms));
    assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
    assert.equal(f.calls.some(x=>x.path==='/api/nox/stop'),false);
  }
});

test('V175 SSE pacing cancels the losing callback without changing STOP/S03',async()=>{
  const ID='abcd1234abcd1234abcd1234abcd1234';
  const answer='Ж'.repeat(360)+'🧠'+'español';
  for(const mode of ['frame','timeout']){
    const frames=new Map(),timers=new Map();
    let serial=0,cancelledFrames=0,clearedTimers=0;
    const scheduler={
      requestAnimationFrame(cb){
        const id=++serial;frames.set(id,cb);
        if(mode==='frame')Promise.resolve().then(()=>{
          if(frames.delete(id))cb(performance.now());
        });
        return id;
      },
      cancelAnimationFrame(id){if(frames.delete(id))cancelledFrames++;},
      setTimeout(cb){
        const id=++serial;timers.set(id,cb);
        if(mode==='timeout')Promise.resolve().then(()=>{
          if(timers.delete(id))cb();
        });
        return id;
      },
      clearTimeout(id){if(timers.delete(id))clearedTimers++;}
    };
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,scheduler);
    const r=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt,dialog_id:ID,request_id:'v175-cancel-'+mode})});
    const output=await events(r);
    assert.equal(output.filter(x=>x.type==='token').map(x=>x.t).join(''),answer);
    assert.equal(output.filter(x=>x.type==='done').length,1);
    assert.equal(output.filter(x=>x.type==='error').length,0);
    assert.equal(frames.size,0,'no pending rAF after SSE completion');
    assert.equal(timers.size,0,'no pending timeout after SSE completion');
    if(mode==='frame')assert(clearedTimers>0,'frame winner cancels timeout fallback');
    else assert(cancelledFrames>0,'timeout winner cancels suspended rAF');
    assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
    assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
  }
});


test('V176 scoped SSE cancellation retains stopped phase, never emits post-cancel error phase',async()=>{
  const phases=[],frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
    {type:'start',model:'NOX HELION'},{type:'delta',text:'SSE first token'}];
  const native=async path=>{
    if(String(path)==='/api/nox/chat/stream')return new Response(new ReadableStream({start(c){
      c.enqueue(new TextEncoder().encode(frames.map(x=>JSON.stringify(x)+'\n').join('')));
      // Open transport: scoped STOP must cancel, not produce a fake completed receipt.
    }}),{headers:{'content-type':'application/x-ndjson'}});
    return new Response('NOT_FOUND',{status:404});
  };
  const w={NOX_NATIVE_OWNER:true,fetch:native,
    dispatchEvent(e){phases.push(e.detail.phase);}};
  const loc={pathname:'/nox-web-v29/pc/resonance.html',origin:'https://nox.local',
    href:'https://nox.local/nox-web-v29/pc/resonance.html'};
  class CE{constructor(type,opts){this.type=type;this.detail=opts.detail;}}
  vm.runInNewContext(JS,{window:w,location:loc,URL,Request,Response,ReadableStream,
    TextDecoder,TextEncoder,AbortController,performance,console,Intl,setTimeout,CustomEvent:CE});
  const res=await w.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:'V176 cancellation',dialog_id:id,request_id:'v176-stop'})});
  const reader=res.body.getReader();
  assert.equal(JSON.parse(new TextDecoder().decode((await reader.read()).value).slice(6).trim()).type,'meta');
  assert.equal(JSON.parse(new TextDecoder().decode((await reader.read()).value).slice(6).trim()).type,'token');
  await reader.cancel('scoped browser stop');
  await new Promise(ok=>setTimeout(ok,5));
  assert.equal(phases.at(-1),'stopped','cancellation phase must not be overwritten by async catch');
  assert.equal(phases.includes('error'),false,'post-cancel errors must not repaint the owner UI');
});

test('V177 native chunks reuse already segmented glyphs during browser pacing',async()=>{
  const Seg=Intl.Segmenter;let segments=0;
  const countedIntl={Segmenter:class {
    constructor(...args){this.delegate=new Seg(...args);}
    segment(str){segments++;return this.delegate.segment(str);}
  }};
  const reply='a'.repeat(120)+('NOX 🧠 español русский ').repeat(32);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
    undefined,false,120,undefined,'verified-exchange-01',[],false,false,prompt,countedIntl);
  const output=await events(await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v177-single-segment'})}));
  assert.equal(output.filter(x=>x.type==='token').map(x=>x.t).join(''),reply);
  assert.equal(output.filter(x=>x.type==='done').length,1);
  assert.equal(output.filter(x=>x.type==='error').length,0);
  assert.equal(segments,3,'two native chunks and final tail should each segment once');
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
  assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
});

test('V178 hidden and reduced-motion SSE skip visual timers but preserve native S03 result',async()=>{
  const reply='NOX 🧠 español русский '.repeat(25);
  for(const view of [{hidden:true},{reduced:true},{hidden:false,reduced:false}]){
    let raf=0,timers=0;
    const scheduler={
      requestAnimationFrame(cb){raf++;queueMicrotask(()=>cb(performance.now()));return raf;},
      cancelAnimationFrame(){},
      setTimeout(cb){timers++;queueMicrotask(cb);return timers;},
      clearTimeout(){}
    };
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
      scheduler,false,5,undefined,'verified-exchange-01',[],false,false,prompt,undefined,view);
    const output=await events(await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v178-visibility'})}));
    assert.equal(output.filter(x=>x.type==='token').map(x=>x.t).join(''),reply);
    assert.equal(output.filter(x=>x.type==='done').length,1);
    assert.equal(output.filter(x=>x.type==='error').length,0);
    assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
    assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
    if(view.hidden||view.reduced)assert.equal(raf+timers,0,'no visual pacing work while suppressed');
    else assert(raf+timers>0,'visible motion retains browser pacing');
  }
});

test('V179 browser multi-exchange history preserves exact S03 exchange IDs',async()=>{
  const later=[
    {role:'user',exchange_id:'verified-exchange-02',content:'Segundo turno'},
    {role:'assistant',exchange_id:'verified-exchange-02',content:'Respuesta persistida'}
  ];
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,
    undefined,false,5,undefined,'verified-exchange-01',later);
  const response=await f.fetch('/api/nox/history?dialog_id='+id);
  assert.equal(response.status,200);
  const data=await response.json();
  assert.deepEqual(Array.from(data.messages,m=>m.exchange_id),
    ['verified-exchange-01','verified-exchange-01','verified-exchange-02','verified-exchange-02']);
  assert.deepEqual(Array.from(data.messages,m=>m.role),
    ['user','assistant','user','assistant']);
  assert.equal(data.messages[3].content,'Respuesta persistida');
  assert.equal(f.calls.filter(c=>c.path.startsWith('/api/ui/memory/dialogs/history?')).length,1);
  assert.equal(f.calls.filter(c=>c.path==='/api/nox/chat/stream').length,0);
});

test('V180 tab hiding during pacing frees queued callbacks and still verifies S03',async()=>{
  const rafPending=new Map(),timerPending=new Map(),listeners=new Set();
  let serial=0;
  const doc={visibilityState:'visible',
    addEventListener(type,handler){if(type==='visibilitychange')listeners.add(handler);},
    removeEventListener(type,handler){if(type==='visibilitychange')listeners.delete(handler);}};
  const scheduler={
    requestAnimationFrame(cb){let n=++serial;rafPending.set(n,cb);return n;},
    cancelAnimationFrame(n){rafPending.delete(n);},
    setTimeout(cb){let n=++serial;timerPending.set(n,cb);return n;},
    clearTimeout(n){timerPending.delete(n);}
  };
  const reply='NOX🧠'.repeat(130);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
    scheduler,false,200,undefined,'verified-exchange-01',[],false,false,prompt,undefined,
    {document:doc,reduced:false});
  const response=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v180-visibility-change'})});
  for(let i=0;i<100&&!rafPending.size;i++)await new Promise(ok=>setTimeout(ok,1));
  assert(rafPending.size>0,'first visible token must enter browser pacing');
  doc.visibilityState='hidden';
  for(const callback of Array.from(listeners))callback();
  const output=await Promise.race([events(response),
    new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_V180_VISIBILITY_STALL')),900))]);
  assert.equal(output.filter(x=>x.type==='token').map(x=>x.t).join(''),reply);
  assert.equal(output.filter(x=>x.type==='done').length,1);
  assert.equal(output.filter(x=>x.type==='error').length,0);
  assert.equal(rafPending.size,0);
  assert.equal(timerPending.size,0);
  assert.equal(listeners.size,0,'visibility listeners must be cleared');
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
  assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
});

test('V181 visibility becomes hidden as listener attaches without lost pacing wakeup',async()=>{
  const rafPending=new Map(),timerPending=new Map(),listeners=new Set();
  let serial=0,rafCalls=0,timerCalls=0;
  const doc={visibilityState:'visible',
    addEventListener(type,callback){
      if(type==='visibilitychange'){
        listeners.add(callback);
        // A browser can hide between the initial state check and listener attachment.
        // It is already hidden when registration finishes, without another event.
        this.visibilityState='hidden';
      }
    },
    removeEventListener(type,callback){
      if(type==='visibilitychange')listeners.delete(callback);
    }
  };
  const scheduler={
    requestAnimationFrame(cb){rafCalls++;const n=++serial;rafPending.set(n,cb);return n;},
    cancelAnimationFrame(n){rafPending.delete(n);},
    setTimeout(cb){timerCalls++;const n=++serial;timerPending.set(n,cb);return n;},
    clearTimeout(n){timerPending.delete(n);}
  };
  const reply='NOX 🧠 español русский '.repeat(35);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
    scheduler,false,5,undefined,'verified-exchange-01',[],false,false,prompt,undefined,
    {document:doc,reduced:false});
  const response=await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v181-visibility-race'})});
  const output=await Promise.race([events(response),
    new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_V181_LOST_VISIBILITY_WAKEUP')),900))]);
  assert.equal(doc.visibilityState,'hidden');
  assert.equal(output.filter(x=>x.type==='token').map(x=>x.t).join(''),reply);
  assert.equal(output.filter(x=>x.type==='done').length,1);
  assert.equal(output.filter(x=>x.type==='error').length,0);
  assert.equal(rafPending.size,0,'no stale animation frame after registration race');
  assert.equal(timerPending.size,0,'no delayed fallback timeout after registration race');
  assert.equal(listeners.size,0,'registered visibility callback must be removed');
  assert.equal(rafCalls,0,'V185: settled hidden wait schedules zero animation frames');
  assert.equal(timerCalls,0,'V185: settled hidden wait schedules zero fallback timers');
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
  assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
});

test('V182 legacy CJK and Hangul safely stream before native completion with S03 readback',async()=>{
  for(const reply of ['中文界面实时回答','한국어대답실시간']){
    let s03Seen=false;
    const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
      undefined,true,5,()=>{s03Seen=true;});
    const response=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v182-legacy-cjk'})});
    const reader=response.body.getReader(),decoder=new TextDecoder();
    const meta=JSON.parse(decoder.decode((await reader.read()).value).slice(6).trim());
    assert.equal(meta.type,'meta');
    const first=await Promise.race([
      reader.read(),
      new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_V182_LEGACY_UNICODE_BUFFERED')),95))
    ]);
    assert.equal(first.done,false);
    const initial=JSON.parse(decoder.decode(first.value).slice(6).trim());
    assert.equal(initial.type,'token');
    assert.equal(initial.t,reply.slice(0,4),'keep final potentially incomplete grapheme');
    assert.equal(s03Seen,false,'do not fabricate durable receipt before model completion');
    const frames=[initial];
    for(;;){
      const chunk=await reader.read();
      if(chunk.done)break;
      frames.push(JSON.parse(decoder.decode(chunk.value).slice(6).trim()));
    }
    const tokens=frames.filter(x=>x.type==='token');
    assert.equal(tokens.map(x=>x.t).join(''),reply,'full native text preserved');
    const boundaries=new Set(),segmenter=new Intl.Segmenter(undefined,{granularity:'grapheme'});
    let count=0;
    for(const g of segmenter.segment(reply)){count+=g.segment.length;boundaries.add(count);}
    count=0;
    for(const t of tokens){count+=t.t.length;assert(boundaries.has(count),'no broken grapheme');}
    assert.equal(frames.filter(x=>x.type==='done').length,1);
    assert.equal(frames.filter(x=>x.type==='error').length,0);
    assert.equal(s03Seen,true,'terminal done waits for genuine S03 history');
    assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
  }
});


test('V186 response-global pacing limits rAF waits to two across native chunks with S03 proof',async()=>{
  const reply='Ж'.repeat(960)+'🧠'+'español';
  let frames=0,timers=0;
  const scheduler={
    requestAnimationFrame(cb){frames++;queueMicrotask(()=>cb(performance.now()));return frames;},
    cancelAnimationFrame(){},
    setTimeout(cb,ms){timers++;return setTimeout(cb,ms);},
    clearTimeout(id){clearTimeout(id);}
  };
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,scheduler,false,480);
  const output=await events(await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v183-one-frame'})}));
  assert.equal(output.filter(e=>e.type==='token').map(e=>e.t).join(''),reply);
  assert.equal(output.filter(e=>e.type==='done').length,1);
  assert.equal(output.filter(e=>e.type==='error').length,0);
  assert.equal(frames,2,'at most two paint frames across BOTH native chunks');
  assert.equal(timers,2,'fallback timers capped for entire response, not per chunk');
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
  assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
});


test('V184 scoped abort wakes frozen paint scheduler without false S03 done',async()=>{
  const abort=new AbortController(),framesPending=new Map(),timersPending=new Map();
  let serial=0,abortQueued=false;
  const scheduler={
    requestAnimationFrame(cb){
      const n=++serial;framesPending.set(n,cb);
      if(!abortQueued){abortQueued=true;queueMicrotask(()=>abort.abort());}
      return n;
    },
    cancelAnimationFrame(n){framesPending.delete(n);},
    setTimeout(cb){const n=++serial;timersPending.set(n,cb);return n;},
    clearTimeout(n){timersPending.delete(n);}
  };
  const reply='Ж'.repeat(960)+'🧠';
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,scheduler,false,480);
  const output=await Promise.race([
    events(await f.fetch('/api/nox/chat',{method:'POST',signal:abort.signal,
      body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v184-abort-pacing'})})),
    new Promise((_,reject)=>setTimeout(()=>reject(Error('HOLD_V184_FROZEN_PAINT_ABORT')),500))
  ]);
  assert.equal(abortQueued,true,'abort actually occurred while visual frame was pending');
  assert.equal(output.filter(e=>e.type==='done').length,0,'no forged S03 success');
  assert.equal(output.filter(e=>e.type==='error').at(-1).error,'STREAM_STOP_REQUESTED');
  assert.equal(framesPending.size,0,'no orphan frame callback');
  assert.equal(timersPending.size,0,'no orphan fallback timer');
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1,'single model POST');
  assert.equal(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')),false);
});


test('V187 redundant token UI phases are deduplicated without changing SSE or S03 fixture',async()=>{
  const phases=[];
  const reply='NOX 🧠 español русский '.repeat(75);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
    undefined,false,240,undefined,'verified-exchange-01',[],false,false,prompt,
    undefined,{onPhase:p=>phases.push(p)});
  const out=await events(await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v187-phase'})}));
  assert(out.filter(x=>x.type==='token').length>20,'real multi-slice fixture');
  assert.deepEqual(phases,['waiting','speaking','idle'],'no redundant speaking phase dispatch');
  assert.equal(out.filter(x=>x.type==='token').map(x=>x.t).join(''),reply);
  assert.equal(out.filter(x=>x.type==='done').length,1);
  assert.equal(out.filter(x=>x.type==='error').length,0);
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
  assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
});

test('V188 long single native delta limits browser token enqueue fanout without Unicode loss',async()=>{
  const reply='Ж'.repeat(4096)+'🧠español';
  let s03Read=false;
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
    undefined,false,reply.length,()=>{s03Read=true;});
  const out=await events(await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v188-delta-event-budget'})}));
  const tokens=out.filter(x=>x.type==='token');
  assert(tokens.length>=2,'must retain progressive browser stream');
  assert(tokens.length<=17,'one long delta: at most 16 streamed slices and one grapheme tail');
  assert.equal(tokens.map(x=>x.t).join(''),reply,'no clipping or synthetic token edits');
  let n=0;const boundaries=new Set();
  for(const g of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(reply)){
    n+=g.segment.length;boundaries.add(n);
  }
  n=0;for(const tok of tokens){
    n+=tok.t.length;
    assert(boundaries.has(n),'token boundaries must preserve Unicode graphemes');
  }
  assert.equal(out.filter(x=>x.type==='done').length,1,'terminal only after durable receipt');
  assert.equal(out.filter(x=>x.type==='error').length,0);
  assert.equal(s03Read,true,'independent native history fixture readback still required');
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,1);
});

test('V189 paint budget short-circuits repeated matchMedia lookups after two waits',async()=>{
  const reply='Ж'.repeat(4096)+'🧠 español';
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
    undefined,false,reply.length,undefined,'verified-exchange-01',[],false,false,prompt,
    undefined,{document:{visibilityState:'visible'}});
  let queries=0;
  f.window.matchMedia=()=>{queries++;return {matches:false};};
  const out=await events(await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v189-media-shortcircuit'})}));
  assert.equal(queries,2,'query reduced-motion only while visible frame budget remains');
  assert.equal(out.filter(e=>e.type==='token').map(e=>e.t).join(''),reply);
  assert.equal(out.filter(e=>e.type==='done').length,1);
  assert.equal(out.filter(e=>e.type==='error').length,0);
  assert.equal(f.calls.filter(c=>c.path==='/api/nox/chat/stream').length,1);
  assert(f.calls.some(c=>c.path.startsWith('/api/ui/memory/dialogs/history?')));
});


test('V191 one Intl.Segmenter object reused across sequential streaming requests',async()=>{
  // Tests browser-side allocation only; native identity and actual S03 are not simulated as accepted.
  let constructors=0,segmentCalls=0,historyChecks=0;
  const NativeSegmenter=Intl.Segmenter;
  const countedIntl={Segmenter:class{
    constructor(...args){constructors++;this.underlying=new NativeSegmenter(...args);}
    segment(s){segmentCalls++;return this.underlying.segment(s);}
  }};
  const reply='NOX '+('e\u0301👩‍💻 español русский ').repeat(24);
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,reply,3,
    undefined,false,4,()=>{historyChecks++;},'verified-exchange-01',
    [],false,false,prompt,countedIntl);
  for(let turn=0;turn<2;turn++){
    const response=await f.fetch('/api/nox/chat',{method:'POST',
      body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v191-browser-'+turn})});
    const frames=await events(response);
    assert.equal(frames.filter(x=>x.type==='done').length,1);
    assert.equal(frames.filter(x=>x.type==='error').length,0);
    assert.equal(frames.filter(x=>x.type==='token').map(x=>x.t).join(''),reply,
      'Unicode grapheme-preserving SSE payload must remain lossless');
    assert.equal(frames.at(-1).model_identity_verified,false,
      'browser source cannot assert installed tokenizer or weights');
  }
  assert.equal(constructors,1,'a single immutable Segmenter should serve the owner page');
  assert(segmentCalls>2,'both transport coalescing and visual token slicing reuse it');
  assert.equal(historyChecks,2,'mock owner S03 history gate still called for both requests');
  assert.equal(f.calls.filter(x=>x.path==='/api/nox/chat/stream').length,2,
    'one native POST per explicit browser request');
});

test('V192 queued native history fetch does not start after scoped STOP',async()=>{
  const f=fake(),abort=new AbortController();
  const pending=f.fetch('/api/nox/history?dialog_id='+id,{signal:abort.signal});
  abort.abort(); // after scheduling the native operation, before its microtask
  const r=await pending;
  assert.equal(r.status,503,'STOP is a HOLD, never a persisted success');
  assert.match((await r.json()).error,/STREAM_STOP_REQUESTED/);
  assert.equal(f.calls.filter(c=>c.path.startsWith('/api/ui/memory/dialogs/history?')).length,0,
    'an aborted queued native fetch must not execute a stale network request');
});

test('V194 scoped AbortSignal STOP reports stopped UI phase without S03 success',async()=>{
  const abort=new AbortController(),phases=[];let stopped=false,historyCalled=false;
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,
    undefined,false,5,()=>{historyCalled=true;},'verified-exchange-01',
    [],false,false,prompt,undefined,{onPhase:p=>{
      phases.push(p);
      if(p==='speaking'&&!stopped){stopped=true;abort.abort();}
    }});
  const out=await events(await f.fetch('/api/nox/chat',{method:'POST',signal:abort.signal,
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v194-signal-stop'})}));
  assert.equal(stopped,true,'abort must occur after live speaking phase');
  assert.equal(out.filter(e=>e.type==='done').length,0,'no forged persisted completion');
  assert.equal(out.filter(e=>e.type==='error').at(-1).error,'STREAM_STOP_REQUESTED');
  assert.equal(phases.at(-1),'stopped','scoped STOP must not repaint error UI');
  assert.equal(phases.includes('error'),false,'STOP is not a model error');
  assert.equal(historyCalled,false,'aborted turn cannot claim S03 readback');
  assert.equal(f.calls.filter(c=>c.path==='/api/nox/chat/stream').length,1);
  const failure=fake(true,'/nox-web-v29/pc/resonance.html',true,answer,3,
    undefined,false,5,undefined,'verified-exchange-01',
    [],false,false,prompt,undefined,{onPhase:p=>phases.push(p)});
  const frames=await events(await failure.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v194-genuine-error'})}));
  assert.equal(frames.some(e=>e.type==='error'&&/HOLD_S03_COMMIT_RECEIPT/.test(e.error)),true);
  assert.equal(phases.at(-1),'error','genuine S03 failure still reports error');
});


test('V195 Request input.signal survives init.body override for stream and JSON STOP',async()=>{
  const abort=new AbortController(),phases=[];
  let stopped=false,historyCalled=false;
  const f=fake(true,'/nox-web-v29/pc/resonance.html',false,answer,3,
    undefined,false,5,()=>{historyCalled=true;},'verified-exchange-01',
    [],false,false,prompt,undefined,{onPhase:p=>{
      phases.push(p);
      if(p==='speaking'&&!stopped){stopped=true;abort.abort();}
    }});
  const body=JSON.stringify({message:prompt,dialog_id:id,request_id:'v195-request-signal'});
  const input=new Request('https://nox.local/api/nox/chat',{method:'POST',body,signal:abort.signal});
  const out=await events(await f.fetch(input,{method:'POST',body}));
  assert.equal(stopped,true,'STOP initiated on live token');
  assert.equal(out.filter(e=>e.type==='done').length,0,'no forged S03 success');
  assert.equal(out.filter(e=>e.type==='error').at(-1).error,'STREAM_STOP_REQUESTED');
  assert.equal(phases.at(-1),'stopped');
  assert.equal(historyCalled,false,'no S03 readback after abort');
  assert.equal(f.calls.filter(c=>c.path==='/api/nox/chat/stream').length,1);
  const preAbort=new AbortController();preAbort.abort();
  const jsonBody=JSON.stringify({message:prompt});
  const jsonRequest=new Request('https://nox.local/api/nox/chat',{
    method:'POST',body:jsonBody,signal:preAbort.signal
  });
  const g=fake();
  const jsonResult=await g.fetch(jsonRequest,{method:'POST',body:jsonBody});
  assert.equal(jsonResult.status,503,'JSON STOP is HOLD');
  assert.match((await jsonResult.json()).error,/STREAM_STOP_REQUESTED/);
  assert.equal(g.calls.length,0,'aborted Request never creates dialog or model POST');
});

test('V196 mismatched native model receipt label fails closed for SSE and JSON',async()=>{
  let reads=0;
  const args=[true,'/nox-web-v29/pc/resonance.html',false,answer,3,
    undefined,false,5,()=>{reads++;},'verified-exchange-01',
    [],false,false,prompt,undefined,{receiptModelLabel:'DIFFERENT MODEL'}];
  const f=fake(...args);
  const out=await events(await f.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt,dialog_id:id,request_id:'v196-label-conflict'})}));
  assert.equal(out.filter(e=>e.type==='done').length,0);
  assert.equal(out.filter(e=>e.type==='error').length,1);
  assert.match(out.find(e=>e.type==='error').error,/HOLD_MODEL_LABEL_CONFLICT/);
  assert.equal(reads,0,'reject identity conflict before history success');
  assert.equal(f.calls.filter(c=>c.path==='/api/nox/chat/stream').length,1);
  const g=fake(...args);
  const r=await g.fetch('/api/nox/chat',{method:'POST',
    body:JSON.stringify({message:prompt})});
  assert.equal(r.status,503);
  assert.match((await r.json()).error,/HOLD_MODEL_LABEL_CONFLICT/);
});
