/* NOX V135 — owner-scoped compatibility for the ORIGINAL V24/V22 Resonance.
 * Repairs the missing /api/nox/chat SSE wiring, dialog create/list/history
 * against existing V112 OneHost/S03. Never adds a server, model or database.
 * No fake success: completion requires native done + persisted S03 readback.
 */
(() => {
  'use strict';
  const here=location.pathname;
  const owner=window.NOX_NATIVE_OWNER===true &&
    /^\/nox-web-v29\/pc\/(?:resonance\.html|v22\/resonance\.template\.html)$/.test(here);
  if (!owner || window.__NOX_V135_OWNER_RESONANCE) return;
  window.__NOX_V135_OWNER_RESONANCE='OWNER_NATIVE_ONLY';
  const nativeFetch=window.fetch.bind(window);
  const enc=new TextEncoder();
  const ID=/^[a-f0-9]{32}$/;
  const MAX=200000;
  // Only split ACTUAL upstream model deltas. Never invent text or report done
  // before a native S03 receipt. A single late native delta still starts late.
  // Limit event count for huge upstream chunks; preserve every codepoint.
  function livePieces(text) {
    // Keep complex emoji and combining accents intact at each visual token edge.
    // The bytes and persisted upstream answer are unchanged. Without
    // Intl.Segmenter, emit the complete native delta: codepoint splitting
    // can tear ZWJ emoji/combining clusters into visibly broken tokens.
    const glyphs=typeof Intl!=='undefined' && typeof Intl.Segmenter==='function'
      ? Array.from(new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text),part=>part.segment)
      : [text];
    const width=Math.max(8,Math.ceil(glyphs.length/64));
    const pieces=[];
    for(let pos=0;pos<glyphs.length;pos+=width)pieces.push(glyphs.slice(pos,pos+width).join(''));
    return pieces;
  }
  const errorResponse=(error,status=503)=>new Response(JSON.stringify({
    status:'HOLD',error,history_persisted:false,s03_integrated:false
  }),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  const samePath=input=>{
    try {
      const u=new URL(input instanceof Request?input.url:String(input),location.href);
      return u.origin===location.origin?u:null;
    } catch{return null;}
  };
  const options=(init={})=>({
    method:init.method||'GET',cache:'no-store',credentials:'same-origin',
    signal:init.signal,headers:init.headers
  });
  const nativePost=(path,data,signal)=>nativeFetch(path,{
    method:'POST',credentials:'same-origin',cache:'no-store',signal,
    headers:{'Content-Type':'application/json'},body:JSON.stringify(data)
  });
  async function reason(r) {
    try{const j=await r.json();return String(j.error||j.reason||'HTTP_'+r.status).slice(0,110);}
    catch{return 'HTTP_'+r.status;}
  }
  const responseJSON=(data,status=200)=>new Response(JSON.stringify(data),{
    status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}
  });
  async function nativeJSON(path,init) {
    const r=await nativeFetch(path,options(init));
    if (!r.ok)throw Error('HOLD_NATIVE_ROUTE_'+await reason(r));
    return r.json();
  }
  async function createDialog(title,signal) {
    const r=await nativePost('/api/ui/memory/dialogs/create',{
      title:String(title||'Новый диалог').replace(/[\x00-\x1F\x7F]/g,' ').trim().slice(0,140)||'Новый диалог',
      confirmed:true
    },signal);
    if(!r.ok)throw Error('HOLD_DIALOG_CREATE_'+await reason(r));
    const d=await r.json();
    if(typeof d.dialog_id!=='string'||!ID.test(d.dialog_id))throw Error('HOLD_DIALOG_CREATE_RECEIPT');
    return d;
  }
  async function dialogId(data,signal) {
    if(data.dialog_id===null||data.dialog_id===undefined||data.dialog_id===''){
      return (await createDialog(String(data.message||'').slice(0,140),signal)).dialog_id;
    }
    if(typeof data.dialog_id!=='string'||!ID.test(data.dialog_id))throw Error('HOLD_INVALID_DIALOG_SCOPE');
    return data.dialog_id;
  }
  async function checkHistory(id,prompt,answer,exchangeId,signal) {
    const data=await nativeJSON('/api/ui/memory/dialogs/history?dialog_id='+id+'&limit=100',{signal});
    if(data.status!=='READY'||data.dialog_id!==id||!Array.isArray(data.messages))throw Error('HOLD_DIALOG_HISTORY_CONTRACT');
    const pair=data.messages.slice(-2);
    if(pair.length!==2||pair[0].role!=='user'||pair[1].role!=='assistant'||
       pair[0].content!==prompt||pair[1].content!==answer||
       pair[0].exchange_id!==exchangeId||pair[1].exchange_id!==exchangeId)
      throw Error('HOLD_DIALOG_HISTORY_READBACK');
  }
  function accepted(done,id) {
    return done?.type==='done'&&done.saved===true&&done.s03_integrated===true&&
      done.dialog_id===id&&typeof done.exchange_id==='string'&&
      done.exchange_id.length>=6&&done.exchange_id.length<=160;
  }
  async function consume(response,emit,signal) {
    if(!response.ok||!response.body)throw Error('HOLD_NATIVE_STREAM_'+await reason(response));
    const reader=response.body.getReader(),decoder=new TextDecoder();
    let buf='',answer='',done=null,doneSeen=false,startSeen=false,preparingSeen=false;
    const line=async str=>{
      if(!str.trim())return;
      let e;
      try{e=JSON.parse(str);}catch{throw Error('HOLD_NATIVE_FRAME_JSON');}
      if(!e||typeof e!=='object'||Array.isArray(e))throw Error('HOLD_NATIVE_FRAME_TYPE');
      // Native done is terminal. Never accept extra protocol frames as
      // a successful persisted exchange (blank lines remain permitted).
      if(doneSeen){
        if(e.type==='done')throw Error('HOLD_DUPLICATE_DONE');
        throw Error('HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE');
      }
      if(e.type==='error')throw Error('HOLD_NATIVE_'+String(e.error||'ERROR').slice(0,90));
      if(e.type==='delta'){
        if(!startSeen)throw Error('HOLD_NATIVE_START_REQUIRED');
        if(doneSeen||typeof e.text!=='string'||answer.length+e.text.length>MAX)throw Error('HOLD_NATIVE_DELTA');
        answer+=e.text;await emit(e.text);
      } else if(e.type==='done') {
        if(!startSeen)throw Error('HOLD_NATIVE_START_REQUIRED');
        if(doneSeen)throw Error('HOLD_DUPLICATE_DONE');
        doneSeen=true;done=e;
      } else if(e.type==='start') {
        if(!preparingSeen)throw Error('HOLD_NATIVE_PREPARING_REQUIRED');
        if(startSeen)throw Error('HOLD_DUPLICATE_NATIVE_START');
        startSeen=true;
      } else if(e.type==='preparing') {
        // Original V112 emits one preparing frame before its native start.
        // A repeated/late preparation is an invalid wire sequence, even if
        // a forged done would otherwise match a healthy S03 history fixture.
        if(preparingSeen||startSeen)throw Error('HOLD_NATIVE_PREPARING_ORDER');
        // The original V112 OneHost always advertises this exact native mode.
        // A mismatched or absent mode cannot support a persisted-S03 receipt.
        if(e.stream_mode!=='NATIVE_TOKEN_STREAM')throw Error('HOLD_NATIVE_STREAM_MODE');
        preparingSeen=true;
      } else {
        // Fail closed: an unrecognized native frame cannot precede a
        // trustworthy terminal receipt or persisted S03 history readback.
        throw Error('HOLD_NATIVE_UNKNOWN_FRAME');
      }
    };
    try{
      for(;;){
        if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');
        const chunk=await reader.read();
        if(chunk.done)break;
        buf+=decoder.decode(chunk.value,{stream:true});
        // A transport read may coalesce MANY valid short NDJSON frames.
        // Enforce the limit per unfinished frame, not on the entire read.
        let j;while((j=buf.indexOf('\n'))>=0){
          if(j>300000)throw Error('HOLD_NATIVE_FRAME_TOO_LARGE');
          await line(buf.slice(0,j).trim());buf=buf.slice(j+1);
        }
        if(buf.length>300000)throw Error('HOLD_NATIVE_FRAME_TOO_LARGE');
      }
      buf+=decoder.decode();
      if(buf.trim())throw Error('HOLD_INCOMPLETE_NATIVE_FRAME');
      if(!done||!answer.trim())throw Error('HOLD_INCOMPLETE_NATIVE_RESPONSE');
      return {answer,receipt:done};
    }finally{try{await reader.cancel();}catch{}}
  }
  // NOX_OWNER_COALESCED_STREAM_V1: visual scheduling never delays native reads.
  // Pending text is real, ordered upstream text and remains under the same MAX.
  // One frame (or hidden-tab timer fallback) combines all arrivals since flush.
  function coalescedTokens(emit,signal,onFailure) {
    let parts=[],length=0,scheduled=null,cancelled=false,failure=null;
    const unschedule=()=>{
      const job=scheduled;scheduled=null;
      if(job?.frame!=null&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(job.frame);
      if(job?.timer!=null&&typeof clearTimeout==='function')clearTimeout(job.timer);
    };
    const cancel=()=>{cancelled=true;unschedule();parts=[];length=0;};
    const check=()=>{
      if(failure)throw failure;
      if(cancelled||signal.aborted)throw Error('STREAM_STOP_REQUESTED');
    };
    const flush=()=>{
      check();
      if(!length)return;
      const text=parts.join('');parts=[];length=0;
      emit(text);
    };
    const schedule=()=>{
      if(scheduled)return;
      const job={frame:null,timer:null};scheduled=job;
      const finish=()=>{
        if(scheduled!==job)return;
        unschedule();
        try{flush();}
        catch{failure=Error('HOLD_NATIVE_RENDER_QUEUE');cancel();onFailure();}
      };
      if(typeof requestAnimationFrame==='function')job.frame=requestAnimationFrame(finish);
      if(scheduled===job&&typeof setTimeout==='function')job.timer=setTimeout(finish,18);
      // Safe for environments without either scheduler; browsers have timers.
      if(scheduled===job&&job.frame===null&&job.timer===null)finish();
    };
    return {
      add(text){
        check();
        if(typeof text!=='string'||length+text.length>MAX)throw Error('HOLD_NATIVE_DELTA');
        if(!text)return;
        parts.push(text);length+=text.length;schedule();
      },
      // Drain synchronously at EOF: no manufactured playback after upstream
      // completion, and no queued token may follow S03 verification or done.
      drain(){check();unschedule();flush();},
      cancel,
      failure:()=>failure
    };
  }
  function sseChat(data,signal) {
    let closed=false,visual=null;const started=performance.now();
    // Downstream reader cancellation must cancel the EXISTING native request.
    // Abort is scoped to this generation, never global /api/nox/stop.
    const upstreamAbort=new AbortController();
    const onAbort=()=>{visual?.cancel();upstreamAbort.abort();};
    if(signal?.aborted)upstreamAbort.abort();
    else signal?.addEventListener?.('abort',onAbort,{once:true});
    const nativeSignal=upstreamAbort.signal;
    const body=new ReadableStream({
      async start(controller){
        const event=payload=>{
          if(payload.type==='token'&&nativeSignal.aborted)return;
          const phase={meta:'waiting',token:'speaking',done:'idle',error:'error'}[payload.type];
          if(phase&&typeof window.dispatchEvent==='function'&&typeof CustomEvent==='function')
            window.dispatchEvent(new CustomEvent('nox:native-phase',{detail:{phase}}));
          if(!closed&&(payload.type!=='token'||!nativeSignal.aborted))
            controller.enqueue(enc.encode('data: '+JSON.stringify(payload)+'\n\n'));
        };
        try {
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          const id=await dialogId(data,nativeSignal);
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          event({type:'meta',dialog_id:id,model_label:'NOX HELION',answer_source:'LIVE_NOX'});
          const upstream=await nativePost('/api/nox/chat/stream',{
            message:data.message,dialog_id:id,task:'general',history:[]
          },nativeSignal);
          // A native NDJSON frame may end MID-grapheme (ZWJ/combining mark).
          // Keep one trailing grapheme until the next frame establishes its edge.
          // Without a segmenter no safe incremental edge is known: buffer the
          // bounded native answer until done instead of corrupting visual tokens.
          const canSegment=typeof Intl!=='undefined' && typeof Intl.Segmenter==='function';
          const segmenter=canSegment?new Intl.Segmenter(undefined,{granularity:'grapheme'}):null;
          let trailing='';
          visual=coalescedTokens(t=>event({type:'token',t}),nativeSignal,()=>upstreamAbort.abort());
          const {answer,receipt}=await consume(upstream,async t=>{
            trailing+=t;
            if(!segmenter)return;
            const glyphs=Array.from(segmenter.segment(trailing),part=>part.segment);
            trailing=glyphs.pop()||'';
            if(glyphs.length)visual.add(glyphs.join(''));
          },nativeSignal);
          if(trailing)visual.add(trailing);
          visual.drain();
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          if(!accepted(receipt,id))throw Error('HOLD_S03_COMMIT_RECEIPT');
          await checkHistory(id,data.message,answer,receipt.exchange_id,nativeSignal);
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          event({type:'done',status:'done',saved:true,s03_integrated:true,
            history_persisted:true,dialog_id:id,exchange_id:receipt.exchange_id,
            seconds:+((performance.now()-started)/1000).toFixed(2)});
        }catch(e){
          visual?.cancel();
          const renderFailure=visual?.failure();
          event({type:'error',error:renderFailure?renderFailure.message:
            nativeSignal.aborted?'STREAM_STOP_REQUESTED':String(e.message||'HOLD_NATIVE_STREAM').slice(0,150)});
        }finally{
          visual?.cancel();
          signal?.removeEventListener?.('abort',onAbort);
          if(!closed){closed=true;try{controller.close();}catch{}}
        }
      },
      cancel(){
        closed=true;visual?.cancel();
        upstreamAbort.abort();
        if(typeof window.dispatchEvent==='function'&&typeof CustomEvent==='function')
          window.dispatchEvent(new CustomEvent('nox:native-phase',{detail:{phase:'stopped'}}));
        signal?.removeEventListener?.('abort',onAbort);
      }
    });
    return responseJSONStream(body);
  }
  const responseJSONStream=body=>new Response(body,{status:200,headers:{
    'Content-Type':'text/event-stream','Cache-Control':'no-store','X-Accel-Buffering':'no'
  }});
  async function jsonChat(data,signal) {
    try{
      const id=await dialogId(data,signal);
      const upstream=await nativePost('/api/nox/chat/stream',{
        message:data.message,dialog_id:id,history:[],task:'general'
      },signal);
      const {answer,receipt}=await consume(upstream,()=>{},signal);
      if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');
      if(!accepted(receipt,id))throw Error('HOLD_S03_COMMIT_RECEIPT');
      await checkHistory(id,data.message,answer,receipt.exchange_id,signal);
      // JSON clients also have a cancellation boundary: a late abort during
      // S03 readback must never produce a persisted-success response.
      if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');
      return responseJSON({answer,model:'NOX HELION',dialog_id:id,
        exchange_id:receipt.exchange_id,history_persisted:true,s03_integrated:true});
    }catch(e){return errorResponse(String(e.message||'HOLD_NATIVE_JSON').slice(0,150));}
  }
  async function legacyDialogs(url,init) {
    try{
      const method=String(init?.method||'GET').toUpperCase();
      if(url.pathname==='/api/nox/dialogs/new'&&method==='POST'){
        const data=JSON.parse(init?.body||'{}');
        const created=await createDialog(data.title,init?.signal);
        return responseJSON({dialog_id:created.dialog_id,title:created.title||'Новый диалог'});
      }
      if(url.pathname==='/api/nox/history'&&method==='GET'){
        const did=url.searchParams.get('dialog_id');
        if(did){
          if(!ID.test(did))return errorResponse('HOLD_INVALID_DIALOG_SCOPE',422);
          const n=Number(url.searchParams.get('limit')||100);
          const limit=Number.isFinite(n)?Math.min(Math.max(Math.floor(n),1),100):100;
          const data=await nativeJSON('/api/ui/memory/dialogs/history?dialog_id='+did+'&limit='+limit,init);
          if(data.status!=='READY'||data.dialog_id!==did||!Array.isArray(data.messages))
            throw Error('HOLD_DIALOG_HISTORY_CONTRACT');
          return responseJSON({dialog_id:did,messages:data.messages.map(m=>({
            role:m.role,content:m.content,created_at:m.ts||'',status:'saved'
          }))});
        }
        const data=await nativeJSON('/api/ui/memory/dialogs?limit=80',init);
        if(data.status!=='READY'||!Array.isArray(data.dialogs))throw Error('HOLD_DIALOG_LIST_CONTRACT');
        return responseJSON({dialogs:data.dialogs.map(d=>({
          id:d.dialog_id,title:d.title,messages:'—'
        })),creator_messages_total:'—'});
      }
      if(url.pathname==='/api/nox/dialog/rename'&&method==='POST'){
        const data=JSON.parse(init?.body||'{}');
        if(!ID.test(String(data.dialog_id||''))||typeof data.title!=='string'||!data.title.trim())
          return errorResponse('HOLD_RENAME_SCOPE',422);
        const list=await nativeJSON('/api/ui/memory/dialogs?limit=80',init);
        if(list.status!=='READY'||!Array.isArray(list.dialogs))throw Error('HOLD_RENAME_LIST');
        const row=list.dialogs.find(d=>d.dialog_id===data.dialog_id);
        if(!row||!Number.isInteger(row.revision)||row.revision<1)throw Error('HOLD_RENAME_REVISION');
        const r=await nativePost('/api/ui/memory/dialogs/update',{
          dialog_id:data.dialog_id,revision:row.revision,title:data.title,confirmed:true
        },init?.signal);
        if(!r.ok)throw Error('HOLD_RENAME_'+await reason(r));
        const d=await r.json();
        if(d.dialog_id!==data.dialog_id||d.title!==data.title||
           !Number.isInteger(d.revision)||d.revision<=row.revision)
          throw Error('HOLD_RENAME_RECEIPT');
        return responseJSON({status:'READY',dialog_id:d.dialog_id,title:d.title,revision:d.revision});
      }
      return errorResponse('HOLD_UNSUPPORTED_LEGACY_ROUTE',405);
    }catch(e){return errorResponse(String(e.message||'HOLD_NATIVE_DIALOG').slice(0,150));}
  }
  window.fetch=function(input,init){
    const url=samePath(input);
    if(!url)return nativeFetch(input,init);
    const method=String(init?.method||(input instanceof Request?input.method:'GET')).toUpperCase();
    // Request objects carry their POST body and AbortSignal on input, not init.
    // The original V24/V22 owner routes must work for both fetch(url, init)
    // and fetch(new Request(url, init)); never bypass the scoped S03 gate.
    if(input instanceof Request&&!init?.body){
      const bridged=(url.pathname==='/api/nox/chat'&&method==='POST'&&!url.search)||
        (url.pathname==='/api/nox/history'&&method==='GET')||
        (url.pathname==='/api/nox/dialogs/new'&&method==='POST')||
        (url.pathname==='/api/nox/dialog/rename'&&method==='POST');
      if(!bridged)return nativeFetch(input,init);
      return input.clone().text().then(body=>window.fetch(url.href,{
        method,body:method==='GET'?undefined:body,
        signal:init?.signal||input.signal,
        headers:init?.headers||input.headers
      })).catch(()=>errorResponse('HOLD_REQUEST_BODY_UNAVAILABLE',422));
    }
    if(url.pathname==='/api/nox/chat'&&method==='POST'&&!url.search){
      let data;try{data=JSON.parse(init?.body);}catch{return Promise.resolve(errorResponse('INVALID_JSON',400));}
      if(!data||typeof data!=='object'||Array.isArray(data)||typeof data.message!=='string'||
         !data.message.trim()||data.message.length>8000)return Promise.resolve(errorResponse('INVALID_MESSAGE',422));
      return typeof data.request_id==='string'||Object.prototype.hasOwnProperty.call(data,'dialog_id')
        ?Promise.resolve(sseChat(data,init?.signal)):jsonChat(data,init?.signal);
    }
    if((url.pathname==='/api/nox/history'&&method==='GET')||
       (url.pathname==='/api/nox/dialogs/new'&&method==='POST')||
       (url.pathname==='/api/nox/dialog/rename'&&method==='POST'))
      return legacyDialogs(url,init);
    return nativeFetch(input,init);
  };
})();
