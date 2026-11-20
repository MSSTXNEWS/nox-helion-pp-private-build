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
function eventData(record){const x=record.split(/\r?\n/).filter(y=>y.startsWith('data:')).map(y=>y.slice(5).trimStart()).join('\n');
  if(x==='[DONE]')return 'done';
  try{const t=JSON.parse(x)?.choices?.[0]?.delta?.content;return typeof t==='string'&&/\S/u.test(t)?'text':null;}catch{return null;}}
export async function capture({ws,count=2,timeoutMs=45000,makeSession,onReady}={}){
  if(!/^ws:\/\/(localhost|127\.0\.0\.1):\d+\//.test(ws||''))throw Error('LOCAL_CDP_ONLY');
  if(!Number.isInteger(count)||count<1||count>6)throw Error('BAD_COUNT');
  const c=await(makeSession?makeSession():new Cdp(ws).open()),active=new Map(),finished=[];
  let yes,no;const completion=new Promise((a,b)=>{yes=a;no=b;});
  const timer=setTimeout(()=>no(Error('CDP_TIMEOUT')),timeoutMs);
  const observe=(x,buffer,timestamp)=>{
    if(!x.streaming)return;
    x.bytes+=buffer.length;if(x.bytes>2_000_000){x.missing=true;return;}
    x.partial+=buffer.toString('utf8');
    for(;;){const m=/\r?\n\r?\n/.exec(x.partial);if(!m)break;
      const data=x.partial.slice(0,m.index);x.partial=x.partial.slice(m.index+m[0].length);
      const kind=eventData(data),ms=Math.round((timestamp-x.start)*1000);
      if(kind==='text'&&x.ttft===null)x.ttft=ms;
      if(kind==='done'&&x.done===null)x.done=ms;}
  };
  c.on((method,p)=>{
    if(method==='Network.requestWillBeSent'){
      let path;try{path=new URL(p.request.url).pathname;}catch{return;}
      if(p.request.method!=='POST'||!paths.has(path))return;
      if(active.has(p.requestId)){no(Error('DUPLICATE_CDP_ID'));return;}
      const x={id:p.requestId,start:p.timestamp,request:null,response:null,status:null,mime:null,first:null,ttft:null,done:null,close:null,streaming:false,missing:false,bytes:0,partial:''};
      active.set(p.requestId,x);
      const record=s=>{if(typeof s==='string')x.request=hash(Buffer.from(s));};
      if(typeof p.request.postData==='string')record(p.request.postData);
      else c.send('Network.getRequestPostData',{requestId:p.requestId}).then(v=>record(v.postData)).catch(()=>{});
      return;
    }
    const x=active.get(p.requestId);if(!x)return;
    if(method==='Network.responseReceived'){
      x.status=p.response?.status;x.mime=p.response?.mimeType;x.first=Math.round((p.timestamp-x.start)*1000);
      c.send('Network.streamResourceContent',{requestId:p.requestId}).then(v=>{
        if(v.bufferedData)x.missing=true;
        x.streaming=true;
      }).catch(()=>{x.missing=true;});
    }
    if(method==='Network.dataReceived'){
      if(p.data){if(!x.streaming)x.missing=true;observe(x,Buffer.from(p.data,'base64'),p.timestamp);}
      else x.missing=true;
    }
    if(method==='Network.loadingFinished'||method==='Network.loadingFailed'){
      x.close=Math.round((p.timestamp-x.start)*1000);
      if(method==='Network.loadingFailed')x.missing=true;
      c.send('Network.getResponseBody',{requestId:p.requestId}).then(v=>{
        if(typeof v.body==='string')x.response=hash(v.base64Encoded?Buffer.from(v.body,'base64'):Buffer.from(v.body));
      }).catch(()=>{}).finally(()=>{finished.push(x);if(finished.length>=count)yes(finished);});
    }
  });
  try{
    await c.send('Network.enable');const version=await c.send('Browser.getVersion');
    if(onReady)await onReady(c);
    const records=await completion;
    const turns=records.map((x,i)=>({turn:i+1,cdp_request_id:x.id,request_sha256:x.request,cdp_decoded_body_sha256:x.response,
      status:x.status,mime:x.mime,first_network_byte_ms:x.first,ttft_ms:!x.missing?x.ttft:null,
      sse_done_ms:!x.missing?x.done:null,close_ms:x.close,stream_timing_complete:!x.missing&&x.streaming}));
    const unique=new Set(turns.map(x=>x.cdp_request_id)).size===turns.length;
    const valid=unique&&turns.every(x=>x.request_sha256&&x.cdp_decoded_body_sha256&&x.status===200&&x.mime==='text/event-stream');
    const timed=valid&&turns.every(x=>x.stream_timing_complete&&x.ttft_ms!==null&&x.sse_done_ms!==null&&x.ttft_ms<=x.sse_done_ms&&x.sse_done_ms<=x.close_ms);
    return {schema:'nox-b4-cdp-v1',chrome_product:version.product,cdp_consistent:Boolean(valid),ttft_sse_verified:Boolean(timed),
      browser_authenticated:false,remote_attested:false,native_verified:false,canonical_s03_verified:false,one_model_post_per_turn_verified:false,
      tcp_wire_verified:false,turns};
  }finally{clearTimeout(timer);c.close();}
}
