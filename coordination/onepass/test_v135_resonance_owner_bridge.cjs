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
function fake(owner=true,pathname='/nox-web-v29/pc/resonance.html',rejectReceipt=false,reply=answer,revision=3,raf,legacyIntl=false,firstDeltaAt=5,onHistory){
  const calls=[];
  let old=async (path,opts={})=>{
    const u=new URL(String(path),'https://nox.local');
    calls.push({path:u.pathname+u.search,method:opts.method||'GET',credentials:opts.credentials,signal:opts.signal});
    if(u.pathname==='/api/ui/memory/dialogs/create'){
      const body=JSON.parse(opts.body||'{}');
      assert.equal(body.confirmed,true);
      return Response.json({dialog_id:id,title:body.title});
    }
    if(u.pathname==='/api/ui/memory/dialogs'){
      return Response.json({status:'READY',dialogs:[{dialog_id:id,title:'Тест',revision:2}]});
    }
    if(u.pathname==='/api/ui/memory/dialogs/history'){
      onHistory?.();
      return Response.json({status:'READY',dialog_id:id,messages:[
        {role:'user',content:prompt,ts:'2026-11-15T00:00:00Z'},
        {role:'assistant',content:reply,ts:'2026-11-15T00:00:01Z'}]});
    }
    if(u.pathname==='/api/ui/memory/dialogs/update'){
      const b=JSON.parse(opts.body);
      assert.equal(b.revision,2);
      assert.equal(b.confirmed,true);
      return Response.json({dialog_id:id,title:b.title,revision});
    }
    if(u.pathname==='/api/nox/chat/stream'){
      const b=JSON.parse(opts.body);
      assert.equal(b.message,prompt);
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
          s03_integrated:true,dialog_id:id,exchange_id:'verified-exchange-01'})+'\n'));
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
  if(legacyIntl)context.Intl={}; // emulate old browsers with no Intl.Segmenter
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
  // Fixture has two native delta events; without a grapheme segmenter the
  // safest fallback emits those exact deltas, not artificial codepoint pieces.
  assert.equal(pieces.length,1,'without grapheme support the bounded whole reply is the only guaranteed safe visual token');
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
    if(legacyIntl)assert.equal(tokens.length,1,'legacy must fail safe, not guess cluster edges');
    else assert(tokens.length>=2,'modern browser still streams genuine prefix before native done');
    assert.equal(read.filter(x=>x.type==='done').length,1);
    assert.equal(read.find(x=>x.type==='done').history_persisted,true);
    assert(f.calls.some(x=>x.path.startsWith('/api/ui/memory/dialogs/history?')));
  }
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
          {role:'user',content:prompt},{role:'assistant',content:answer}]});
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
          {role:'user',content:prompt},{role:'assistant',content:answer}]});
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
        status:'READY',dialog_id:id,messages:[{role:'user',content:p},{role:'assistant',content:a}]
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
          {role:'user',content:p},{role:'assistant',content:a}]});
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
          {role:'user',content:prompt},{role:'assistant',content:answer}]});
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
          {role:'user',content:p},{role:'assistant',content:a}]});
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
          {role:'user',content:question},{role:'assistant',content:answer}]});
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
