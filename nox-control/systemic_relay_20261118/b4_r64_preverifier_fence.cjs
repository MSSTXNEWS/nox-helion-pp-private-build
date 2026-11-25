'use strict';
// B4 R64: optional R63 + R74 composition, one absolute clock before preflight.
// No authority grant, no transport retry, no production wiring.
function createPreverifierFence({createAdmissionBudget,transport,verifyWire,limitMs,now=()=>globalThis.performance.now(),maxRecords=4096}={}){
  const fail=code=>{throw Object.assign(new Error(code),{code});};
  if(typeof createAdmissionBudget!=='function'||typeof verifyWire!=='function'||typeof now!=='function'||!Number.isSafeInteger(limitMs)||limitMs<1||limitMs>600000||!Number.isSafeInteger(maxRecords)||maxRecords<1||!transport||typeof transport.post!=='function'||typeof transport.readback!=='function'||typeof transport.ack!=='function')fail('HOLD_B4_R64_CONFIG');
  const records=new Map(),id=/^[A-Za-z0-9._:-]{1,128}$/,send=transport.post.bind(transport);
  function scope(raw){
    const s=Object.freeze({conversation_id:raw?.conversation_id,exchange_id:raw?.exchange_id});
    if(typeof s.conversation_id!=='string'||!id.test(s.conversation_id)||typeof s.exchange_id!=='string'||!id.test(s.exchange_id))fail('HOLD_B4_R64_SCOPE');
    return [s,s.conversation_id+'\0'+s.exchange_id];
  }
  function check(r,stage){
    const t=now();
    if(!Number.isFinite(t)||t<r.last){r.reason='HOLD_B4_R64_CLOCK';return false;}
    r.last=t;r[stage+'_elapsed_ms']=t-r.start;
    if(t-r.start>=limitMs){r.reason='HOLD_B4_R64_EXPIRED_'+stage.toUpperCase();return false;}
    return true;
  }
  const finalTransport={post(raw,signal){
    const [s,k]=scope(raw),r=records.get(k);
    if(!r||r.closed||!r.verifier_invoked||r.transport_invoked||signal?.aborted!==false)fail('HOLD_B4_R64_NO_ADMISSION');
    if(!check(r,'transport'))fail(r.reason);
    if(signal.aborted!==false)fail('HOLD_B4_R64_STOPPED');
    r.transport_invoked=true;return send(s,signal);
  },readback:transport.readback.bind(transport),ack:transport.ack.bind(transport)};
  if(typeof transport.readCanonicalAck==='function')finalTransport.readCanonicalAck=transport.readCanonicalAck.bind(transport);
  const budget=createAdmissionBudget({transport:finalTransport,limitMs,now,maxRecords});
  async function begin(client,raw){
    const [s,k]=scope(raw);
    if(records.has(k))fail('HOLD_B4_R64_NO_REPOST');
    if(records.size>=maxRecords)fail('HOLD_B4_R64_CAPACITY');
    const start=now();if(!Number.isFinite(start))fail('HOLD_B4_R64_CLOCK');
    const r={start,last:start,closed:false,verifier_invoked:false,transport_invoked:false,verifier_elapsed_ms:null,transport_elapsed_ms:null,reason:null};
    records.set(k,r);
    try{return await budget.begin(client,s);}finally{r.closed=true;}
  }
  async function guardedVerifier(pin,raw,signal){
    const [s,k]=scope(raw),r=records.get(k);
    if(!r||r.closed||r.verifier_invoked||signal?.aborted!==false)return false;
    if(!check(r,'verifier'))return false;
    if(signal.aborted!==false)return false;
    r.verifier_invoked=true;return verifyWire(pin,s,signal);
  }
  function report(raw){
    const [,k]=scope(raw),r=records.get(k);
    if(!r)fail('HOLD_B4_R64_SCOPE');
    const b=budget.report(raw);
    return Object.freeze({verifier_elapsed_ms:r.verifier_elapsed_ms,verifier_invoked:r.verifier_invoked,transport_elapsed_ms:r.transport_elapsed_ms,transport_invoked:r.transport_invoked,reason:r.reason||b.reason,closed:r.closed,physical_glm_measured:false,native_accepted:false});
  }
  return Object.freeze({begin,verifyWire:guardedVerifier,transport:budget.transport,report});
}
module.exports={createPreverifierFence};
