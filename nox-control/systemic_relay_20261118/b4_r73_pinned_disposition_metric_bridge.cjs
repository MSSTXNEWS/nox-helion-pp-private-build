'use strict';
const {createHash}=require('node:crypto');
const {TextDecoder}=require('node:util');
const {classifyFinalizedCompletion}=require('./b4_r72_final_disposition_metric_fence.cjs');
// Only an independently authenticated host supplies trusted. Never deserialize it
// from the browser, candidate receipts, or R101's MATCHED_OFFLINE review.
const SCOPE=['conversation_id','physical_dialog_id','s03_dialog_id','session_id','served_sha256','server_sha256','owner_admission_receipt_sha256'];
const BIND=['turn','exchange_id','request_id','attempt_id','event_id','turn_id','user_message_id','assistant_message_id'];
const COMMON=[...SCOPE,...BIND,'observation_id','browser_sha256','terminal_receipt_sha256'];
const DIGESTS=['observation_sha256','reservation_sha256','disposition_sha256'];
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=v=>typeof v==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(v);
const need=(ok)=>{if(!ok)throw Error('HOLD_PINNED_DISPOSITION');};
const exact=(o,keys)=>o&&Object.getPrototypeOf(o)===Object.prototype&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
function read(bytes,pin,keys){
 need(Buffer.isBuffer(bytes)&&bytes.length>0&&bytes.length<=65536&&sha(pin));
 need(createHash('sha256').update(bytes).digest('hex')===pin);
 const raw=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
 const obj=JSON.parse(raw);
 need(exact(obj,keys));
 // All receipt fields are flat scalars; reject duplicate JSON keys before use.
 need((raw.match(/"(?:\\.|[^"\\])*"\s*:/g)||[]).length===keys.length);
 need(Object.values(obj).every(v=>typeof v==='string'||typeof v==='number'));
 return obj;
}
function classifyPinnedCompletion(receipts,quality, trusted){
 const hold=()=>Object.freeze({status:'HOLD_PINNED_DISPOSITION',ttft_ms:null,completion_ms:null,stream_eof_ms:null,recovery_ms:null,native_accepted:false});
 try{
  // The host must independently authenticate timing, DOM/S03 proof and all three
  // detached pins. No authentication is performed or inferred by this classifier.
  need(trusted&&trusted.authentication_verified===true&&trusted.proof?.verified===true);
  const {sample,proof,pins}=trusted;
  need(sample?.outcome==='STREAM_ENDED_READBACK_REQUIRED'&&[2,3].includes(proof.turn));
  need(exact(pins,DIGESTS)&&DIGESTS.every(k=>sha(pins[k])));
  need(new Set(DIGESTS.map(k=>pins[k])).size===3);
  const o=read(receipts.observation,pins.observation_sha256,[...COMMON,'schema','visible_text_sha256','visible_row_count','state','ack_state']);
  const r=read(receipts.reservation,pins.reservation_sha256,[...COMMON,'observation_sha256','schema','reservation_id','state']);
  const f=read(receipts.disposition,pins.disposition_sha256,[...COMMON,'observation_sha256','schema','disposition_id','reservation_id','reservation_sha256','state','dom_recheck','stop_recheck']);
  need(o.schema==='nox.browser.projection-readback.v1'&&o.state==='TERMINAL_VISIBLE'&&o.ack_state==='NOT_SENT'&&o.visible_row_count===1);
  need(r.schema==='nox.browser.ack-reservation-readback.v1'&&r.state==='RESERVED_NOT_SENT');
  need(f.schema==='nox.browser.projection-disposition.v1'&&f.state==='FINALIZED'&&f.dom_recheck==='MATCHED'&&f.stop_recheck==='CLEAR');
  for(const k of COMMON){
   need(k==='turn'?[2,3].includes(o[k]):k.endsWith('sha256')?sha(o[k]):id(o[k]));
   need(o[k]===r[k]&&o[k]===f[k]&&o[k]===proof[k]);
  }
  need(sha(o.visible_text_sha256)&&o.visible_text_sha256===proof.dom_sha256&&o.visible_text_sha256===proof.answer_sha256);
  need(r.observation_sha256===pins.observation_sha256&&f.observation_sha256===pins.observation_sha256&&proof.observation_sha256===pins.observation_sha256);
  need(f.reservation_sha256===pins.reservation_sha256&&id(r.reservation_id)&&r.reservation_id===f.reservation_id&&r.reservation_id===proof.reservation_receipt_id);
  need(id(f.disposition_id)&&new Set([f.disposition_id,r.reservation_id,o.observation_id,proof.dom_receipt_id,proof.canonical_receipt_id]).size===5);
  // R101 offline output only identifies which exact bytes its quality review used.
  const q=quality?.dialog_provenance;
  need(quality?.route==='REVIEW_DATA_ONLY'&&q?.disposition_status==='MATCHED_OFFLINE'&&q.authentication_verified===false);
  need(['native_accepted','training_admitted','next_post_allowed','retry_allowed','ack_allowed'].every(k=>quality[k]===false));
  const pair=q.finalized_observation_pairs;
  need(Array.isArray(pair)&&pair.length===2&&pair.every(x=>exact(x,DIGESTS)&&DIGESTS.every(k=>sha(x[k]))));
  need(new Set(pair.flatMap(x=>DIGESTS.map(k=>x[k]))).size===6);
  need(DIGESTS.every(k=>pair[proof.turn-2][k]===pins[k]));
  const result=classifyFinalizedCompletion(sample,proof,{...proof,state:'ACK_RESERVED_AFTER_DOM_RECHECK',receipt_id:f.disposition_id});
  need(result.status==='VERIFIED_COMPLETION_SAMPLE');
  return Object.freeze({...result,...pins,turn:proof.turn});
 }catch{return hold();}
}
module.exports={classifyPinnedCompletion};
