/* NOX B1: opt-in IndexedDB adapter for browser terminal ACK/readback.
 * SOURCE ONLY. No import-time side effects, no model POST, no UI or S03 writes.
 * Caller MUST provide independently authenticated authorizeEnvelope and
 * freshPermit callbacks. IndexedDB is origin-local, NOT a server proof or
 * protection from scripts already running in the same origin.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.NOXB1IndexedAckStore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const STORE = 'terminal_acks';
  const PAIR = ['conversation_id', 'exchange_id'];
  const ID = /^[A-Za-z0-9._:-]{1,128}$/;
  const HEX = /^[a-f0-9]{64}$/;
  const CURSOR = /^[A-Za-z0-9_-]{1,1200}$/;
  const FIELDS = ['conversation_id','exchange_id','event_id','next_cursor',
                  'response_sha256','s03_proof_sha256'];
  class HoldIndexedAck extends Error {
    constructor(code) { super(code); this.name = 'HoldIndexedAck'; this.code = code; }
  }
  function hold(code) { throw new HoldIndexedAck(code); }
  function str(v, re, code) {
    if (typeof v !== 'string' || !re.test(v)) hold(code);
    return v;
  }
  function snapshot(p) {
    if (!p || typeof p !== 'object' || Array.isArray(p) ||
        p.readback_only !== true || typeof p.emit_terminal !== 'boolean')
      hold('HOLD_ACK_PACKET');
    return Object.freeze({
      conversation_id:str(p.conversation_id,ID,'HOLD_ACK_SCOPE'),
      exchange_id:str(p.exchange_id,ID,'HOLD_ACK_SCOPE'),
      event_id:str(p.event_id,HEX,'HOLD_ACK_EVENT'),
      next_cursor:str(p.next_cursor,CURSOR,'HOLD_ACK_CURSOR'),
      response_sha256:str(p.response_sha256,HEX,'HOLD_ACK_PROOF'),
      s03_proof_sha256:str(p.s03_proof_sha256,HEX,'HOLD_ACK_PROOF'),
      readback_only:true
    });
  }
  function matches(saved,p) {
    return saved && typeof saved === 'object' && saved.durable === true &&
      FIELDS.every(f => saved[f] === p[f]) && saved.readback_only === true;
  }
  function quotaCode(err, fallback) {
    return err && err.name === 'QuotaExceededError' ? 'HOLD_ACK_QUOTA' : fallback;
  }
  function dbOpen(idb, name, onLost) {
    return new Promise((resolve,reject) => {
      let request, settled=false;
      const fail=code => {if (!settled) {settled=true; reject(new HoldIndexedAck(code));}};
      try {
        request=idb.open(name,1);
        request.onupgradeneeded=ev=>{
          try {
            // Never migrate or overwrite an older, unrelated client database.
            if (ev.oldVersion !== 0) {request.transaction.abort();return;}
            const s=request.result.createObjectStore(STORE,{keyPath:PAIR});
            s.createIndex('event_id','event_id',{unique:true});
          } catch (_) {try {request.transaction.abort();} catch (_) {}}
        };
        request.onblocked=()=>fail('HOLD_ACK_DB_BLOCKED');
        request.onerror=()=>fail('HOLD_ACK_DB_OPEN');
        request.onsuccess=()=>{
          const db=request.result;
          if (settled) {db.close();return;}
          try {
            if (!db.objectStoreNames.contains(STORE)) hold('HOLD_ACK_SCHEMA');
            const tx=db.transaction(STORE,'readonly');
            const s=tx.objectStore(STORE);
            const kp=s.keyPath;
            if (!Array.isArray(kp) || kp.length!==2 ||
                kp[0]!==PAIR[0] || kp[1]!==PAIR[1] ||
                !s.indexNames.contains('event_id')) hold('HOLD_ACK_SCHEMA');
            const ix=s.index('event_id');
            if (ix.unique!==true || ix.keyPath!=='event_id')
              hold('HOLD_ACK_SCHEMA');
            // A schema upgrade revokes this host, even if the connection
            // closes cleanly. Do not accept another terminal on the stale DB.
            db.onversionchange=()=>{onLost('HOLD_ACK_VERSIONCHANGE');db.close();};
            db.onclose=()=>onLost('HOLD_ACK_DB_CLOSED');
            if (!settled) {settled=true; resolve(db);}
          } catch (_) {db.close();fail('HOLD_ACK_SCHEMA');}
        };
      } catch (_) {fail('HOLD_ACK_DB_OPEN');}
    });
  }
  function write(db,p) {
    return new Promise((resolve,reject)=>{
      let tx, result='COMMITTED', done=false, error='HOLD_ACK_TX';
      const fail=()=>{if (!done) {done=true;reject(new HoldIndexedAck(error));}};
      try {
        // A single readwrite transaction serializes conflicting pair writes.
        // The unique event index also prevents event_id aliasing across turns.
        tx=db.transaction(STORE,'readwrite',{durability:'strict'});
        tx.oncomplete=()=>{if (!done) {done=true;resolve(result);}};
        tx.onabort=()=>{error=quotaCode(tx.error,error);fail();};
        tx.onerror=()=>{
          // IDB request errors bubble. Retain the specific request failure.
          if (!['HOLD_ACK_EVENT_COLLISION','HOLD_ACK_CONFLICT','HOLD_ACK_QUOTA'].includes(error))
            error=quotaCode(tx.error,'HOLD_ACK_TX');
        };
        const req=tx.objectStore(STORE).get([p.conversation_id,p.exchange_id]);
        req.onerror=()=>{error=quotaCode(req.error,'HOLD_ACK_TX');try {tx.abort();}catch (_) {}};
        req.onsuccess=()=>{
          try {
            const previous=req.result;
            if (previous) {
              if (!matches(previous,p)) {
                error='HOLD_ACK_CONFLICT';tx.abort();return;
              }
              result='ALREADY_COMMITTED';
            } else {
              const add=tx.objectStore(STORE).add({...p,durable:true});
              add.onerror=()=>{
                error=quotaCode(add.error,
                  add.error && add.error.name==='ConstraintError' ?
                  'HOLD_ACK_EVENT_COLLISION' : 'HOLD_ACK_TX');
              };
            }
          } catch (err) {error=quotaCode(err,'HOLD_ACK_TX');try {tx.abort();}catch (_) {}}
        };
      } catch (err) {error=quotaCode(err,'HOLD_ACK_TX');fail();}
    });
  }
  function read(db,conversation_id,exchange_id) {
    str(conversation_id,ID,'HOLD_ACK_SCOPE');
    str(exchange_id,ID,'HOLD_ACK_SCOPE');
    return new Promise((resolve,reject)=>{
      let tx, value=null, finished=false;
      const fail=()=>{if (!finished) {finished=true;reject(new HoldIndexedAck('HOLD_ACK_READ'));}};
      try {
        tx=db.transaction(STORE,'readonly');
        tx.oncomplete=()=>{if (!finished) {finished=true;resolve(value);}};
        tx.onabort=fail;tx.onerror=fail;
        const req=tx.objectStore(STORE).get([conversation_id,exchange_id]);
        req.onerror=fail;
        req.onsuccess=()=>{
          // Only expose immutable copied proof fields. Read in a separate
          // transaction after the write commits: not the in-memory input.
          const r=req.result;
          value=r?Object.freeze({...Object.fromEntries(FIELDS.map(k=>[k,r[k]])),
                                  readback_only:r.readback_only,durable:r.durable}):null;
        };
      } catch (_) {fail();}
    });
  }
  async function openClientAckHost({indexedDB, databaseName,
                                   authorizeEnvelope,freshPermit}={}) {
    if (!indexedDB || typeof indexedDB.open!=='function' ||
        typeof authorizeEnvelope!=='function' ||
        typeof freshPermit!=='function')
      hold('HOLD_ACK_HOST_CONTRACT');
    const name=str(databaseName, /^[A-Za-z0-9._:-]{1,100}$/, 'HOLD_ACK_DB_NAME');
    let closed=false, invalidated=null;
    const db=await dbOpen(indexedDB,name,code=>{if (!invalidated) invalidated=code;});
    function live() {
      if (invalidated) hold(invalidated);
      if (closed) hold('HOLD_ACK_CLOSED');
    }
    return Object.freeze({
      authorizeEnvelope:async p=>{live();return authorizeEnvelope(p);},
      freshPermit:async p=>{live();return freshPermit(p);},
      commitTerminalAndAck:async raw=>{live();return write(db,snapshot(raw));},
      readCommitted:async (conversation,exchange)=>{live();return read(db,conversation,exchange);},
      close:()=>{if(!closed){closed=true;db.close();}}
    });
  }
  return Object.freeze({openClientAckHost,HoldIndexedAck});
});
