'use strict';
// Offline integration only. An independently authorized provider is still absent.
// Never construct trusted host evidence from the candidate packet.
const {createHash}=require('node:crypto');
const {isDeepStrictEqual}=require('node:util');
const {classifyOrderedCompletionPair}=require('./b4_r75_ordered_completion_pair.cjs');
const hash=b=>createHash('sha256').update(b).digest('hex');
const hold=status=>({status,quality_sample:null,metrics:null,native_accepted:false,training_admitted:false,ack_allowed:false,next_post_allowed:false});
const kinds=['observation','reservation','disposition'];
function makeOfflinePairReview(readHostEvidence){
 return function(raw){
  try{
   if(typeof raw!=='string'||Buffer.byteLength(raw)>4194304)return hold('HOLD_PAIR_INPUT');
   if(typeof readHostEvidence!=='function')return hold('HOLD_HOST_PROVIDER');
   const pin=hash(Buffer.from(raw,'utf8')), candidate=JSON.parse(raw);
   const host=readHostEvidence(pin);
   if(!host||host.packet_sha256!==pin||!isDeepStrictEqual(host.quality,candidate.review)||!Array.isArray(host.turns)||host.turns.length!==2)return hold('HOLD_HOST_BINDING');
   if(!Array.isArray(candidate.turns)||candidate.turns.length!==2)return hold('HOLD_PAIR_INPUT');
   for(let i=0;i<2;i++){
    const t=candidate.turns[i], h=host.turns[i];
    if(!h||h.trusted?.authentication_verified!==true||h.trusted?.proof?.verified!==true)return hold('HOLD_HOST_AUTHENTICATION');
    const {verified,...hostProof}=h.trusted.proof;
    if(!isDeepStrictEqual(t.sample,h.trusted.sample)||!isDeepStrictEqual(t.proof,hostProof))return hold('HOLD_HOST_TIMING_BINDING');
    for(const k of kinds){
     const p=t[k], bytes=h.receipts?.[k], hp=h.trusted.pins?.[k+'_sha256'];
     if(!Array.isArray(p)||p.length!==2||typeof p[0]!=='string'||!Buffer.isBuffer(bytes)||!bytes.equals(Buffer.from(p[0],'utf8'))||p[1]!==hp||hash(bytes)!==hp)return hold('HOLD_HOST_BYTES');
    }
   }
   const pair=classifyOrderedCompletionPair(host.turns,host.quality);
   if(pair.status!=='VERIFIED_COMPLETION_PAIR'||pair.samples.length!==2||pair.native_accepted!==false)return hold('HOLD_ATOMIC_PAIR');
   return {...hold('MATCHED_PAIR_OFFLINE'),offline_metrics:pair.samples,host_provider_required:true};
  }catch{return hold('HOLD_PAIR_BINDING');}
 };
}
module.exports={makeOfflinePairReview};
