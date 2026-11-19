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
  function livePieces(text) {
    const glyphs=Array.isArray(text)?text:typeof Intl!=='undefined' && typeof Intl.Segmenter==='function'
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
  async function waitOrAbort(op,signal){
    if(!signal)return op();
    if(signal.aborted)throw Error('STREAM_STOP_REQUESTED');
    let stop;const cancelled=new Promise((_,reject)=>{
      stop=()=>reject(Error('STREAM_STOP_REQUESTED'));
      signal.addEventListener('abort',stop,{once:true});
    });
    try{return await Promise.race([Promise.resolve().then(op),cancelled]);}
    finally{signal.removeEventListener('abort',stop);}
  }
  const nativeBodyJSON=(response,signal)=>waitOrAbort(()=>response.json(),signal);
  const nativePost=(path,data,signal)=>waitOrAbort(()=>nativeFetch(path,{
    method:'POST',credentials:'same-origin',cache:'no-store',signal,
    headers:{'Content-Type':'application/json'},body:JSON.stringify(data)
  }),signal);
  async function reason(r,signal) {
    try{const j=await nativeBodyJSON(r,signal);return String(j.error||j.reason||'HTTP_'+r.status).slice(0,110);}
    catch{if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');return 'HTTP_'+r.status;}
  }
  const responseJSON=(data,status=200)=>new Response(JSON.stringify(data),{
    status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}
  });
  async function nativeJSON(path,init) {
    const r=await waitOrAbort(()=>nativeFetch(path,options(init)),init?.signal);
    if (!r.ok)throw Error('HOLD_NATIVE_ROUTE_'+await reason(r,init?.signal));
    return nativeBodyJSON(r,init?.signal);
  }
  async function createDialog(title,signal) {
    const r=await nativePost('/api/ui/memory/dialogs/create',{
      title:String(title||'Новый диалог').replace(/[\x00-\x1F\x7F]/g,' ').trim().slice(0,140)||'Новый диалог',
      confirmed:true
    },signal);
    if(!r.ok)throw Error('HOLD_DIALOG_CREATE_'+await reason(r,signal));
    const d=await nativeBodyJSON(r,signal);
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
    const pair=data.messages.filter(m=>m&&m.exchange_id===exchangeId);
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
  async function readNativeOrAbort(reader,signal) {
    if(!signal)return reader.read();
    if(signal.aborted)throw Error('STREAM_STOP_REQUESTED');
    let onAbort;
    const aborted=new Promise((_,reject)=>{
      onAbort=()=>{
        try{Promise.resolve(reader.cancel('STREAM_STOP_REQUESTED')).catch(()=>{});}catch{}
        reject(Error('STREAM_STOP_REQUESTED'));
      };
      signal.addEventListener('abort',onAbort,{once:true});
      if(signal.aborted)onAbort();
    });
    try{return await Promise.race([reader.read(),aborted]);}
    finally{signal.removeEventListener('abort',onAbort);}
  }
  async function consume(response,emit,signal) {
    if(!response.ok||!response.body)throw Error('HOLD_NATIVE_STREAM_'+await reason(response,signal));
    const reader=response.body.getReader(),decoder=new TextDecoder();
    let buf='',answer='',done=null,doneSeen=false,startSeen=false,preparingSeen=false;
    let nativeModel='UNKNOWN';
    const line=async str=>{
      if(!str.trim())return;
      let e;
      try{e=JSON.parse(str);}catch{throw Error('HOLD_NATIVE_FRAME_JSON');}
      if(!e||typeof e!=='object'||Array.isArray(e))throw Error('HOLD_NATIVE_FRAME_TYPE');
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
        nativeModel=typeof e.model==='string'
          ?e.model.replace(/[\x00-\x1F\x7F]/g,' ').trim().slice(0,96)||'UNKNOWN'
          :'UNKNOWN';
      } else if(e.type==='preparing') {
        if(preparingSeen||startSeen)throw Error('HOLD_NATIVE_PREPARING_ORDER');
        if(e.stream_mode!=='NATIVE_TOKEN_STREAM')throw Error('HOLD_NATIVE_STREAM_MODE');
        preparingSeen=true;
      } else {
        throw Error('HOLD_NATIVE_UNKNOWN_FRAME');
      }
    };
    try{
      for(;;){
        if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');
        const chunk=await readNativeOrAbort(reader,signal);
        if(chunk.done)break;
        buf+=decoder.decode(chunk.value,{stream:true});
        let j;while((j=buf.indexOf('\n'))>=0){
          if(j>300000)throw Error('HOLD_NATIVE_FRAME_TOO_LARGE');
          await line(buf.slice(0,j).trim());buf=buf.slice(j+1);
        }
        if(buf.length>300000)throw Error('HOLD_NATIVE_FRAME_TOO_LARGE');
        if(doneSeen){
          if(buf.trim())throw Error('HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE');
          break;
        }
      }
      buf+=decoder.decode();
      if(buf.trim())throw Error('HOLD_INCOMPLETE_NATIVE_FRAME');
      if(!done||!answer.trim())throw Error('HOLD_INCOMPLETE_NATIVE_RESPONSE');
      return {answer,receipt:Object.assign(done,{native_model_label:nativeModel}),nativeModel};
    }finally{
      try{Promise.resolve(reader.cancel('STREAM_CLOSED')).catch(()=>{});}catch{}
    }
  }
  function sseChat(data,signal) {
    let closed=false,phase;const started=performance.now();let firstVisibleMs=null;
    const upstreamAbort=new AbortController();
    const onAbort=()=>upstreamAbort.abort();
    if(signal?.aborted)upstreamAbort.abort();
    else signal?.addEventListener?.('abort',onAbort,{once:true});
    const nativeSignal=upstreamAbort.signal;
    const body=new ReadableStream({
      async start(controller){
        const event=payload=>{
          if(closed)return;
          if(payload.type==='token'&&firstVisibleMs===null&&typeof payload.t==='string'&&payload.t.trim())
            firstVisibleMs=Math.round(performance.now()-started);
          const p={meta:'waiting',token:'speaking',done:'idle',error:'error'}[payload.type];
          if(p&&p!==phase&&(phase=p)&&typeof window.dispatchEvent==='function'&&typeof CustomEvent==='function')
            window.dispatchEvent(new CustomEvent('nox:native-phase',{detail:{phase:p}}));
          if(!closed)controller.enqueue(enc.encode('data: '+JSON.stringify(payload)+'\n\n'));
        };
        try {
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          const id=await dialogId(data,nativeSignal);
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          event({type:'meta',dialog_id:id,model_label:'UNKNOWN',
            answer_source:'NATIVE_PENDING',model_identity_verified:false});
          const upstream=await nativePost('/api/nox/chat/stream',{
            message:data.message,dialog_id:id,task:'general',history:[]
          },nativeSignal);
          const segmenter=typeof Intl!=='undefined'&&typeof Intl.Segmenter==='function'?new Intl.Segmenter(undefined,{granularity:'grapheme'}):null;
          let trailing='',paintWaits=0;
          const emitPieces=async t=>{
            const parts=livePieces(t);
            for(let index=0;index<parts.length;index++){
              if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
              event({type:'token',t:parts[index]});
              if(index<parts.length-1&&
                 (typeof document==='undefined'||document.visibilityState!=='hidden')&&
                 !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches&&paintWaits++<2){
                await new Promise(resolve=>{
                  let settled=false,frameId,timerId;
                  const visibility=()=>{if(document.visibilityState==='hidden')finish();};
                  const finish=()=>{
                    if(settled)return;
                    settled=true;
                    if(typeof document!=='undefined')document.removeEventListener?.('visibilitychange',visibility);
                    nativeSignal.removeEventListener('abort',finish);
                    if(frameId!==undefined&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(frameId);
                    if(timerId!==undefined&&typeof clearTimeout==='function')clearTimeout(timerId);
                    resolve();
                  };
                  if(typeof document!=='undefined'){document.addEventListener?.('visibilitychange',visibility);visibility();}
                  if(!settled){nativeSignal.addEventListener('abort',finish,{once:true});if(nativeSignal.aborted)finish();}else return;
                  if(typeof requestAnimationFrame==='function'){
                    frameId=requestAnimationFrame(finish);
                    if(settled&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(frameId);
                  }
                  if(typeof setTimeout==='function'){
                    timerId=setTimeout(finish,18);
                    if(settled&&typeof clearTimeout==='function')clearTimeout(timerId);
                  } else if(typeof requestAnimationFrame!=='function')finish();
                });
              }
            }
          };
          const {answer,receipt}=await consume(upstream,async t=>{
            trailing+=t;
            if(!segmenter){
              const ascii=trailing.match(/^[\x20-\x7e\u00a1\u00ab\u00b7\u00bb\u00bf\u00c0-\u024f\u0400-\u052f\u4e00-\u9fff\uac00-\ud7af\u2010-\u2015\u2018-\u201f\u2026]{2,}/);
              if(ascii){
                const safe=ascii[0].slice(0,-1);
                trailing=trailing.slice(safe.length);
                await emitPieces(safe);
              }
              return;
            }
            const glyphs=Array.from(segmenter.segment(trailing),part=>part.segment);
            trailing=glyphs.pop()||'';
            if(glyphs.length)await emitPieces(glyphs);
          },nativeSignal);
          if(trailing)await emitPieces(trailing);
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          if(!accepted(receipt,id))throw Error('HOLD_S03_COMMIT_RECEIPT');
          await checkHistory(id,data.message,answer,receipt.exchange_id,nativeSignal);
          if(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');
          event({type:'done',status:'done',saved:true,s03_integrated:true,
            history_persisted:true,dialog_id:id,exchange_id:receipt.exchange_id,
            model_label:receipt.native_model_label||'UNKNOWN',
            model_identity_verified:false,answer_source:'LIVE_NOX',
            first_visible_token_ms:firstVisibleMs,
            seconds:+((performance.now()-started)/1000).toFixed(2)});
        }catch(e){
          event({type:'error',
            error:nativeSignal.aborted?'STREAM_STOP_REQUESTED':String(e.message||'HOLD_NATIVE_STREAM').slice(0,150),
            gpu_stop_verified:false});
        }finally{
          signal?.removeEventListener?.('abort',onAbort);
          if(!closed){closed=true;try{controller.close();}catch{}}
        }
      },
      cancel(){
        closed=true;
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
      const {answer,receipt,nativeModel}=await consume(upstream,()=>{},signal);
      if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');
      if(!accepted(receipt,id))throw Error('HOLD_S03_COMMIT_RECEIPT');
      await checkHistory(id,data.message,answer,receipt.exchange_id,signal);
      if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');
      return responseJSON({answer,model:nativeModel,model_identity_verified:false,dialog_id:id,
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
            role:m.role,content:m.content,exchange_id:m.exchange_id||null,created_at:m.ts||'',status:'saved'
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
        if(!r.ok)throw Error('HOLD_RENAME_'+await reason(r,init?.signal));
        const d=await nativeBodyJSON(r,init?.signal);
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
