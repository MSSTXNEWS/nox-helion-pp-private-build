/* NOX B1 isolated cross-tab terminal ACK fence. No native route, model POST,
 * S03 write or serving side effects. Fail closed if an ACK may have been sent:
 * SENDING has no automatic timeout/takeover. Server idempotency is still required.
 */
(function(root,factory) {
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.NOXB1CrossTabAckLease=api;
})(typeof globalThis!=='undefined'?globalThis:this,function() {
  'use strict';
  const STORE='ack_fences', ID=/^[A-Za-z0-9._:-]{1,128}$/;
  const HEX=/^[a-f0-9]{64}$/, CURSOR=/^[A-Za-z0-9_-]{1,1200}$/;
  class HoldCrossTab extends Error {
    constructor(code) { super(code); this.name='HoldCrossTab';this.code=code; }
  }
  const hold=code=>{throw new HoldCrossTab(code);};
  function snapshot(raw,event,cursor) {
    if(!raw||typeof raw!=='object'||typeof raw.conversation_id!=='string'||
       typeof raw.exchange_id!=='string'||!ID.test(raw.conversation_id)||
       !ID.test(raw.exchange_id)||typeof event!=='string'||!HEX.test(event)||
       typeof cursor!=='string'||!CURSOR.test(cursor)) hold('HOLD_CROSSTAB_SCOPE');
    return Object.freeze({conversation_id:raw.conversation_id,
      exchange_id:raw.exchange_id,event_id:event,cursor});
  }
  async function digest(cursor) {
    if(!globalThis.crypto||!crypto.subtle) hold('HOLD_CROSSTAB_CRYPTO');
    const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(cursor));
    return Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
  }
  function dbOpen(indexedDB,name) {
    return new Promise((resolve,reject)=>{
      let req,settled=false;
      const fail=code=>{if(!settled){settled=true;reject(new HoldCrossTab(code));}};
      try {
        req=indexedDB.open(name,1);
        req.onupgradeneeded=e=>{
          if(e.oldVersion!==0){req.transaction.abort();return;}
          const store=req.result.createObjectStore(STORE,{keyPath:['conversation_id','exchange_id']});
          store.createIndex('event_id','event_id',{unique:true});
        };
        req.onblocked=()=>fail('HOLD_CROSSTAB_OPEN_BLOCKED');
        req.onerror=()=>fail('HOLD_CROSSTAB_OPEN');
        req.onsuccess=()=>{
          const db=req.result;
          if(settled){db.close();return;}
          try {
            const tx=db.transaction(STORE,'readonly'),s=tx.objectStore(STORE);
            if(!Array.isArray(s.keyPath)||s.keyPath.join('/')!=='conversation_id/exchange_id'||
               !s.indexNames.contains('event_id')||
               s.index('event_id').keyPath!=='event_id'||
               s.index('event_id').unique!==true) hold('HOLD_CROSSTAB_SCHEMA');
          }catch(_){db.close();fail('HOLD_CROSSTAB_SCHEMA');return;}
          settled=true;resolve(db);
        };
      }catch(_){fail('HOLD_CROSSTAB_OPEN');}
    });
  }
  function mutate(db,k,operation) {
    return new Promise((resolve,reject)=>{
      let tx,answer,error='HOLD_CROSSTAB_TX',settled=false;
      const fail=()=>{if(!settled){settled=true;reject(new HoldCrossTab(error));}};
      try {
        tx=db.transaction(STORE,'readwrite',{durability:'strict'});
        tx.oncomplete=()=>{if(!settled){settled=true;resolve(answer);}};
        tx.onabort=fail;
        // A request error bubbles through tx; preserve the more specific code.
        tx.onerror=()=>{};
        const s=tx.objectStore(STORE),req=s.get(k);
        req.onerror=()=>{error='HOLD_CROSSTAB_READ';try{tx.abort();}catch(_){}};
        req.onsuccess=()=>{
          try {
            const update=operation(req.result);
            if(update.error){error=update.error;tx.abort();return;}
            answer=update.value;
            if(update.write){
              const put=s.put(update.write);
              put.onerror=()=>{
                error=put.error&&put.error.name==='ConstraintError'?
                  'HOLD_CROSSTAB_EVENT_COLLISION':'HOLD_CROSSTAB_WRITE';
              };
            }
          }catch(_){error='HOLD_CROSSTAB_TX';try{tx.abort();}catch(_){}}
        };
      }catch(_){fail();}
    });
  }
  async function createGate({indexedDB,databaseName,ttlMs=30000}={}) {
    if(!indexedDB||typeof indexedDB.open!=='function'||
       typeof databaseName!=='string'||!/^[A-Za-z0-9._:-]{1,100}$/.test(databaseName)||
       !Number.isSafeInteger(ttlMs)||ttlMs<20||ttlMs>600000)
      hold('HOLD_CROSSTAB_CONTRACT');
    const db=await dbOpen(indexedDB,databaseName);
    let closed=false,invalidated=null;
    db.onversionchange=()=>{invalidated='HOLD_CROSSTAB_VERSIONCHANGE';db.close();};
    db.onclose=()=>{if(!closed)invalidated='HOLD_CROSSTAB_DB_CLOSED';};
    function live() {if(invalidated)hold(invalidated);if(closed)hold('HOLD_CROSSTAB_CLOSED');}
    async function reserve(raw,event,cursor) {
      live();
      const s=snapshot(raw,event,cursor),proof=await digest(s.cursor);
      live();
      const token=crypto.randomUUID(),now=Date.now(),k=[s.conversation_id,s.exchange_id];
      return mutate(db,k,prev=>{
        if(prev&&(prev.event_id!==s.event_id||prev.cursor_digest!==proof))
          return {error:'HOLD_CROSSTAB_CONFLICT'};
        if(prev){
          if(prev.state==='ACKED') return {value:Object.freeze({status:'ALREADY_ACKED'})};
          if(prev.state==='SENDING') return {error:'HOLD_CROSSTAB_ACK_UNCERTAIN'};
          if(prev.state!=='RESERVED') return {error:'HOLD_CROSSTAB_STATE'};
          if(now<=prev.expires_at) return {error:'HOLD_CROSSTAB_RESERVED'};
        }
        const generation=(prev?prev.generation:0)+1;
        const write={conversation_id:s.conversation_id,exchange_id:s.exchange_id,
          event_id:s.event_id,cursor_digest:proof,state:'RESERVED',token,generation,
          expires_at:now+ttlMs};
        return {write,value:Object.freeze({status:'RESERVED',
          scope:Object.freeze({conversation_id:s.conversation_id,exchange_id:s.exchange_id}),
          token,generation})};
      });
    }
    function transition(grant,expected,target) {
      live();
      if(!grant||grant.status!=='RESERVED'||!grant.scope||
         typeof grant.token!=='string'||!Number.isSafeInteger(grant.generation))
        hold('HOLD_CROSSTAB_GRANT');
      return mutate(db,[grant.scope.conversation_id,grant.scope.exchange_id],prev=>{
        if(!prev||prev.state!==expected||prev.token!==grant.token||
           prev.generation!==grant.generation) return {error:'HOLD_CROSSTAB_FENCED'};
        if(expected==='RESERVED'&&Date.now()>prev.expires_at)
          return {error:'HOLD_CROSSTAB_EXPIRED'};
        return {write:{...prev,state:target},value:target};
      });
    }
    return Object.freeze({
      reserve,
      beginSend:grant=>transition(grant,'RESERVED','SENDING'),
      confirm:grant=>transition(grant,'SENDING','ACKED'),
      // Unknown delivery never releases the SENDING record.
      close:()=>{if(!closed){closed=true;db.close();}}
    });
  }
  return Object.freeze({createGate,HoldCrossTab});
});
