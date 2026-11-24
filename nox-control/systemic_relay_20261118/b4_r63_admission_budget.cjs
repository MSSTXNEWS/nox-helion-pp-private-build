'use strict';
// B4 R63 opt-in local deadline witness/fence. Never grants owner admission.
// Wrap the final transport BELOW the authenticated R73 guard; begin wraps R71.
// No retries, no network, no synthetic IDs. All times share one monotonic clock.
function createAdmissionBudget({transport,limitMs,now=()=>globalThis.performance.now(),maxRecords=4096}={}){
  const fail=code=>{throw Object.assign(new Error(code),{code});};
  const id=/^[A-Za-z0-9._:-]{1,128}$/;
  if(!transport||typeof transport.post!=='function'||typeof transport.readback!=='function'||typeof transport.ack!=='function'||typeof now!=='function'||!Number.isSafeInteger(limitMs)||limitMs<1||limitMs>600000||!Number.isSafeInteger(maxRecords)||maxRecords<1)fail('HOLD_B4_BUDGET_CONFIG');
  const records=new Map(),send=transport.post.bind(transport);
  function scope(raw){
    const s=Object.freeze({conversation_id:raw?.conversation_id,exchange_id:raw?.exchange_id});
    if(typeof s.conversation_id!=='string'||!id.test(s.conversation_id)||typeof s.exchange_id!=='string'||!id.test(s.exchange_id))fail('HOLD_B4_BUDGET_SCOPE');
    return [s,s.conversation_id+'\0'+s.exchange_id];
  }
  function elapsed(r){
    const t=now();
    if(!Number.isFinite(t)||t<r.last){r.reason='HOLD_B4_BUDGET_CLOCK';fail(r.reason);}
    r.last=t;return t-r.start;
  }
  async function begin(client,raw){
    const [s,k]=scope(raw);
    if(!client||typeof client.begin!=='function')fail('HOLD_B4_BUDGET_CONFIG');
    if(records.has(k))fail('HOLD_B4_BUDGET_NO_REPOST');
    if(records.size>=maxRecords)fail('HOLD_B4_BUDGET_CAPACITY');
    const start=now();if(!Number.isFinite(start))fail('HOLD_B4_BUDGET_CLOCK');
    const r={start,last:start,closed:false,checked:false,invoked:false,admission_elapsed_ms:null,reason:null};
    records.set(k,r);
    try{return await client.begin(s);}finally{r.closed=true;}
  }
  async function post(raw,signal){
    const [s,k]=scope(raw),r=records.get(k);
    if(!r||r.closed||r.checked)fail('HOLD_B4_BUDGET_NO_ADMISSION');
    r.checked=true;
    if(!signal||signal.aborted!==false){r.reason='HOLD_B4_BUDGET_STOPPED';fail(r.reason);}
    r.admission_elapsed_ms=elapsed(r);
    if(r.admission_elapsed_ms>=limitMs){r.reason='HOLD_B4_BUDGET_EXPIRED';fail(r.reason);}
    if(signal.aborted!==false){r.reason='HOLD_B4_BUDGET_STOPPED';fail(r.reason);}
    r.invoked=true;
    // Invocation is NOT a server admission receipt. No async boundary here.
    return send(s,signal);
  }
  function report(raw){
    const [,k]=scope(raw),r=records.get(k);
    if(!r)fail('HOLD_B4_BUDGET_SCOPE');
    return Object.freeze({admission_elapsed_ms:r.admission_elapsed_ms,transport_invoked:r.invoked,reason:r.reason,closed:r.closed,physical_glm_measured:false,native_accepted:false});
  }
  const out={post,readback:transport.readback.bind(transport),ack:transport.ack.bind(transport)};
  if(typeof transport.readCanonicalAck==='function')out.readCanonicalAck=transport.readCanonicalAck.bind(transport);
  return Object.freeze({begin,transport:Object.freeze(out),report});
}
module.exports={createAdmissionBudget};
