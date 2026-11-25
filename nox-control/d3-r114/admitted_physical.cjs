'use strict';
// B3 R83: offline consistency only. Owner must independently authenticate the
// admission/readback envelope and its digest, separately from frozen producer.
// Never construct this envelope from the candidate or use it as native authority.
const {createHash}=require('node:crypto');
const {TextDecoder}=require('node:util');
const sha=b=>createHash('sha256').update(b).digest('hex');
const hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v)&&!/^(.)\1+$/.test(v);
const id=v=>typeof v==='string'&&v.length>0&&v.length<=160&&v.trim()===v&&!/[\x00-\x1f\x7f]/.test(v);
const pos=v=>Number.isSafeInteger(v)&&v>0;
const obj=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const keys=(o,ks)=>obj(o)&&Object.keys(o).length===ks.length&&ks.every(k=>Object.hasOwn(o,k));
const fields=['model_id','route','dialog_id','weights_manifest_sha256','tokenizer_manifest_sha256','bridge_sha256','original_checkpoint_sha256','owner_admission_receipt_sha256','window_start_ms','window_end_ms'];
const flags={native_accepted:false,authentication_verified:false,host_provider_bound:false,ack_allowed:false,next_post_allowed:false,training_admitted:false,production_ready:false};
const hold=status=>({status,consistent:false,...flags});
const schema='NOX_B3_R83_INDEPENDENT_PHYSICAL_ENVELOPE_V1';
const bridge='c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7';
const parse=b=>JSON.parse(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(b));
function checkAdmittedPhysical(payload,payloadPin,admitted,admittedPin){
 try{
  if(!Buffer.isBuffer(payload)||!payload.length||payload.length>8*1024*1024||
     !hex(payloadPin)||!Buffer.isBuffer(admitted)||!admitted.length||admitted.length>65536||!hex(admittedPin))return hold('HOLD_R83_INPUT');
  const raw=Buffer.from(payload),proof=Buffer.from(admitted);
  if(sha(raw)!==payloadPin||sha(proof)!==admittedPin)return hold('HOLD_R83_DETACHED_DIGEST');
  const a=parse(proof);
  if(!keys(a,['schema','expected','receipt_index'])||a.schema!==schema||
     !Buffer.from(JSON.stringify(a),'utf8').equals(proof))return hold('HOLD_R83_ENVELOPE');
  const e=a.expected;
  if(!keys(e,[...fields,'process','turn_request_ids'])||
     !['model_id','route','dialog_id'].every(k=>id(e[k]))||
     !fields.filter(k=>k.endsWith('_sha256')).every(k=>hex(e[k]))||e.bridge_sha256!==bridge||
     !pos(e.window_start_ms)||!pos(e.window_end_ms)||e.window_start_ms>=e.window_end_ms||
     !keys(e.process,['boot_id','pid','start_ticks'])||!id(e.process.boot_id)||!pos(e.process.pid)||!pos(e.process.start_ticks)||
     !Array.isArray(e.turn_request_ids)||e.turn_request_ids.length!==2||!e.turn_request_ids.every(id)||
     e.turn_request_ids[0]===e.turn_request_ids[1])return hold('HOLD_R83_ADMISSION_SCOPE');
  const index=a.receipt_index;
  if(!Array.isArray(index)||index.length!==4||
     !index.every(x=>keys(x,['readback_id','sha256'])&&id(x.readback_id)&&hex(x.sha256))||
     new Set(index.map(x=>x.readback_id)).size!==4||new Set(index.map(x=>x.sha256)).size!==4)return hold('HOLD_R83_ADMITTED_INDEX');
  const doc=parse(raw);
  const r=Array.isArray(doc)&&doc.length===3?doc[0]?.receipts:null;
  const c=r?.expected;
  if(r?.schema!=='NOX_B3_R66_READBACK_BYTES_V1'||!obj(c)||
     fields.some(k=>c[k]!==e[k])||!obj(c.process)||
     ['boot_id','pid','start_ticks'].some(k=>c.process[k]!==e.process[k])||
     !Array.isArray(c.turn_request_ids)||c.turn_request_ids.length!==2||
     c.turn_request_ids.some((x,i)=>x!==e.turn_request_ids[i]))return hold('HOLD_R83_PHYSICAL_DRIFT');
  if(!Array.isArray(r.receipt_index)||r.receipt_index.length!==4||
     !Array.isArray(r.receipt_payloads)||r.receipt_payloads.length!==4||
     index.some((x,i)=>r.receipt_index[i]?.readback_id!==x.readback_id||
       r.receipt_index[i]?.sha256!==x.sha256||
       typeof r.receipt_payloads[i]!=='string'||Buffer.byteLength(r.receipt_payloads[i],'utf8')>65536||
       sha(Buffer.from(r.receipt_payloads[i],'utf8'))!==x.sha256))return hold('HOLD_R83_RECEIPT_DRIFT');
  return {status:'MATCHED_R83_ADMISSION_OFFLINE',consistent:true,payload_sha256:payloadPin,
    admitted_envelope_sha256:admittedPin,...flags};
 }catch{return hold('HOLD_R83_INVALID');}
}
module.exports={checkAdmittedPhysical,schema};
