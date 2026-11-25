'use strict';
// Opt-in B4 hard admission deadline: only pre-POST, never a generation timeout.
// All authority and idempotency checks remain in R66/R64/R63 and the host.
const {createScopedAdmission}=require('./b4_r66_scoped_admission.cjs');
function createHardAdmissionDeadline(opts={}){
 const {transport,limitMs,now=()=>performance.now(),maxRecords=4096}=opts;
 const fail=code=>{throw Object.assign(new Error(code),{code});};
 if(!transport||typeof transport.post!=='function'||typeof transport.readback!=='function'||typeof transport.ack!=='function'||typeof now!=='function'||!Number.isSafeInteger(limitMs)||limitMs<1||limitMs>600000||!Number.isSafeInteger(maxRecords)||maxRecords<1)fail('HOLD_B4_R68_CONFIG');
 const records=new Map(),id=/^[A-Za-z0-9._:-]{1,128}$/,send=transport.post.bind(transport);
 function scope(raw){
  const s=Object.freeze({conversation_id:raw?.conversation_id,exchange_id:raw?.exchange_id});
  if(typeof s.conversation_id!=='string'||!id.test(s.conversation_id)||typeof s.exchange_id!=='string'||!id.test(s.exchange_id))fail('HOLD_B4_R68_SCOPE');
  return [s,s.conversation_id+'\0'+s.exchange_id];
 }
 const clear=r=>{if(r.timer!==null){clearTimeout(r.timer);r.timer=null;}};
 const wrapped={
  post(raw,signal){
   const [s,k]=scope(raw),r=records.get(k);
   if(!r||r.closed||r.invoked||r.reason||signal?.aborted!==false)fail('HOLD_B4_R68_NO_ADMISSION');
   const t=now();
   if(!Number.isFinite(t)||t<r.start){r.reason='HOLD_B4_R68_CLOCK';fail(r.reason);}
   if(t-r.start>=limitMs){r.reason='HOLD_B4_R68_ADMISSION_TIMEOUT';fail(r.reason);}
   if(signal.aborted!==false)fail('HOLD_B4_R68_NO_ADMISSION');
   // Disarm before calling the actual transport, even if it throws or hangs.
   // A possibly committed POST must not be cancelled by the admission timer.
   r.invoked=true;r.admission_elapsed_ms=t-r.start;clear(r);
   return send(s,signal);
  },readback:transport.readback.bind(transport),ack:transport.ack.bind(transport)
 };
 if(typeof transport.readCanonicalAck==='function')wrapped.readCanonicalAck=transport.readCanonicalAck.bind(transport);
 const inner=createScopedAdmission({...opts,now,maxRecords,transport:wrapped});
 async function begin(raw){
  const [s,k]=scope(raw);
  if(records.has(k))fail('HOLD_B4_R68_NO_REPOST');
  if(records.size>=maxRecords)fail('HOLD_B4_R68_CAPACITY');
  const start=now();if(!Number.isFinite(start))fail('HOLD_B4_R68_CLOCK');
  const r={start,timer:null,closed:false,invoked:false,reason:null,admission_elapsed_ms:null};records.set(k,r);
  r.timer=setTimeout(()=>{
   r.timer=null;
   if(r.closed||r.invoked||r.reason)return;
   r.reason='HOLD_B4_R68_ADMISSION_TIMEOUT';
   // R77 stop() aborts local read-only preflight/verifier waits, not a remote STOP.
   inner.stop(s);
  },limitMs);
  try{
   const value=await inner.begin(s);
   if(r.reason)fail(r.reason);
   return value;
  }catch(err){if(r.reason)fail(r.reason);throw err;}
  finally{r.closed=true;clear(r);}
 }
 function report(raw){
  const [s,k]=scope(raw),r=records.get(k);if(!r)fail('HOLD_B4_R68_SCOPE');
  return Object.freeze({...inner.report(s),reason:r.reason||inner.report(s).reason,transport_invoked:r.invoked,hard_admission_elapsed_ms:r.admission_elapsed_ms,physical_glm_measured:false,native_accepted:false});
 }
 return Object.freeze({begin,report,stop:raw=>inner.stop(scope(raw)[0]),reconnect:raw=>inner.reconnect(scope(raw)[0])});
}
module.exports={createHardAdmissionDeadline};
