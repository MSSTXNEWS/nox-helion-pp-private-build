/** B4 CDP observer: read-only, digest-only; CDP != authenticated remote attestation. Node 22+. */
import {createHash} from 'node:crypto';
const hash=s=>createHash('sha256').update(s).digest('hex');
const paths=new Set(['/api/nox/chat','/api/nox/chat/stream','/nox/chat']);
export class Cdp {
  constructor(url){this.url=url;this.next=0;this.pending=new Map();}
  async open(){
    this.ws=new WebSocket(this.url);
    await new Promise((yes,no)=>{this.ws.addEventListener('open',yes,{once:true});this.ws.addEventListener('error',no,{once:true});});
    this.ws.addEventListener('message',e=>{
      let p;try{p=JSON.parse(e.data);}catch{return;}
      if(p.id){const cb=this.pending.get(p.id);if(cb){this.pending.delete(p.id);p.error?cb.no(Error(p.error.message)):cb.yes(p.result||{});}}
      else if(p.method)this.listener?.(p.method,p.params||{});
    });
    this.ws.addEventListener('close',()=>{for(const x of this.pending.values())x.no(Error('CDP_DISCONNECTED'));this.pending.clear();});return this;
  }
  send(method,params={}){return new Promise((yes,no)=>{const id=++this.next;this.pending.set(id,{yes,no});this.ws.send(JSON.stringify({id,method,params}));});}
  on(fn){this.listener=fn;}
  close(){this.ws?.close();}
}
// CDP Headers are normalized even for HTTP/2; headersText may be absent.
function ambiguousEncoding(headers){
  if(!headers||typeof headers!=='object'||Array.isArray(headers))return true;
  const entries=Object.entries(headers).filter(([k])=>k.toLowerCase()==='content-encoding');
  return entries.length>1||entries.some(([,v])=>typeof v!=='string'||v.split(',').some(x=>x.trim().toLowerCase()!=='identity'));
}
function cacheProvenance(r){
  return Boolean(r?.fromDiskCache||r?.fromServiceWorker||r?.fromPrefetchCache||
    r?.fromEarlyHints||r?.cacheStorageCacheName||r?.serviceWorkerResponseSource||
    r?.serviceWorkerRouterInfo?.matchedSourceType||r?.serviceWorkerRouterInfo?.actualSourceType);
}
// JSON.parse can map legal JSON 1e309 / -1e309 into nonfinite JS numbers.
// Every parsed number must stay finite, including ignored metadata / usage.
function finiteJsonNumbers(value){
  const pending=[value];
  while(pending.length){
    const v=pending.pop();
    if(typeof v==='number'&&!Number.isFinite(v))return false;
    if(v!==null&&typeof v==='object')
      for(const child of Object.values(v))pending.push(child);
  }
  return true;
}
// Fail closed on malformed or explicit error SSE before a later valid [DONE].
function eventData(record){
  const data=[];let eventName=null;
  for(const line of record.split(/\r?\n/)){
    if(line===''||line.startsWith(':'))continue; // SSE comments are heartbeats, not JSON
    if(line.startsWith('event:')){
      if(eventName!==null)return {invalid:true};
      eventName=line.slice(6).trim();continue;
    }
    if(line.startsWith('data:')){data.push(line.slice(5).replace(/^ /,''));continue;}
    if(line.startsWith('id:')||line.startsWith('retry:'))continue;
    return {invalid:true};
  }
  if(eventName==='error')return {invalid:true};
  if(!data.length)return eventName===null||['ping','heartbeat','keepalive'].includes(eventName)?{ignored:true}:{invalid:true};
  const payload=data.join('\n');
  if(payload==='[DONE]')return eventName===null||eventName==='message'?{done:true}:{invalid:true};
  if(eventName!==null&&!['message','usage','ping','heartbeat','keepalive'].includes(eventName))return {invalid:true};
  let obj;try{obj=JSON.parse(payload);}catch{return {invalid:true};}
  if(!obj||typeof obj!=='object'||Array.isArray(obj)||Object.hasOwn(obj,'error'))return {invalid:true};
  if(!finiteJsonNumbers(obj))return {invalid:true};
  const usage=obj.usage&&typeof obj.usage==='object'&&!Array.isArray(obj.usage);
  if(Array.isArray(obj.choices)){
    if(obj.choices.length===0)return usage?{ignored:true}:{invalid:true};
    const first=obj.choices[0];
    if(!first||typeof first!=='object'||Array.isArray(first))return {invalid:true};
    const delta=first.delta;
    if(!delta||typeof delta!=='object'||Array.isArray(delta))return {invalid:true};
    if(Object.hasOwn(delta,'content')&&delta.content!==null&&typeof delta.content!=='string')return {invalid:true};
    // [DONE] is not proof of successful model completion: length/filter/tool
    // finishes are distinct terminal outcomes and cannot certify TTFT/completion.
    const finish=first.finish_reason;
    if(finish!==undefined&&finish!==null&&finish!=='stop')return {invalid:true};
    if(finish==='stop'&&typeof delta.content==='string'&&delta.content.length>0)return {invalid:true};
    if(typeof delta.content==='string')return {text:delta.content,stop:finish==='stop'};
    return finish==='stop'?{stop:true}:{ignored:true};
  }
  if(usage)return {ignored:true};
  if(['ping','heartbeat','keepalive'].includes(eventName)&&Object.keys(obj).length===0)return {ignored:true};
  return {invalid:true};
}
export async function capture({ws,count=2,timeoutMs=45000,makeSession,onReady}={}){
  if(!/^ws:\/\/(localhost|127\.0\.0\.1):\d+\//.test(ws||''))throw Error('LOCAL_CDP_ONLY');
  if(!Number.isInteger(count)||count<1||count>6)throw Error('BAD_COUNT');
  const c=await(makeSession?makeSession():new Cdp(ws).open()),active=new Map(),finished=[];
  let yes,no;const completion=new Promise((a,b)=>{yes=a;no=b;});
  const timer=setTimeout(()=>no(Error('CDP_TIMEOUT')),timeoutMs);
  const validTime=t=>typeof t==='number'&&Number.isFinite(t)&&t>=0;
  const millis=(x,t)=>{
    if(!validTime(x.start)||!validTime(t)||t<x.start){x.missing=true;return null;}
    const delta=(t-x.start)*1000,rounded=Math.round(delta);
    if(!Number.isSafeInteger(rounded)||rounded<0){x.missing=true;return null;}
    return rounded;
  };
  const chronological=(x,t)=>{
    if(!validTime(x.start)||!validTime(t)||t<x.start||
       (x.lastTimestamp!==null&&t<x.lastTimestamp)){x.missing=true;return false;}
    x.lastTimestamp=t;return true;
  };
  const observe=(x,buffer,timestamp)=>{
    if(!x.streaming||x.missing)return;
    x.bytes+=buffer.length;if(x.bytes>2_000_000){x.missing=true;return;}
    // CDP delivers decoded resource data; this is NOT a raw TCP-byte witness.
    x.streamHasher.update(buffer);
    try{x.partial+=x.decoder.decode(buffer,{stream:true});}
    catch{x.missing=true;return;}
    for(;;){const m=/\r?\n\r?\n/.exec(x.partial);if(!m)break;
      const data=x.partial.slice(0,m.index);x.partial=x.partial.slice(m.index+m[0].length);
      // Any frame after the first terminal is ambiguous, even if it is not JSON.
      // Preserve decoded-body digest checks but never promote an invalid SSE stream.
      if(x.done!==null&&data.trim()!==''){x.missing=true;return;}
      const event=eventData(data),ms=millis(x,timestamp);
      if(!event||event.invalid){x.missing=true;return;}
      if(event?.stop){
        if(x.finishStop||x.done!==null){x.missing=true;return;}
        x.finishStop=true;
      }
      if(Object.hasOwn(event,'text')){
        if(x.finishStop&&event.text.length>0){x.missing=true;return;}
        x.visibleText+=event.text;
        if(/\S/u.test(event.text)&&x.ttft===null&&ms!==null){x.ttft=ms;x.ttftAt=timestamp;}
      }
      if(event?.done){
        if(x.done!==null||ms===null||!x.finishStop){x.missing=true;return;}
        x.done=ms;x.doneAt=timestamp;
      }}
  };
  c.on((method,p)=>{
    if(method==='Network.requestWillBeSent'){
      let path;try{path=new URL(p.request.url).pathname;}catch{return;}
      if(p.request.method!=='POST'||!paths.has(path))return;
      if(active.has(p.requestId)){no(Error('DUPLICATE_CDP_ID'));return;}
      const x={id:p.requestId,start:p.timestamp,request:null,response:null,status:null,mime:null,first:null,ttft:null,done:null,close:null,streaming:false,missing:!validTime(p.timestamp),lastTimestamp:validTime(p.timestamp)?p.timestamp:null,firstAt:null,ttftAt:null,doneAt:null,closeAt:null,bytes:0,partial:'',decoder:new TextDecoder('utf-8',{fatal:true}),visibleText:'',streamHasher:createHash('sha256'),streamDigest:null,bodyMatchesStream:false,encoded:false,extraExpected:null,extraSeen:0,requestLookupPending:null,finishStop:false};
      active.set(p.requestId,x);
      const record=s=>{if(typeof s==='string')x.request=hash(Buffer.from(s));};
      if(typeof p.request.postData==='string')record(p.request.postData);
      else x.requestLookupPending=Promise.resolve()
        .then(()=>c.send('Network.getRequestPostData',{requestId:p.requestId}))
        .then(v=>record(v?.postData)).catch(()=>{});
      return;
    }
    const x=active.get(p.requestId);if(!x)return;
    if(method==='Network.requestServedFromCache'){x.missing=true;return;}
    // ExtraInfo can precede OR follow responseReceived; cached 200 can hide a 304.
    if(method==='Network.responseReceivedExtraInfo'){
      x.extraSeen++;
      if(x.extraSeen!==1||x.extraExpected===false||p.statusCode!==200||
         ambiguousEncoding(p.headers)){x.missing=true;x.encoded=true;}
      return;
    }
    if(method==='Network.responseReceived'){
      x.status=p.response?.status;x.mime=p.response?.mimeType;
      if(chronological(x,p.timestamp)){x.first=millis(x,p.timestamp);x.firstAt=p.timestamp;}
      // Chrome signals whether ExtraInfo will arrive; unknown means a HOLD.
      x.extraExpected=typeof p.hasExtraInfo==='boolean'?p.hasExtraInfo:null;
      if(x.extraExpected===null||(x.extraExpected===false&&x.extraSeen!==0)||
         cacheProvenance(p.response)||ambiguousEncoding(p.response?.headers)){
        x.missing=true;x.encoded=true;
      }
      c.send('Network.streamResourceContent',{requestId:p.requestId}).then(v=>{
        if(v.bufferedData)x.missing=true;
        x.streaming=true;
      }).catch(()=>{x.missing=true;});
    }
    if(method==='Network.dataReceived'){
      if(!chronological(x,p.timestamp))return;
      if(p.data){if(!x.streaming)x.missing=true;observe(x,Buffer.from(p.data,'base64'),p.timestamp);}
      else x.missing=true;
    }
    if(method==='Network.loadingFinished'||method==='Network.loadingFailed'){
      if(x.close!==null){x.missing=true;return;}
      if(chronological(x,p.timestamp)){x.close=millis(x,p.timestamp);x.closeAt=p.timestamp;}
      if(method==='Network.loadingFailed')x.missing=true;
      // A final incomplete UTF-8 code point or unclosed SSE event is NOT a clean stream.
      if(!x.streaming||x.extraExpected===null||
         (x.extraExpected===true&&x.extraSeen!==1)||
         (x.extraExpected===false&&x.extraSeen!==0))x.missing=true;
      try{x.partial+=x.decoder.decode();}catch{x.missing=true;}
      if(x.partial.length!==0)x.missing=true;
      x.streamDigest=x.streamHasher.digest('hex');
      c.send('Network.getResponseBody',{requestId:p.requestId}).then(v=>{
        if(typeof v.body!=='string'){x.missing=true;return;}
        // Base64 bytes or UTF-8 text are the only unambiguous CDP decoded-body forms here.
        if(typeof v.base64Encoded!=='boolean'){x.missing=true;return;}
        if(v.base64Encoded && (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(v.body))){x.missing=true;return;}
        const body=v.base64Encoded?Buffer.from(v.body,'base64'):Buffer.from(v.body,'utf8');
        x.response=hash(body);
        x.bodyMatchesStream=!x.missing&&!x.encoded&&x.bytes===body.length&&x.streamDigest===x.response;
        if(!x.bodyMatchesStream)x.missing=true;
      }).catch(()=>{x.missing=true;}).finally(()=>{finished.push(x);if(finished.length>=count)yes(finished);});
    }
  });
  try{
    await c.send('Network.enable');const version=await c.send('Browser.getVersion');
    if(onReady)await onReady(c);
    const records=await completion;
    // Response-body completion can beat the asynchronous request-data CDP ACK.
    // Wait only for already-issued metadata queries, never replay the model POST.
    const requestLookups=records.map(x=>x.requestLookupPending).filter(Boolean);
    if(requestLookups.length){
      let guard;
      try{
        await Promise.race([
          Promise.allSettled(requestLookups),
          new Promise(resolve=>{guard=setTimeout(resolve,750);})
        ]);
      }finally{clearTimeout(guard);}
    }
    // Rejected, missing or timed-out request metadata remains fail-closed.
    const turns=records.map((x,i)=>({turn:i+1,cdp_request_id:x.id,request_sha256:x.request,cdp_decoded_body_sha256:x.response,
      cdp_streamed_body_sha256:x.streamDigest,cdp_decoded_body_matches_stream:x.bodyMatchesStream,
      status:x.status,mime:x.mime,first_network_byte_ms:x.first,ttft_ms:!x.missing?x.ttft:null,
      sse_done_ms:!x.missing?x.done:null,close_ms:x.close,
      visible_text_sha256:!x.missing?hash(Buffer.from(x.visibleText,'utf8')):null,
      stream_timing_complete:!x.missing&&x.streaming&&x.bodyMatchesStream}));
    const unique=new Set(turns.map(x=>x.cdp_request_id)).size===turns.length;
    const valid=unique&&turns.every(x=>x.request_sha256&&x.cdp_decoded_body_sha256&&x.cdp_decoded_body_matches_stream&&x.status===200&&x.mime==='text/event-stream');
    const timed=valid&&turns.every((t,i)=>{
      const x=records[i],raw=[x.start,x.firstAt,x.ttftAt,x.doneAt,x.closeAt];
      const ms=[t.first_network_byte_ms,t.ttft_ms,t.sse_done_ms,t.close_ms];
      return t.stream_timing_complete&&raw.every(validTime)&&
        x.start<=x.firstAt&&x.firstAt<=x.ttftAt&&x.ttftAt<=x.doneAt&&x.doneAt<=x.closeAt&&
        ms.every(v=>Number.isSafeInteger(v)&&v>=0)&&
        ms[0]<=ms[1]&&ms[1]<=ms[2]&&ms[2]<=ms[3];
    });
    return {schema:'nox-b4-cdp-v1',chrome_product:version.product,cdp_consistent:Boolean(valid),ttft_sse_verified:Boolean(timed),
      browser_authenticated:false,remote_attested:false,native_verified:false,canonical_s03_verified:false,one_model_post_per_turn_verified:false,
      tcp_wire_verified:false,turns};
  }finally{clearTimeout(timer);c.close();}
}
