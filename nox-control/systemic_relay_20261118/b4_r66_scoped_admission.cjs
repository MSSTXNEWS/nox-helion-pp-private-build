'use strict';
// B4 R66: actual R76 + R64/R63 opt-in composition. No owner authority.
// One start before host preflight; expensive authenticated binding is fenced too.
function createScopedAdmission({createClient,createScopedTransport,createWireGuard,createPreverifierFence,createAdmissionBudget,checkScope,readBinding,authenticateBinding,transport,contract,clientOptions,limitMs,deadlineMs,now=()=>globalThis.performance.now(),maxRecords=4096}={}){
 const fail=code=>{throw Object.assign(new Error(code),{code});};
 if([createClient,createScopedTransport,createWireGuard,createPreverifierFence,createAdmissionBudget,checkScope,readBinding,authenticateBinding,now].some(f=>typeof f!=='function')||!Number.isSafeInteger(limitMs)||limitMs<1||limitMs>600000||!Number.isSafeInteger(maxRecords)||maxRecords<1)fail('HOLD_B4_R66_CONFIG');
 const id=/^[A-Za-z0-9._:-]{1,128}$/,records=new Map();
 function scope(raw){
  const s=Object.freeze({conversation_id:raw?.conversation_id,exchange_id:raw?.exchange_id});
  if(typeof s.conversation_id!=='string'||!id.test(s.conversation_id)||typeof s.exchange_id!=='string'||!id.test(s.exchange_id))fail('HOLD_B4_R66_SCOPE');
  return [s,s.conversation_id+'\0'+s.exchange_id];
 }
 function within(raw,signal,stage){
  const [,k]=scope(raw),r=records.get(k);
  if(!r||r.closed||signal?.aborted!==false)return false;
  const t=now();
  if(!Number.isFinite(t)||t<r.last){r.reason='HOLD_B4_R66_CLOCK';return false;}
  r.last=t;
  if(t-r.start>=limitMs){r.reason='HOLD_B4_R66_EXPIRED_'+stage;return false;}
  return signal.aborted===false;
 }
 let fence;
 const guarded=createScopedTransport({checkScope,contract,deadlineMs,transport,
  readBinding:(pin,s,signal)=>within(s,signal,'BINDING')?readBinding(pin,s,signal):null,
  authenticateBinding:(binding,pin,s,signal)=>within(s,signal,'AUTH')?authenticateBinding(binding,pin,s,signal):false,
  createWireGuard:opts=>{
   if(fence)fail('HOLD_B4_R66_CONFIG');
   fence=createPreverifierFence({createAdmissionBudget,transport:opts.transport,verifyWire:opts.verifyWire,limitMs,now,maxRecords});
   return createWireGuard({...opts,transport:fence.transport,verifyWire:fence.verifyWire});
  }
 });
 if(!fence)fail('HOLD_B4_R66_CONFIG');
 const client=createClient({...clientOptions,transport:guarded});
 async function begin(raw){
  const [s,k]=scope(raw);
  if(records.has(k))fail('HOLD_B4_R66_NO_REPOST');
  if(records.size>=maxRecords)fail('HOLD_B4_R66_CAPACITY');
  const start=now();if(!Number.isFinite(start))fail('HOLD_B4_R66_CLOCK');
  const r={start,last:start,closed:false,reason:null};records.set(k,r);
  try{return await fence.begin(client,s);}finally{r.closed=true;}
 }
 function report(raw){
  const [s,k]=scope(raw),r=records.get(k);if(!r)fail('HOLD_B4_R66_SCOPE');
  const b=fence.report(s);
  return Object.freeze({...b,reason:r.reason||b.reason,physical_glm_measured:false,native_accepted:false});
 }
 return Object.freeze({begin,report,stop:raw=>client.stop(scope(raw)[0]),reconnect:raw=>client.reconnect(scope(raw)[0])});
}
module.exports={createScopedAdmission};
