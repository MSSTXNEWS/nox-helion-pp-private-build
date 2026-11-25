/** Pair binding for ALREADY observed existing-dialog turns 2/3.
 * No network or POST. Expected values must come from independently pinned
 * capture/owner/S03 artifacts; this module does not authenticate those inputs.
 */
const hex64=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const id=x=>typeof x==='string'&&x.length>=6&&x.length<=160;
const count=x=>Number.isSafeInteger(x)&&x>=0&&x<=Number.MAX_SAFE_INTEGER-2;
const hold=code=>{throw Object.assign(new Error(code),{code});};
export function bindExistingTurnPair(expected,observed){
  if(!expected||! /^[a-f0-9]{32}$/.test(expected.dialog_id??'')||
     !id(expected.prior_exchange_id)||!count(expected.baseline_browser_posts)||
     !count(expected.baseline_admitted_posts)||!Array.isArray(expected.turns)||
     expected.turns.length!==2||!Array.isArray(observed)||observed.length!==2)
    hold('B4_PAIR_SCOPE');
  const exchanges=new Set([expected.prior_exchange_id]),bodies=new Set(),turns=[];
  for(let i=0;i<2;i++){
    const turn=i+2,e=expected.turns[i],o=observed[i],p=o?.proof;
    if(e?.turn!==turn||o?.turn!==turn||!id(e.exchange_id)||
       exchanges.has(e.exchange_id)||!hex64(e.body_sha256)||
       !hex64(e.visible_text_sha256)||bodies.has(e.body_sha256))
      hold('B4_PAIR_SEQUENCE');
    exchanges.add(e.exchange_id);bodies.add(e.body_sha256);
    if(o.browser_posts!==expected.baseline_browser_posts+i+1||
       o.admitted_posts!==expected.baseline_admitted_posts+i+1)
      hold('B4_PAIR_POST_COUNT');
    if(!p||p.verified!==true||p.timing_scope!=='browser-consumer'||
       p.dialog_id!==expected.dialog_id||p.exchange_id!==e.exchange_id||
       p.body_sha256!==e.body_sha256||p.visible_text_sha256!==e.visible_text_sha256||
       p.browser_authenticated!==false||p.native_verified!==false||
       p.canonical_s03_verified!==false||p.model_tokens_per_second!==null)
      hold('B4_PAIR_PROOF');
    const times=[p.first_byte_ms,p.ttft_ms,p.sse_done_ms,p.completion_ms];
    if(!times.every((v,j)=>Number.isFinite(v)&&v>=0&&(!j||v>=times[j-1]))||
       !Number.isSafeInteger(p.body_bytes)||p.body_bytes<=0)
      hold('B4_PAIR_TIMING');
    turns.push(Object.freeze({turn,exchange_id:e.exchange_id,
      first_byte_ms:times[0],ttft_ms:times[1],sse_done_ms:times[2],completion_ms:times[3],
      body_sha256:e.body_sha256,visible_text_sha256:e.visible_text_sha256}));
  }
  return Object.freeze({status:'B4_PAIR_INPUTS_MATCHED',dialog_id:expected.dialog_id,
    turns:Object.freeze(turns),browser_authenticated:false,native_verified:false,
    canonical_s03_verified:false,model_tokens_per_second:null});
}
