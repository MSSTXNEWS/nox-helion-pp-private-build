/** NOX B4 isolated SSE latency witness. Node 22+, read-only, digest-only.
 * Browser authenticity, model tokens/s and canonical S03 are OUT OF SCOPE.
 * A completed response requires an actual EOF after finish_reason=stop and [DONE].
 */
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';

const digest=s=>createHash('sha256').update(s).digest('hex');
const printable=s=>/[\p{L}\p{N}\p{P}\p{S}]/u.test(s);
const fail=code=>Object.assign(new Error(code),{code});

export async function measureSseResponse(response,options={}){
  const {startedAt=performance.now(),clock=()=>performance.now(),
    idleTimeoutMs=5000,totalTimeoutMs=60000,
    maxEventBytes=262144,maxTotalBytes=8388608}=options;
  if(!response?.body?.getReader || response.status!==200 ||
     !/^(?:text\/event-stream)(?:\s*;|\s*$)/i.test(response.headers?.get('content-type')||''))
    throw fail('B4_NOT_SSE_200');
  for(const [name,value,min,max] of [
    ['idleTimeoutMs',idleTimeoutMs,10,120000],
    ['totalTimeoutMs',totalTimeoutMs,10,1800000],
    ['maxEventBytes',maxEventBytes,128,8388608],
    ['maxTotalBytes',maxTotalBytes,128,67108864]])
    if(!Number.isInteger(value)||value<min||value>max)throw fail('B4_INVALID_'+name);
  if(!Number.isFinite(startedAt))throw fail('B4_INVALID_STARTED_AT');
  const reader=response.body.getReader();
  const decoder=new TextDecoder('utf-8',{fatal:true});
  const rawHash=createHash('sha256');
  let total=0,firstByte=null,ttft=null,sseDone=null,close=null;
  let line='',frame=[],frameBytes=0,seenStop=false,seenDone=false,visible='';
  const nowMs=()=>Math.max(0,clock()-startedAt);
  function acceptFrame(){
    const lines=frame;frame=[];frameBytes=0;
    const payload=lines.filter(x=>x.startsWith('data:')).map(x=>x.slice(5).replace(/^ /,'')).join('\n');
    if(!payload)return;
    if(seenDone)throw fail('B4_POST_DONE_EVENT');
    if(payload==='[DONE]'){
      if(!seenStop)throw fail('B4_DONE_WITHOUT_STOP');
      seenDone=true;sseDone=nowMs();return;
    }
    let parsed;
    try{parsed=JSON.parse(payload);}catch{throw fail('B4_MALFORMED_EVENT');}
    if(!parsed||!Array.isArray(parsed.choices)||parsed.choices.length!==1)
      throw fail('B4_BAD_CHOICES');
    const choice=parsed.choices[0];
    const text=choice?.delta?.content??choice?.text??'';
    if(typeof text!=='string')throw fail('B4_BAD_TEXT');
    if(seenStop&&text.length)throw fail('B4_TEXT_AFTER_STOP');
    if(text){visible+=text;if(ttft===null&&printable(text))ttft=nowMs();}
    const reason=choice?.finish_reason;
    if(reason!==null&&reason!==undefined){
      if(reason!=='stop'||seenStop)throw fail('B4_BAD_FINISH_REASON');
      seenStop=true;
    }
  }
  function feedText(text){
    for(const c of text){
      if(c==='\n'){
        const current=line.endsWith('\r')?line.slice(0,-1):line;
        line='';
        if(current==='')acceptFrame();
        else frame.push(current);
      }else line+=c;
      if(Buffer.byteLength(line,'utf8')+frameBytes>maxEventBytes)
        throw fail('B4_EVENT_TOO_LARGE');
      if(c==='\n'&&frame.length)frameBytes=Buffer.byteLength(frame.join('\n'),'utf8');
    }
  }
  async function boundedRead(){
    let timer;
    const remaining=totalTimeoutMs-(clock()-startedAt);
    if(remaining<=0)throw fail('B4_TOTAL_TIMEOUT');
    const wait=Math.min(idleTimeoutMs,remaining);
    try{return await Promise.race([
      reader.read(),
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(fail(wait===remaining?'B4_TOTAL_TIMEOUT':'B4_IDLE_TIMEOUT')),wait);})
    ]);}finally{clearTimeout(timer);}
  }
  try{
    for(;;){
      const {done,value}=await boundedRead();
      if(done)break;
      if(!(value instanceof Uint8Array))throw fail('B4_NONBYTE_CHUNK');
      if(value.length===0)continue;
      if(firstByte===null)firstByte=nowMs();
      total+=value.length;
      if(total>maxTotalBytes)throw fail('B4_STREAM_TOO_LARGE');
      rawHash.update(value);
      try{feedText(decoder.decode(value,{stream:true}));}
      catch(e){if(e?.code)throw e;throw fail('B4_INVALID_UTF8');}
    }
    try{feedText(decoder.decode());}
    catch(e){if(e?.code)throw e;throw fail('B4_INVALID_UTF8');}
    close=nowMs();
    if(line||frame.length)throw fail('B4_UNFRAMED_EOF');
    if(!seenStop||!seenDone||ttft===null)throw fail('B4_INCOMPLETE_SSE');
    if(close<sseDone||sseDone<ttft)throw fail('B4_TIME_ORDER_INVALID');
    return Object.freeze({
      verified:true,first_byte_ms:firstByte,ttft_ms:ttft,
      sse_done_ms:sseDone,completion_ms:close,
      body_bytes:total,body_sha256:rawHash.digest('hex'),
      visible_text_sha256:digest(visible),
      // Never claim a local fetch is an authenticated model/browser/S03 proof.
      browser_authenticated:false,native_verified:false,canonical_s03_verified:false,
      model_tokens_per_second:null
    });
  }catch(e){try{await reader.cancel();}catch{}throw e;}
  finally{reader.releaseLock();}
}
