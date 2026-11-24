/** NOX B4 isolated SSE latency witness. Node 22+, read-only, digest-only.
 * Browser authenticity, model tokens/s and canonical S03 are OUT OF SCOPE.
 * A completed response requires an actual EOF after finish_reason=stop and [DONE].
 */
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {request as httpRequest} from 'node:http';
import {request as httpsRequest} from 'node:https';
import {Readable} from 'node:stream';
import {createGunzip} from 'node:zlib';

const printable=s=>/[\p{L}\p{N}\p{P}\p{S}]/u.test(s);
const fail=code=>Object.assign(new Error(code),{code});


// Bound staged UTF-16 to 4096 code units (at most 12 KiB encoded UTF-8).
// Large deltas bypass staging. Caller joins cross-delta surrogate pairs
// before update; final lone high surrogate is supplied only at actual EOF.
export function createBatchedVisibleHash(){
  const hash=createHash('sha256'),limit=4096;
  let staged='';
  function flush(){
    if(staged){hash.update(staged,'utf8');staged='';}
  }
  return {
    update(chunk){
      if(!chunk)return;
      if(staged.length+chunk.length>limit)flush();
      if(chunk.length>=limit)hash.update(chunk,'utf8');
      else staged+=chunk;
    },
    get bufferedCodeUnits(){return staged.length;},
    digest(){flush();return hash.digest('hex');}
  };
}

export async function measureSseResponse(response,options={}){
  const {startedAt=performance.now(),clock=()=>performance.now(),
    idleTimeoutMs=5000,totalTimeoutMs=60000,
    maxEventBytes=262144,maxTotalBytes=8388608,
    protocol='openai',expectedDialogId=null}=options;
  if(!['openai','nox-browser'].includes(protocol))throw fail('B4_INVALID_PROTOCOL');
  const browser=protocol==='nox-browser';
  if(browser&&(typeof expectedDialogId!=='string'||! /^[a-f0-9]{32}$/.test(expectedDialogId)))
    throw fail('B4_BROWSER_DIALOG_REQUIRED');
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
  // A browser/undici fetch can silently accept a missing gzip trailer after
  // exposing [DONE]. Integrity requires an untouched compressed byte stream.
  const encoding=(response.headers?.get('content-encoding')||'').trim().toLowerCase();
  if(encoding&&encoding!=='identity')throw fail('B4_COMPRESSED_TRANSPORT_UNVERIFIABLE');
  const reader=response.body.getReader();
  const decoder=new TextDecoder('utf-8',{fatal:true});
  const rawHash=createHash('sha256');
  let total=0,firstByte=null,ttft=null,sseDone=null,close=null;
  let line='',lineBytes=0,frame=[],frameBytes=0,seenStop=false,seenDone=false;
  // Hash the visible stream in bounded batches; retain at most one dangling UTF-16
  // high surrogate because distinct JSON deltas can split one Unicode scalar.
  const visibleHash=createBatchedVisibleHash();
  let pendingHighSurrogate='';
  let browserMeta=false,browserExchangeId=null;
  const nowMs=()=>Math.max(0,clock()-startedAt);
  // Timers can run late if parsing or the event loop stalls. A settled read
  // is not proof that the monotonic absolute deadline was respected.
  function assertTotalDeadline(){
    if(clock()-startedAt>=totalTimeoutMs)throw fail('B4_TOTAL_TIMEOUT');
  }
  function appendVisible(text){
    if(!text)return;
    let chunk=pendingHighSurrogate+text;
    pendingHighSurrogate='';
    // Node's UTF-8 encoding replaces an unpaired surrogate; postponing only
    // a terminal high surrogate preserves hash(Buffer.from(fullVisibleText))
    // if the next delta begins with its low surrogate.
    const tail=chunk.charCodeAt(chunk.length-1);
    if(tail>=0xD800&&tail<=0xDBFF){
      pendingHighSurrogate=chunk.slice(-1);
      chunk=chunk.slice(0,-1);
    }
    if(chunk){
      visibleHash.update(chunk);
      // First-printable TTFT must also recognize cross-delta emoji.
      if(ttft===null&&printable(chunk))ttft=nowMs();
    }
  }
  function acceptFrame(){
    const lines=frame;frame=[];frameBytes=0;
    // SSE fields allow both `data:` and the valueless `data` form.
    // Multiple data fields form one payload with a literal LF between values.
    const dataFields=lines.filter(x=>x==='data'||x.startsWith('data:'));
    // An empty data frame is still an SSE event, including after [DONE].
    // Ignore comment-only frames; never let a terminal data frame bypass the fence.
    if(!dataFields.length)return;
    if(seenDone)throw fail('B4_POST_DONE_EVENT');
    const payload=dataFields.map(x=>x==='data'?'':x.slice(5).replace(/^ /,'')).join('\n');
    if(!payload)return;
    if(browser){
      // B3 R56 browser bridge emits meta/token/done/error, not OpenAI choices.
      // Time from the consumer's monotonic clock; never trust embedded timing,
      // or equate browser-visible pieces with model tokens.
      let e;
      try{e=JSON.parse(payload);}catch{throw fail('B4_MALFORMED_EVENT');}
      if(!e||typeof e!=='object'||Array.isArray(e))throw fail('B4_BROWSER_BAD_FRAME');
      if(e.type==='error')throw fail('B4_BROWSER_ERROR');
      if('dialog_id' in e&&e.dialog_id!==expectedDialogId)throw fail('B4_BROWSER_DIALOG_MISMATCH');
      if(e.type==='meta'){
        if(browserMeta||e.dialog_id!==expectedDialogId||e.answer_source!=='NATIVE_PENDING')
          throw fail('B4_BROWSER_BAD_META');
        browserMeta=true;return;
      }
      if(!browserMeta)throw fail('B4_BROWSER_META_REQUIRED');
      if(e.type==='token'){
        if(typeof e.t!=='string')throw fail('B4_BROWSER_BAD_TOKEN');
        appendVisible(e.t);return;
      }
      if(e.type==='done'){
        if(e.dialog_id!==expectedDialogId||e.status!=='done'||e.saved!==true||
           e.history_persisted!==true||e.answer_source!=='LIVE_NOX'||
           typeof e.exchange_id!=='string'||e.exchange_id.length<6||e.exchange_id.length>160||
           typeof e.s03_integrated!=='boolean'||ttft===null)
          throw fail('B4_BROWSER_BAD_DONE');
        browserExchangeId=e.exchange_id;seenStop=true;seenDone=true;sseDone=nowMs();return;
      }
      throw fail('B4_BROWSER_BAD_FRAME');
    }
    if(payload==='[DONE]'){
      if(!seenStop)throw fail('B4_DONE_WITHOUT_STOP');
      seenDone=true;sseDone=nowMs();return;
    }
    let parsed;
    try{parsed=JSON.parse(payload);}catch{throw fail('B4_MALFORMED_EVENT');}
    if(!parsed||!Array.isArray(parsed.choices)||parsed.choices.length!==1)
      throw fail('B4_BAD_CHOICES');
    const choice=parsed.choices[0];
    // A malformed choice is not a heartbeat or an empty valid delta.
    if(!choice||typeof choice!=='object'||Array.isArray(choice))
      throw fail('B4_BAD_CHOICES');
    const delta=choice.delta;
    // Null/missing delta is valid for legacy text and terminal choices.
    // A present non-null delta must be an object, not a scalar or array.
    if(delta!==null&&delta!==undefined&&(typeof delta!=='object'||Array.isArray(delta)))
      throw fail('B4_BAD_DELTA');
    const text=delta?.content??choice.text??'';
    if(typeof text!=='string')throw fail('B4_BAD_TEXT');
    if(seenStop&&text.length)throw fail('B4_TEXT_AFTER_STOP');
    appendVisible(text);
    const reason=choice?.finish_reason;
    if(reason!==null&&reason!==undefined){
      if(reason!=='stop'||seenStop)throw fail('B4_BAD_FINISH_REASON');
      seenStop=true;
    }
  }
  // CR, LF and CRLF are each a single SSE line terminator. The pending
  // CRLF suffix is tracked across UTF-8 decoder / HTTP transport chunks.
  let skipNextLF=false;
  function feedText(text){
    for(const c of text){
      if(skipNextLF){
        skipNextLF=false;
        if(c==='\n')continue;
      }
      if(c==='\r'||c==='\n'){
        const current=line,currentBytes=lineBytes;
        line='';lineBytes=0;
        if(current==='')acceptFrame();
        else {
          frame.push(current);
          // SSE multi-field payloads contribute one LF between field lines.
          frameBytes+=currentBytes+(frame.length>1?1:0);
        }
        if(c==='\r')skipNextLF=true;
      }else {
        line+=c;
        // Iteration is by Unicode code point, not by UTF-16 code unit.
        lineBytes+=Buffer.byteLength(c,'utf8');
      }
      if(lineBytes+frameBytes>maxEventBytes)
        throw fail('B4_EVENT_TOO_LARGE');
    }
  }
  let lastByteAt=null;
  async function boundedRead(){
    let timer;
    const readStartedAt=clock();
    const remaining=totalTimeoutMs-(readStartedAt-startedAt);
    if(remaining<=0)throw fail('B4_TOTAL_TIMEOUT');
    if(lastByteAt===null)lastByteAt=readStartedAt;
    const idleRemaining=idleTimeoutMs-(readStartedAt-lastByteAt);
    if(idleRemaining<=0)throw fail('B4_IDLE_TIMEOUT');
    const wait=Math.min(idleRemaining,remaining);
    try{
      const result=await Promise.race([
        reader.read(),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(fail(
          wait===remaining||clock()-startedAt>=totalTimeoutMs?'B4_TOTAL_TIMEOUT':'B4_IDLE_TIMEOUT'
        )),wait);})
      ]);
      // A fulfilled read may win the race against a delayed timer callback.
      // Both deadlines apply to EOF as well as data; total has precedence.
      const settledAt=clock();
      if(settledAt-startedAt>=totalTimeoutMs)throw fail('B4_TOTAL_TIMEOUT');
      if(settledAt-lastByteAt>=idleTimeoutMs)throw fail('B4_IDLE_TIMEOUT');
      // Only actual transport bytes renew the idle budget, never empty reads.
      if(!result.done&&result.value instanceof Uint8Array&&result.value.length>0)
        lastByteAt=settledAt;
      return result;
    }finally{clearTimeout(timer);}
  }
  try{
    for(;;){
      const {done,value}=await boundedRead();
      assertTotalDeadline();
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
    assertTotalDeadline();
    close=nowMs();
    if(line||frame.length)throw fail('B4_UNFRAMED_EOF');
    if(!seenStop||!seenDone||ttft===null)throw fail('B4_INCOMPLETE_SSE');
    if(close<sseDone||sseDone<ttft)throw fail('B4_TIME_ORDER_INVALID');
    // At actual EOF a lone high surrogate is a U+FFFD replacement, as with
    // one-shot crypto.update(fullVisibleText,'utf8'). Never digest before EOF.
    if(pendingHighSurrogate)visibleHash.update(pendingHighSurrogate);
    const result=Object.freeze({
      verified:true,first_byte_ms:firstByte,ttft_ms:ttft,
      sse_done_ms:sseDone,completion_ms:close,
      body_bytes:total,body_sha256:rawHash.digest('hex'),
      visible_text_sha256:visibleHash.digest(),
      // Never claim a local fetch is an authenticated model/browser/S03 proof.
      browser_authenticated:false,native_verified:false,canonical_s03_verified:false,
      model_tokens_per_second:null,
      ...(browser?{timing_scope:'browser-consumer',dialog_id:expectedDialogId,
        exchange_id:browserExchangeId}: {})
    });
    assertTotalDeadline();
    return result;
  }catch(e){
    // Stream cancellation is best-effort: a nonsettling cancel must not
    // override or delay the original timeout or malformed-stream failure.
    try{Promise.resolve(reader.cancel()).catch(()=>{});}catch{}
    throw e;
  }finally{
    // A raced read may still be pending. Release the lock even if cancel
    // never settles, without masking the original failure.
    try{reader.releaseLock();}catch{}
  }
}

// R30: both the HTTP preheader wait and SSE body share one absolute deadline.
// External abort races BOTH phases and quarantines late fetch/reader outcomes.
// Never retry or replay a POST; all cleanup is best-effort and nonblocking.
export async function measureSseFetch(url,init={},options={}){
  const {startedAt=performance.now(),clock=()=>performance.now(),
    totalTimeoutMs=60000,fetchImpl=globalThis.fetch}=options;
  if(!Number.isFinite(startedAt))throw fail('B4_INVALID_STARTED_AT');
  if(!Number.isInteger(totalTimeoutMs)||totalTimeoutMs<10||totalTimeoutMs>1800000)
    throw fail('B4_INVALID_totalTimeoutMs');
  if(typeof fetchImpl!=='function')throw fail('B4_INVALID_FETCH_IMPL');
  const externalSignal=init?.signal;
  if(externalSignal!=null&&!(externalSignal instanceof AbortSignal))
    throw fail('B4_INVALID_EXTERNAL_SIGNAL');
  if(externalSignal?.aborted)throw fail('B4_FETCH_ABORTED');
  const remaining=totalTimeoutMs-(clock()-startedAt);
  if(remaining<=0)throw fail('B4_TOTAL_TIMEOUT');
  const owner=new AbortController();
  const signal=externalSignal?AbortSignal.any([externalSignal,owner.signal]):owner.signal;
  let expired=false,headerTimer,response,rejectExternal;
  function disposeLate(bodyResponse){
    try{Promise.resolve(bodyResponse?.body?.cancel?.()).catch(()=>{});}catch{}
  }
  const externalAbort=new Promise((_,reject)=>{rejectExternal=reject;});
  const onExternalAbort=()=>{
    expired=true;
    try{owner.abort();}catch{}
    rejectExternal(fail('B4_FETCH_ABORTED'));
  };
  externalSignal?.addEventListener('abort',onExternalAbort,{once:true});
  // Late fetch settlement is observed even if the fetch implementation ignores
  // abort. Its body cannot be used as a successful verification after failure.
  const pending=Promise.resolve().then(()=>fetchImpl(url,{...init,signal}));
  pending.then(value=>{if(expired)disposeLate(value);},()=>{});
  try{
    response=await Promise.race([
      pending,externalAbort,
      new Promise((_,reject)=>{headerTimer=setTimeout(()=>reject(fail('B4_TOTAL_TIMEOUT')),remaining);})
    ]);
    clearTimeout(headerTimer);
    if(externalSignal?.aborted)throw fail('B4_FETCH_ABORTED');
    if(clock()-startedAt>=totalTimeoutMs)throw fail('B4_TOTAL_TIMEOUT');
    return await Promise.race([
      measureSseResponse(response,{...options,startedAt,clock,totalTimeoutMs}),
      externalAbort
    ]);
  }catch(error){
    expired=true;
    try{owner.abort();}catch{}
    if(response)disposeLate(response);
    if(['Z_BUF_ERROR','Z_DATA_ERROR','Z_STREAM_ERROR'].includes(error?.code))
      throw fail('B4_COMPRESSED_INTEGRITY_FAILED');
    if(error?.code)throw error;
    throw fail(externalSignal?.aborted?'B4_FETCH_ABORTED':'B4_FETCH_FAILED');
  }finally{
    clearTimeout(headerTimer);
    externalSignal?.removeEventListener('abort',onExternalAbort);
  }
}


// R34: trustworthy compressed SSE requires transport-level integrity, not a
// fetch() body already transparently decoded by undici. Node's gzip transform
// verifies the gzip CRC32/ISIZE trailer before its readable EOF is released.
// This is opt-in; the established fetch route and model are untouched.
export async function measureSseRawHttp(url,init={},options={}){
  const fetchRaw=(target,requestInit)=>new Promise((resolve,reject)=>{
    let address;
    try{address=new URL(target);}catch{return reject(fail('B4_INVALID_URL'));}
    if(!['http:','https:'].includes(address.protocol))
      return reject(fail('B4_INVALID_PROTOCOL'));
    const transport=address.protocol==='https:'?httpsRequest:httpRequest;
    const req=transport(address,{
      method:requestInit.method||'GET',headers:requestInit.headers,
      signal:requestInit.signal
    },res=>{
      const coding=String(res.headers['content-encoding']||'identity').trim().toLowerCase();
      if(coding!=='identity'&&coding!=='gzip'){
        res.destroy();reject(fail('B4_UNSUPPORTED_COMPRESSION'));return;
      }
      let source=res;
      if(coding==='gzip'){
        const decoded=createGunzip();
        res.on('aborted',()=>decoded.destroy(new Error('B4_COMPRESSED_TRUNCATED')));
        res.on('error',e=>decoded.destroy(e));
        decoded.once('close',()=>{if(!res.complete&&!res.destroyed)res.destroy();});
        res.pipe(decoded);
        source=decoded;
      }
      // Advertise identity only after the raw gzip decoder owns the stream.
      // A Readable.toWeb read() may finish only when zlib has seen a valid EOF.
      const headers=new Headers(res.headers);
      headers.set('content-encoding','identity');
      headers.delete('content-length');
      resolve({status:res.statusCode,headers,body:Readable.toWeb(source)});
    });
    req.once('error',reject);
    try{req.end(requestInit.body);}catch(e){req.destroy();reject(e);}
  });
  return measureSseFetch(url,init,{...options,fetchImpl:fetchRaw});
}
