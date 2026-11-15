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
function fake(owner=true,pathname='/nox-web-v29/pc/resonance.html',rejectReceipt=false,reply=answer){
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
      return Response.json({status:'READY',dialog_id:id,messages:[
        {role:'user',content:prompt,ts:'2026-11-15T00:00:00Z'},
        {role:'assistant',content:reply,ts:'2026-11-15T00:00:01Z'}]});
    }
    if(u.pathname==='/api/ui/memory/dialogs/update'){
      const b=JSON.parse(opts.body);
      assert.equal(b.revision,2);
      assert.equal(b.confirmed,true);
      return Response.json({dialog_id:id,title:b.title,revision:3});
    }
    if(u.pathname==='/api/nox/chat/stream'){
      const b=JSON.parse(opts.body);
      assert.equal(b.message,prompt);
      assert.equal(b.dialog_id,id);
      assert.deepEqual(b.history,[]);
      assert.equal(opts.credentials,'same-origin');
      const bytes=new TextEncoder();
      const stream=new ReadableStream({async start(ctrl){
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'preparing'})+'\n'));
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'start',model:'NOX HELION'})+'\n'));
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'delta',text:reply.slice(0,5)})+'\n'));
        await new Promise(ok=>setTimeout(ok,110));
        if(opts.signal?.aborted){ctrl.close();return;}
        ctrl.enqueue(bytes.encode(JSON.stringify({type:'delta',text:reply.slice(5)})+'\n'));
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
    TextDecoder,TextEncoder,AbortController,performance,console};
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
  assert.equal(n.status,'READY','original V24 demands READY on rename');
  assert.equal(n.revision,3);
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
