/* NOX V29.3 owner-stage legacy chat protocol adapter.
 * Narrowly bridges the ORIGINAL /api/nox/chat legacy callers to the verified
 * EXISTING /api/nox/chat/stream OneHost endpoint. No new backend or model.
 * Everything is gated by native owner state; original Windows route is inert.
 */
(() => {
  'use strict';
  const ownerScope = window.NOX_NATIVE_OWNER === true &&
    /^\/nox-web-v29\//.test(window.location.pathname);
  if (!ownerScope || window.__NOX_V293_LEGACY_CHAT_BRIDGE) return;
  window.__NOX_V293_LEGACY_CHAT_BRIDGE = 'SOURCE_ADAPTER_NOT_A_SECOND_MODEL';
  const originalFetch = window.fetch.bind(window);
  const enc = new TextEncoder();
  const MAX_ANSWER = 200000;
  const jsonError = (code, status=503) => new Response(JSON.stringify({
    status:'HOLD', error:code, history_persisted:false, s03_integrated:false
  }), {status, headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  function decodePath(input) {
    try {
      const url = new URL(input instanceof Request ? input.url : String(input),location.href);
      return url.origin === location.origin && url.pathname === '/api/nox/chat' && !url.search;
    } catch { return false; }
  }
  function safeTitle(message) {
    return ('NOX · '+message.replace(/[\x00-\x1F\x7F]/g,' ').trim()).slice(0,140);
  }
  function nativeCall(path, data, signal) {
    return originalFetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal});
  }
  async function readError(response) {
    try {
      const body = await response.json();
      return String(body.error || body.reason || 'HTTP_'+response.status).slice(0,110);
    } catch { return 'HTTP_'+response.status; }
  }
  async function authorizeDialog(data, signal) {
    if (data.dialog_id !== undefined && data.dialog_id !== null && data.dialog_id !== '') {
      if (typeof data.dialog_id !== 'string' || !/^[a-f0-9]{32}$/.test(data.dialog_id))
        throw Error('HOLD_INVALID_DIALOG_SCOPE');
      return data.dialog_id;
    }
    const response = await nativeCall('/api/ui/memory/dialogs/create',{
      title:safeTitle(data.message),confirmed:true
    },signal);
    if (!response.ok) throw Error('HOLD_DIALOG_CREATE_'+await readError(response));
    const row=await response.json();
    if (typeof row.dialog_id !== 'string' || !/^[a-f0-9]{32}$/.test(row.dialog_id))
      throw Error('HOLD_DIALOG_CREATE_RECEIPT');
    return row.dialog_id;
  }
  async function assertHistory(dialogId, prompt, answer, signal) {
    const response=await originalFetch('/api/ui/memory/dialogs/history?dialog_id='+encodeURIComponent(dialogId),{
      credentials:'same-origin',cache:'no-store',signal
    });
    if (!response.ok) throw Error('HOLD_DIALOG_HISTORY_'+await readError(response));
    const body=await response.json();
    if (body.status !== 'READY' || body.dialog_id !== dialogId || !Array.isArray(body.messages))
      throw Error('HOLD_DIALOG_HISTORY_CONTRACT');
    const last=body.messages.slice(-2);
    if (last.length!==2 || last[0].role!=='user' || last[0].content!==prompt ||
      last[1].role!=='assistant' || last[1].content!==answer)
      throw Error('HOLD_DIALOG_HISTORY_READBACK');
  }
  function confirmed(done, dialogId) {
    return done && done.type==='done' && done.saved===true && done.s03_integrated===true &&
      done.dialog_id===dialogId && typeof done.exchange_id==='string' &&
      done.exchange_id.length>=6 && done.exchange_id.length<=160;
  }
  async function parseNDJSON(response, callbacks, signal) {
    if (!response.ok || !response.body) throw Error('HOLD_NATIVE_STREAM_'+await readError(response));
    const reader=response.body.getReader();
    const decoder=new TextDecoder('utf-8');
    let buffer='', answer='', receipt=null;
    try {
      while (true) {
        if (signal?.aborted) throw Error('STREAM_STOP_REQUESTED');
        const {value,done}=await reader.read();
        if (done) break;
        buffer+=decoder.decode(value,{stream:true});
        if (buffer.length>300000) throw Error('HOLD_NATIVE_FRAME_TOO_LARGE');
        let pos;
        while ((pos=buffer.indexOf('\n'))>=0) {
          const line=buffer.slice(0,pos).trim();buffer=buffer.slice(pos+1);
          if (!line) continue;
          let event;
          try { event=JSON.parse(line); } catch { throw Error('HOLD_NATIVE_FRAME_JSON'); }
          if (!event || typeof event!=='object' || Array.isArray(event))
            throw Error('HOLD_NATIVE_FRAME_SCHEMA');
          if (event.type==='delta') {
            if (typeof event.text!=='string' || answer.length+event.text.length>MAX_ANSWER)
              throw Error('HOLD_NATIVE_ANSWER_BOUNDS');
            answer+=event.text;
            await callbacks.token?.(event.text,answer);
          } else if (event.type==='done') {
            if (receipt) throw Error('HOLD_DUPLICATE_DONE');
            receipt=event;
          } else if (event.type==='error') {
            throw Error('HOLD_NATIVE_'+String(event.error||'ERROR').slice(0,80));
          }
        }
      }
      buffer+=decoder.decode();
      if (buffer.trim()) throw Error('HOLD_INCOMPLETE_NATIVE_FRAME');
      if (!answer.trim() || !receipt) throw Error('HOLD_INCOMPLETE_NATIVE_RESPONSE');
      return {answer,receipt};
    } finally {
      try { await reader.cancel(); } catch {}
    }
  }
  async function runJSON(data,signal) {
    try {
      const dialogId=await authorizeDialog(data,signal);
      const wire=await nativeCall('/api/nox/chat/stream',{
        message:data.message,dialog_id:dialogId,history:[],task:'general'
      },signal);
      const {answer,receipt}=await parseNDJSON(wire,{},signal);
      if (!confirmed(receipt,dialogId)) throw Error('HOLD_S03_COMMIT_RECEIPT');
      await assertHistory(dialogId,data.message,answer,signal);
      return new Response(JSON.stringify({
        model:'NOX HELION',answer,exchange_id:receipt.exchange_id,
        dialog_id:dialogId,history_persisted:true,s03_integrated:true,
        source:'EXISTING_ONEHOST_NATIVE_S03_VERIFIED'
      }),{status:200,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    } catch (error) {
      if (signal?.aborted) return jsonError('STREAM_STOP_REQUESTED',499);
      return jsonError(String(error.message||'HOLD_NATIVE_BRIDGE').slice(0,150));
    }
  }
  function runSSE(data,signal) {
    let cancel=false;
    const stream=new ReadableStream({
      async start(controller) {
        const event=(body)=>{
          if (!cancel) controller.enqueue(enc.encode('data: '+JSON.stringify(body)+'\n\n'));
        };
        try {
          const dialogId=await authorizeDialog(data,signal);
          const wire=await nativeCall('/api/nox/chat/stream',{
            message:data.message,dialog_id:dialogId,history:[],task:'general'
          },signal);
          event({type:'meta',dialog_id:dialogId,model_label:'NOX HELION'});
          const {answer,receipt}=await parseNDJSON(wire,{token:async text=>event({type:'token',t:text})},signal);
          if (!confirmed(receipt,dialogId)) throw Error('HOLD_S03_COMMIT_RECEIPT');
          await assertHistory(dialogId,data.message,answer,signal);
          event({type:'done',dialog_id:dialogId,exchange_id:receipt.exchange_id,
            saved:true,s03_integrated:true,history_persisted:true});
        } catch (error) {
          event({type:'error',error:String(error.message||'HOLD_NATIVE_BRIDGE').slice(0,150)});
        } finally {
          if (!cancel) { try { controller.close(); } catch {} }
        }
      },
      cancel() { cancel=true; }
    });
    return new Response(stream,{status:200,headers:{'Content-Type':'text/event-stream','Cache-Control':'no-store'}});
  }
  window.fetch = function(input,init) {
    if (!decodePath(input) || (init?.method || (input instanceof Request?input.method:'GET')).toUpperCase()!=='POST')
      return originalFetch(input,init);
    if (input instanceof Request && !init?.body)
      return originalFetch(input,init); // do not consume or modify unknown Request bodies
    let body;
    try { body=JSON.parse(init?.body); } catch { return Promise.resolve(jsonError('INVALID_JSON',400)); }
    if (!body || typeof body!=='object' || Array.isArray(body) ||
      typeof body.message!=='string' || !body.message.trim() || body.message.length>8000)
      return Promise.resolve(jsonError('INVALID_MESSAGE',422));
    const signal=init?.signal;
    const expectsSSE=(typeof body.request_id==='string' ||
      Object.prototype.hasOwnProperty.call(body,'dialog_id') ||
      (init?.headers && String(init.headers.Accept||init.headers.accept||'').includes('text/event-stream')));
    return expectsSSE?Promise.resolve(runSSE(body,signal)):runJSON(body,signal);
  };
})();
