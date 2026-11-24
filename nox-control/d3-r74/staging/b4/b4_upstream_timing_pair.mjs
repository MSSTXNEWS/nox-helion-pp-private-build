// R55: bind two already measured upstream records to the existing browser pair.
// No network, model POST, clock conversion, authentication or native acceptance.
// Expected pins MUST be obtained independently from the owner verifier.
import {createHash} from 'node:crypto';
import {bindExistingTurnPair} from './b4_existing_turn_pair.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const hex=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const id=x=>typeof x==='string'&&/^[A-Za-z0-9._:-]{6,160}$/.test(x);
const hold=code=>{throw Object.assign(new Error(code),{code});};
export function bindUpstreamTimingPair(expected,observed,upstreamPins,records){
  const browser=bindExistingTurnPair(expected,observed);
  if(!upstreamPins||!id(upstreamPins.model)||!id(upstreamPins.route_id)||
    !hex(upstreamPins.weights_sha256)||!hex(upstreamPins.tokenizer_sha256)||
    !Number.isSafeInteger(upstreamPins.baseline_posts)||upstreamPins.baseline_posts<0||
    upstreamPins.baseline_posts>Number.MAX_SAFE_INTEGER-2||
    !Array.isArray(upstreamPins.turns)||upstreamPins.turns.length!==2||
    !Array.isArray(records)||records.length!==2)hold('B4_UPSTREAM_SCOPE');
  const seen=new Set(),digests=new Set(),turns=[];
  for(let i=0;i<2;i++){
    const b=browser.turns[i],pin=upstreamPins.turns[i],bytes=records[i];
    if(!pin||pin.turn!==b.turn||pin.exchange_id!==b.exchange_id||
      !id(pin.request_id)||seen.has(pin.request_id)||!hex(pin.record_sha256)||
      !hex(pin.body_sha256)||digests.has(pin.body_sha256)||
      !(bytes instanceof Uint8Array)||bytes.byteLength<2||bytes.byteLength>16384)
      hold('B4_UPSTREAM_PIN');
    // Hash and parse the same immutable private snapshot, not a caller's object.
    const copy=Buffer.from(bytes);
    if(sha(copy)!==pin.record_sha256)hold('B4_UPSTREAM_DIGEST');
    let r;try{r=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(copy));}
    catch{hold('B4_UPSTREAM_JSON');}
    if(!r||typeof r!=='object'||Array.isArray(r)||
      r.turn!==b.turn||r.dialog_id!==browser.dialog_id||
      r.exchange_id!==b.exchange_id||r.request_id!==pin.request_id||
      r.model!==upstreamPins.model||r.route_id!==upstreamPins.route_id||
      r.weights_sha256!==upstreamPins.weights_sha256||
      r.tokenizer_sha256!==upstreamPins.tokenizer_sha256||
      r.upstream_posts!==upstreamPins.baseline_posts+i+1||
      r.timing_scope!=='upstream-response-consumer'||r.verified!==true||
      r.native_verified!==false||r.browser_authenticated!==false||
      r.canonical_s03_verified!==false||r.model_tokens_per_second!==null||
      r.body_sha256!==pin.body_sha256||
      r.visible_text_sha256!==b.visible_text_sha256)
      hold('B4_UPSTREAM_BINDING');
    const t=[r.first_byte_ms,r.ttft_ms,r.sse_done_ms,r.completion_ms];
    if(!t.every((v,j)=>Number.isFinite(v)&&v>=0&&(!j||v>=t[j-1]))||
      !Number.isSafeInteger(r.body_bytes)||r.body_bytes<=0)
      hold('B4_UPSTREAM_TIMING');
    seen.add(pin.request_id);digests.add(pin.body_sha256);
    // Independent monotonic durations only. No subtraction across clocks,
    // no conversion of browser chunks to model tokens.
    turns.push(Object.freeze({turn:b.turn,exchange_id:b.exchange_id,
      upstream_request_id:pin.request_id,upstream_record_sha256:pin.record_sha256,
      upstream_body_sha256:pin.body_sha256,browser_ttft_ms:b.ttft_ms,
      browser_completion_ms:b.completion_ms,upstream_ttft_ms:t[1],
      upstream_completion_ms:t[3]}));
  }
  return Object.freeze({status:'B4_TIMING_INPUTS_MATCHED',dialog_id:browser.dialog_id,
    turns:Object.freeze(turns),native_verified:false,browser_authenticated:false,
    canonical_s03_verified:false,model_tokens_per_second:null});
}
