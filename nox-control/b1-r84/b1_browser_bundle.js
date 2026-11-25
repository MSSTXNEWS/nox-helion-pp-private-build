/* B1 R82: independent read-only DOM observation; never ACK/POST authority.
 * Host must authenticate terminal context and durable ACK state, and retain
 * detached immutable bytes in its approved evidence store. No native claim.
 */
(function(root){
'use strict';
const SCOPE=['conversation_id','physical_dialog_id','s03_dialog_id','session_id','served_sha256','server_sha256','owner_admission_receipt_sha256'];
const BIND=['turn','exchange_id','request_id','attempt_id','event_id','turn_id','user_message_id','assistant_message_id'];
const ID=/^[A-Za-z0-9._:-]{1,128}$/;
const SHA=/^[0-9a-f]{64}$/;
const hold=()=>{const e=new Error('HOLD_B1_PREACK_OBSERVATION');e.code=e.message;throw e;};
const pin=v=>typeof v==='string'&&SHA.test(v)&&new Set(v).size>1;
const id=v=>typeof v==='string'&&ID.test(v);
function create({container,host,crypto=root.crypto}){
 if(!container||!host||typeof host.readPreAckContext!=='function'||
    typeof host.retainPreAckObservation!=='function'||!crypto||!crypto.subtle||
    typeof crypto.randomUUID!=='function')hold();
 const view=container.ownerDocument.defaultView;
 async function hash(text){
   const bytes=new TextEncoder().encode(text);
   if(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes)!==text)hold();
   return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
 }
 function row(s,event){
   if(!container.isConnected||!view)hold();
   const rows=Array.from(container.children).filter(el=>el.dataset.noxB1Conversation===s.conversation_id&&el.dataset.noxB1Exchange===s.exchange_id);
   if(rows.length!==1)hold();
   const el=rows[0];
   if(!el.isConnected||el.dataset.noxB1State!=='terminal'||el.dataset.noxB1EventId!==event||
      el.childElementCount!==0||!el.getClientRects().length)hold();
   for(let p=el;p;p=p.parentElement){
     const cs=view.getComputedStyle(p);
     if(p.hidden||p.getAttribute('aria-hidden')==='true'||cs.display==='none'||
        cs.visibility!=='visible'||Number(cs.opacity)===0||cs.contentVisibility==='hidden')hold();
   }
   return el;
 }
 return async function observe(s,proof,witness,signal,registerRecheck){
   if(!signal||signal.aborted)hold();
   // Host reads authoritative state; do not infer NOT_SENT from DOM or fixture.
   const context=await host.readPreAckContext(s,proof,witness,signal);
   if(signal.aborted)hold();
   if(!context||typeof context!=='object')hold();
   // Historical/uncertain ACK never gets a fabricated pre-ACK observation.
   if(context.ack_state!=='NOT_SENT')return false;
   const snapshot={...context};
   if(snapshot.ack_state!=='NOT_SENT'||!snapshot.scope||!snapshot.terminal)hold();
   const sc=Object.freeze({...snapshot.scope}),t=Object.freeze({...snapshot.terminal});
   const c=Object.freeze({...snapshot,scope:sc,terminal:t});
   if(!SCOPE.every(k=>k.endsWith('sha256')?pin(sc[k]):id(sc[k]))||
      !BIND.every(k=>k==='turn'?[2,3].includes(t[k]):id(t[k]))||
      !pin(c.browser_sha256)||!pin(c.terminal_receipt_sha256)||
      !pin(t.answer_sha256)||t.state!=='TERMINAL_SAVED'||t.eof!==true||
      sc.conversation_id!==s.conversation_id||t.exchange_id!==s.exchange_id||
      sc.physical_dialog_id!==proof.physical_dialog_id||sc.s03_dialog_id!==proof.s03_dialog_id||
      sc.session_id!==proof.s03_session_id||sc.served_sha256!==proof.served_sha256||
      t.turn!==proof.sequence||t.request_id!==proof.request_id||t.attempt_id!==proof.attempt_id||
      t.event_id!==proof.s03_event_id||t.turn_id!==proof.s03_turn_id||
      t.assistant_message_id!==proof.assistant_message_id||t.answer_sha256!==proof.answer_sha256)hold();
   const event=witness.projection_event_id;
   const el=row(s,event),visible=el.textContent;
   const digest=await hash(visible);
   if(signal.aborted||row(s,event)!==el||el.textContent!==visible||digest!==t.answer_sha256)hold();
   const oid=crypto.randomUUID();if(!id(oid))hold();
   const doc={};for(const k of SCOPE)doc[k]=sc[k];for(const k of BIND)doc[k]=t[k];
   Object.assign(doc,{schema:'nox.browser.projection-readback.v1',observation_id:oid,
      browser_sha256:c.browser_sha256,terminal_receipt_sha256:c.terminal_receipt_sha256,
      visible_text_sha256:digest,visible_row_count:1,state:'TERMINAL_VISIBLE',ack_state:'NOT_SENT'});
   const bytes=JSON.stringify(doc),sha256=await hash(bytes);
   if(signal.aborted||row(s,event)!==el||el.textContent!==visible)hold();
   // Host must compare-and-retain against the same independent NOT_SENT state;
   // exact true attests retention only; never grants ACK or native acceptance.
   const retained=await host.retainPreAckObservation(Object.freeze({bytes,sha256}),c,signal);
   if(retained!==true||signal.aborted||row(s,event)!==el||el.textContent!==visible)hold();
   // Retention is only a snapshot. Recheck the SAME visible row synchronously
   // immediately before the durable transition and actual ACK invocation.
   if(registerRecheck!==undefined){
     if(typeof registerRecheck!=='function')hold();
     registerRecheck(()=>{if(row(s,event)!==el||el.textContent!==visible)hold();return true;});
   }
   return true;
 };
}
root.NOXB1PreAckObserver=Object.freeze({create});
})(typeof globalThis!=='undefined'?globalThis:this);

/* NOX B1: opt-in browser DOM adapter for streamed turns.
 * Caller must pass AbortSignal from SSE client into onDelta().
 * UI projection is NOT proof of server ACK, model completion or S03 storage.
 * No network calls, storage writes, or production wiring occur in this module.
 */
(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object' && module.exports) module.exports=api;
  else root.NOXB1AbortSafeUI=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const ID=/^[A-Za-z0-9._:-]{1,128}$/;
  // Multiple opt-in adapters can coexist during chat reattachment. Their
  // exchange queues must be shared for the same live DOM container.
  const containerStates=new WeakMap();
  class UiHold extends Error {
    constructor(code){super(code);this.name='UiHold';this.code=code;}
  }
  const hold=code=>{throw new UiHold(code);};
  const SHA=/^[0-9a-f]{64}$/;
  async function textSha(text){
    if(!globalThis.crypto||!globalThis.crypto.subtle) hold('HOLD_B1_UI_TEXT_CRYPTO');
    // TextEncoder silently replaces lone UTF-16 surrogates. Reject them so
    // the browser hashes the exact strict UTF-8 bytes used by B5.
    const bytes=new TextEncoder().encode(text);
    if(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes)!==text)
      hold('HOLD_B1_UI_TEXT_ENCODING');
    return Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes)),
      x=>x.toString(16).padStart(2,'0')).join('');
  }
  function scope(s){
    if(!s||typeof s!=='object'||Array.isArray(s)) hold('HOLD_B1_UI_SCOPE');
    // Snapshot identity once; getters must not change the validated FIFO key.
    const conversation_id=s.conversation_id,exchange_id=s.exchange_id;
    if(typeof conversation_id!=='string'||!ID.test(conversation_id)||
       typeof exchange_id!=='string'||!ID.test(exchange_id))
      hold('HOLD_B1_UI_SCOPE');
    return {conversation_id,exchange_id};
  }
  function createUiAdapter({container,beforeCommit=()=>Promise.resolve(),terminalTimeoutMs=30000,deltaPrecommitTimeoutMs=30000}={}){
    if(!container||container.nodeType!==1||
       !container.ownerDocument||
       typeof container.ownerDocument.createElement!=='function'||
       typeof beforeCommit!=='function'||
       !Number.isSafeInteger(terminalTimeoutMs)||terminalTimeoutMs<1||terminalTimeoutMs>120000||
       !Number.isSafeInteger(deltaPrecommitTimeoutMs)||
       deltaPrecommitTimeoutMs<1||deltaPrecommitTimeoutMs>120000)
      hold('HOLD_B1_UI_CONTRACT');
    // Search existing direct children, not only memory, so adapter recreation
    // after reload/reattachment does not duplicate an already-present turn.
    function find(s){
      let found=null;
      for(const el of container.children){
        if(el.dataset.noxB1Conversation===s.conversation_id&&
           el.dataset.noxB1Exchange===s.exchange_id){
          if(found) hold('HOLD_B1_DUPLICATE_DOM_TURN');
          found=el;
        }
      }
      return found;
    }
    function create(s){
      const el=container.ownerDocument.createElement('div');
      el.dataset.noxB1Conversation=s.conversation_id;
      el.dataset.noxB1Exchange=s.exchange_id;
      el.dataset.noxB1State='streaming';
      container.appendChild(el);
      return el;
    }
    // Concurrent render callbacks may otherwise commit in completion order,
    // which silently reorders SSE tokens. Serialize each exchange independently;
    // STOP releases hung precommit waits and fences every queued DOM mutation.
    // A new adapter may be attached while the old one has async callbacks
    // pending. Per-instance queues would reorder deltas or overlap terminal
    // projections for the very same exchange (duplicate-turn risk).
    let shared=containerStates.get(container);
    if(!shared){
      shared={deltaTails:new Map(),terminalIntents:new Map(),deltaEvents:new Map()};
      containerStates.set(container,shared);
    }
    const {deltaTails,terminalIntents,deltaEvents}=shared;
    // Reserve terminal intent synchronously, before any async precommit.
    // Earlier queued deltas drain FIFO across *all* adapters of this container.
    async function onDelta(raw,delta,signal,eventId){
      const s=scope(raw);
      if(!signal||typeof signal.aborted!=='boolean'||
         typeof signal.addEventListener!=='function'||
         typeof delta!=='string') hold('HOLD_B1_UI_DELTA_CONTRACT');
      if(eventId!==undefined&&(typeof eventId!=='string'||!ID.test(eventId)))
        hold('HOLD_B1_UI_DELTA_EVENT_ID');
      if(signal.aborted) return false;
      const k=s.conversation_id+'\u0000'+s.exchange_id;
      // SSE reconnect may replay the final event. Reserve the event ID before
      // the first await, across all adapters sharing this DOM container.
      // Equal IDs with different payloads are corrupt: fail closed.
      const replayKey=eventId===undefined?null:k+'\u0000'+eventId;
      if(replayKey!==null){
        const known=deltaEvents.get(replayKey);
        if(known){
          if(known.delta!==delta) hold('HOLD_B1_UI_REPLAY_PAYLOAD');
          // A pending terminal forbids new projection, not integrity checks.
          if(terminalIntents.has(k)||known.committed) return false;
          // An overlapping reconnect must observe its OWN STOP. Waiting only
          // on the original in-flight delta could otherwise delay cancellation
          // until that adapter's precommit timeout, even after fresh STOP.
          const readback=known.promise.then(
            ok=>{
              if(signal.aborted) return false;
              return ok===true?false:onDelta(s,delta,signal,eventId);
            },
            error=>{
              if(signal.aborted) return false;
              // A failed prior projection releases its ID reservation; allow
              // GET-only replay using the same event, without a second POST.
              if(deltaEvents.get(replayKey)!==known)
                return onDelta(s,delta,signal,eventId);
              throw error;
            }
          );
          let onAbort;
          const stopped=new Promise(resolve=>{
            onAbort=()=>resolve(false);
            signal.addEventListener('abort',onAbort,{once:true});
            if(signal.aborted) onAbort();
          });
          return Promise.race([readback,stopped]).finally(()=>{
            signal.removeEventListener('abort',onAbort);
          });
        }
      }
      if(terminalIntents.has(k)) return false;
      // A canonical terminal already committed to this DOM is immutable.
      // Late transport deltas must not call an untrusted/hung precommit again.
      // Preserve known event-ID conflict/replay checks above this fast path.
      const terminalRow=find(s);
      if(terminalRow&&terminalRow.dataset.noxB1State==='terminal')
        return false;
      const previous=deltaTails.get(k)||Promise.resolve();
      let reservation=null,projected=false;
      const job=previous.catch(()=>{}).then(async()=>{
        if(signal.aborted) return false;
        let onAbort,timeoutId=null;
        let outcome;
        try{
          outcome=await Promise.race([
            Promise.resolve().then(()=>beforeCommit('delta',{...s}))
              .then(()=>({ready:true}),()=>({failed:true})),
            new Promise(resolve=>{
              onAbort=()=>resolve({aborted:true});
              signal.addEventListener('abort',onAbort,{once:true});
              if(signal.aborted) onAbort();
            }),
            // An unresponsive UI precommit must not block this exchange's
            // SSE FIFO indefinitely when STOP was never dispatched.
            new Promise(resolve=>{
              timeoutId=setTimeout(()=>resolve({timedOut:true}),deltaPrecommitTimeoutMs);
            })
          ]);
        }finally{
          if(onAbort) signal.removeEventListener('abort',onAbort);
          if(timeoutId!==null) clearTimeout(timeoutId);
        }
        if(outcome.aborted||signal.aborted) return false;
        if(outcome.timedOut) hold('HOLD_B1_UI_DELTA_TIMEOUT');
        if(outcome.failed) hold('HOLD_B1_UI_PRECOMMIT');
        let el=find(s);
        // A terminal projection is immutable; a late delta cannot reopen it.
        if(el&&el.dataset.noxB1State==='terminal') return false;
        if(!el) el=create(s);
        // textContent, never innerHTML: arbitrary model text cannot inject DOM.
        el.textContent+=delta;
        projected=true;
        if(reservation) reservation.committed=true;
        return true;
      });
      deltaTails.set(k,job);
      if(replayKey!==null){
        reservation={delta,committed:false,promise:job};
        deltaEvents.set(replayKey,reservation);
      }
      const release=()=>{
        if(deltaTails.get(k)===job) deltaTails.delete(k);
        // STOP, timeout or failed precommit must not poison a GET-only replay.
        if(reservation&&!reservation.committed&&
           deltaEvents.get(replayKey)===reservation)
          deltaEvents.delete(replayKey);
      };
      job.then(release,release);
      // Caller STOP must not wait behind an unrelated live FIFO precommit.
      // Keep the internal job/tail reserved until it drains in order.
      let onCallerAbort;
      const callerStopped=new Promise(resolve=>{
        onCallerAbort=()=>{if(!projected) resolve(false);};
        signal.addEventListener('abort',onCallerAbort,{once:true});
        if(signal.aborted) onCallerAbort();
      });
      return Promise.race([job,callerStopped]).finally(()=>{
        signal.removeEventListener('abort',onCallerAbort);
      });
    }
    // The SSE caller may pass the exchange STOP signal. Legacy callers still
    // have a finite precommit timeout and cannot commit after it has expired.
    function upsertTerminal(raw,eventId,signal,proof){
      const s=scope(raw);
      if(!proof||proof.conversation_id!==s.conversation_id||proof.exchange_id!==s.exchange_id||
         typeof proof.assistant_text!=='string'||!proof.assistant_text||
         typeof proof.answer_sha256!=='string'||!SHA.test(proof.answer_sha256))
        hold('HOLD_B1_UI_CANONICAL_TEXT');
      const text=proof.assistant_text, digest=proof.answer_sha256;
      proof=Object.freeze({conversation_id:s.conversation_id,exchange_id:s.exchange_id,
        assistant_text:text,answer_sha256:digest});
      if(typeof eventId!=='string'||!ID.test(eventId))
        hold('HOLD_B1_UI_EVENT_ID');
      if(signal!==undefined&&(!signal||typeof signal.aborted!=='boolean'||
         typeof signal.addEventListener!=='function'||
         typeof signal.removeEventListener!=='function'))
        hold('HOLD_B1_UI_TERMINAL_SIGNAL');
      if(signal&&signal.aborted) return Promise.resolve(false);
      const k=s.conversation_id+'\u0000'+s.exchange_id;
      const pending=terminalIntents.get(k);
      if(pending){
        if(pending.eventId!==eventId||pending.digest!==digest||pending.text!==text)
          hold('HOLD_B1_UI_CONFLICTING_TERMINAL');
        // A reconnect with a fresh STOP signal must not inherit false from
        // an already-aborted terminal projection. Wait for its reservation to
        // settle, then project the same server-verified event via GET-only
        // readback. Never overlap two writers or accept a different event ID.
        // A legacy projection may have NO AbortSignal. A fresh reconnect
        // waiter still owns its own STOP and must not wait for legacy's
        // potentially hung precommit/deadline before returning HOLD.
        if(signal&&pending.signal!==signal){
          // Reconnect can arrive before the old signal gets STOP. A new
          // live signal must observe the old result, then safely retry the
          // same canonical terminal event after an aborted old projection.
          // A later STOP of the new signal must also win this waiting race.
          // A fresh STOP must release its reconnect waiter immediately,
          // even if the previous terminal precommit remains hung. Waiting
          // exclusively on pending.promise delays STOP until the old timeout.
          // Promise.race observes both outcomes, so a late rejection cannot
          // turn into an unhandled rejection after the fresh signal aborts.
          const readback=pending.promise.then(
            projected=>{
              if(signal.aborted) return false;
              return projected===true?true:upsertTerminal(s,eventId,signal,proof);
            },
            error=>{
              if(signal.aborted) return false;
              // A legacy projection can have no signal. If it expires
              // without committing, the fresh GET-only reconnect must be
              // allowed to project the SAME event instead of inheriting its
              // timeout. Do not retry arbitrary precommit/DOM failures.
              if((pending.signal&&pending.signal.aborted)||
                 (error instanceof UiHold&&
                  error.code==='HOLD_B1_UI_TERMINAL_TIMEOUT'))
                return upsertTerminal(s,eventId,signal,proof);
              throw error;
            }
          );
          let onAbort;
          const stopped=new Promise(resolve=>{
            onAbort=()=>resolve(false);
            signal.addEventListener('abort',onAbort,{once:true});
            if(signal.aborted) onAbort();
          });
          return Promise.race([readback,stopped]).finally(()=>{
            signal.removeEventListener('abort',onAbort);
          });
        }
        return pending.promise;
      }
      // Completed terminal events are already visible. An SSE reconnect
      // may replay their ID after the original async intent was released.
      // Avoid repeating beforeCommit (which may be expensive or have UI
      // side effects) and preserve a single immutable DOM turn.
      const existing=find(s);
      if(existing&&existing.dataset.noxB1State==='terminal'){
        if(existing.dataset.noxB1EventId!==eventId||
           (existing.dataset.noxB1AnswerSha256&&existing.dataset.noxB1AnswerSha256!==digest))
          hold('HOLD_B1_UI_CONFLICTING_TERMINAL');
        // A legacy terminal without a verified digest may be repaired.
        // A previously verified row is immutable; re-read it before ACK.
        if(existing.dataset.noxB1AnswerSha256&&existing.textContent!==text)
          hold('HOLD_B1_UI_CANONICAL_TEXT_MISMATCH');
      }
      const previous=deltaTails.get(k)||Promise.resolve();
      const job=Promise.resolve().then(async()=>{
        let closed=false, onAbort, timer=null;
        const cancellation=new Promise(resolve=>{
          onAbort=()=>{closed=true;resolve({kind:'aborted'});};
          if(signal){
            signal.addEventListener('abort',onAbort,{once:true});
            if(signal.aborted) onAbort();
          }
          timer=setTimeout(()=>{
            closed=true;
            resolve({kind:'timeout'});
          },terminalTimeoutMs);
        });
        const projection=(async()=>{
          // Earlier queued deltas drain first. Abort also interrupts a hung
          // pending delta without waiting for its precommit to resolve.
          // A rejected streaming delta must not poison a later, independently
          // verified GET-only terminal projection. Preserve FIFO ordering but
          // treat prior delta failure as non-terminal; STOP/conflict fences
          // below still apply before any DOM mutation or ACK witness.
          await previous.catch(()=>{});
          if(closed||(signal&&signal.aborted)) return {kind:'aborted'};
          await beforeCommit('terminal',{...s});
          // No asynchronous gap between this fence and the DOM mutation.
          if(closed||(signal&&signal.aborted)) return {kind:'aborted'};
          let el=find(s);
          if(el&&el.dataset.noxB1EventId&&el.dataset.noxB1EventId!==eventId)
            hold('HOLD_B1_UI_CONFLICTING_TERMINAL');
          if(await textSha(text)!==digest) hold('HOLD_B1_UI_CANONICAL_TEXT_MISMATCH');
          if(closed||(signal&&signal.aborted)) return {kind:'aborted'};
          el=find(s);
          if(el&&el.dataset.noxB1EventId&&el.dataset.noxB1EventId!==eventId)
            hold('HOLD_B1_UI_CONFLICTING_TERMINAL');
          if(!el) el=create(s);
          if(el.dataset.noxB1AnswerSha256&&
             (el.dataset.noxB1AnswerSha256!==digest||el.textContent!==text))
            hold('HOLD_B1_UI_CANONICAL_TEXT_MISMATCH');
          // Replace rather than append. Do not mark complete until hashing
          // an independent read of the actual DOM text succeeds.
          if(el.textContent!==text) el.textContent=text;
          if(!el.dataset.noxB1AnswerSha256) el.dataset.noxB1State='streaming';
          const rendered=el.textContent;
          if(await textSha(rendered)!==digest) hold('HOLD_B1_UI_CANONICAL_TEXT_MISMATCH');
          if(closed||(signal&&signal.aborted)) return {kind:'aborted'};
          if(find(s)!==el||el.textContent!==rendered||rendered!==text)
            hold('HOLD_B1_UI_CANONICAL_TEXT_MISMATCH');
          el.dataset.noxB1EventId=eventId;
          el.dataset.noxB1AnswerSha256=digest;
          el.dataset.noxB1State='terminal';
          return {kind:'done'};
        })().catch(error=>({kind:'error',error}));
        try{
          const outcome=await Promise.race([projection,cancellation]);
          if(outcome.kind==='timeout') hold('HOLD_B1_UI_TERMINAL_TIMEOUT');
          if(outcome.kind==='error') throw outcome.error;
          return outcome.kind==='done';
        }finally{
          closed=true;
          if(timer!==null) clearTimeout(timer);
          if(signal&&onAbort) signal.removeEventListener('abort',onAbort);
        }
      });
      const intent={eventId,digest,text,promise:job,signal};
      terminalIntents.set(k,intent);
      const release=()=>{if(terminalIntents.get(k)===intent) terminalIntents.delete(k);};
      job.then(release,release);
      return job;
    }
    return Object.freeze({onDelta,upsertTerminal});
  }
  return Object.freeze({createUiAdapter,UiHold});
});

;
/* NOX B1 opt-in source-only SSE STOP -> readback reconnect bridge.
 * No side effects, no native NOX route, no S03 writes or model POST on reconnect.
 * Source fixture; caller supplies authenticated transport, owner/STOP gate, ACK
 * store, and UI upsert. Server MUST independently enforce exchange idempotency.
 */
(function(root,factory) {
  'use strict';
  const api=factory();
  if(typeof module==='object' && module.exports) module.exports=api;
  else root.NOXB1StreamReconnect=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const ID=/^[A-Za-z0-9._:-]{1,128}$/;
  const MAX_SSE_FRAME_BYTES=65536;
  // The SSE budget is bytes, not UTF-16 code units. In particular, 23k
  // three-byte characters can evade a naive 64k string.length check.
  // Fast paths avoid re-encoding ordinary short or ASCII-only fragments.
  function frameTooLarge(frame){
    if(frame.length>MAX_SSE_FRAME_BYTES) return true;
    // A UTF-16 code unit encodes to at most three UTF-8 bytes.
    if(frame.length<=Math.floor(MAX_SSE_FRAME_BYTES/3)) return false;
    if(!/[^\x00-\x7f]/.test(frame)) return false;
    return new TextEncoder().encode(frame).byteLength>MAX_SSE_FRAME_BYTES;
  }
  class HoldStream extends Error {
    constructor(code){super(code);this.code=code;this.name='HoldStream';}
  }
  const hold=code=>{throw new HoldStream(code);};
  function snap(s){
    if(!s||typeof s!=='object'||Array.isArray(s)) hold('HOLD_STREAM_SCOPE');
    // Pin each identity exactly once before validation and admission.
    const conversation_id=s.conversation_id,exchange_id=s.exchange_id;
    if(typeof conversation_id!=='string'||!ID.test(conversation_id)||
       typeof exchange_id!=='string'||!ID.test(exchange_id)) hold('HOLD_STREAM_SCOPE');
    return Object.freeze({conversation_id,exchange_id});
  }
  const key=s=>s.conversation_id+'\u0000'+s.exchange_id;
  function createClient({transport,host,bridge,ui,ackGate=null,
    observePreAck=null,strictAckNoReplay=false,timeoutMs=120000,
    canonicalFreshnessMs=30000,reconnectReadTimeoutMs=30000,
    uiProjectionTimeoutMs=30000,ackSendTimeoutMs=30000,
    canonicalAckTimeoutMs=30000}={}){
    if(!transport||!host||!bridge||!ui||
       typeof transport.post!=='function'||
       typeof transport.readback!=='function'||
       typeof transport.ack!=='function'||
       typeof host.readCommitted!=='function'||
       typeof host.verifyCanonicalText!=='function'||
       typeof bridge.acceptTerminal!=='function'||
       typeof ui.onDelta!=='function'||
       typeof ui.upsertTerminal!=='function'||
       typeof strictAckNoReplay!=='boolean'||
       (observePreAck!==null&&typeof observePreAck!=='function')||
       (ackGate && (typeof ackGate.reserve!=='function'||
         typeof ackGate.beginSend!=='function'||typeof ackGate.confirm!=='function'||
         typeof ackGate.requireCanonicalAck!=='function'||
         typeof transport.readCanonicalAck!=='function'||
         typeof host.verifyCanonicalAck!=='function'||
         typeof host.verifyFreshCanonicalAck!=='function'))||
       !Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>600000||
       !Number.isSafeInteger(canonicalFreshnessMs)||
       canonicalFreshnessMs<1000||canonicalFreshnessMs>60000||
       !Number.isSafeInteger(reconnectReadTimeoutMs)||
       reconnectReadTimeoutMs<1||reconnectReadTimeoutMs>600000||
       !Number.isSafeInteger(uiProjectionTimeoutMs)||
       uiProjectionTimeoutMs<1||uiProjectionTimeoutMs>600000||
       !Number.isSafeInteger(ackSendTimeoutMs)||
       ackSendTimeoutMs<1||ackSendTimeoutMs>600000||
       !Number.isSafeInteger(canonicalAckTimeoutMs)||
       canonicalAckTimeoutMs<1||canonicalAckTimeoutMs>600000)
      hold('HOLD_STREAM_HOST_CONTRACT');
    // STOP/timeout may win while an uncooperative model POST is pending.
    // A successful late response otherwise leaks an unclaimed SSE socket.
    // Never await cancel(), and never project or ACK an abandoned POST.
     // A readCommitted() callback may ignore AbortSignal and resolve AFTER
    // STOP with an unclaimed HTTP response. Its body is read-only; release
    // the socket without waiting on cancel() or projecting/ACKing late data.
    // Only call this for abandoned preflight results, never live witnesses.
    function cancelAbandonedGet(previous){
      try{
        const body=previous&&previous.body;
        if(!body||typeof body.cancel!=='function') return;
        const pending=body.cancel();
        if(pending&&typeof pending.catch==='function')pending.catch(()=>{});
      }catch(_){}
    }
    const started=new Set(),reconnectSeen=new Set(),ackAttempted=new Set(),
      active=new Map(),reconnecting=new Map(),
      reconnectControllers=new Map();
    async function begin(raw){
      const s=snap(raw),k=key(s);
      if(started.has(k)) hold('HOLD_STREAM_NO_REPOST');
      // Preserve RECONNECT_ONLY when a committed row exists, while refusing
      // any new POST after an ambiguous reconnect with no durable row yet.
      const priorReconnect=reconnectSeen.has(k);
      // Claim the exchange SYNCHRONOUSLY before the first await. Previously two
      // simultaneous begin() calls could both pass started.has() while the
      // host's readCommitted() promise was pending, causing two model POSTs.
      // A failed/unknown preflight also retains the local no-repost fence.
      started.add(k);
      const ctrl=new AbortController();
      active.set(k,ctrl);
      let timedOut=false;
      const stopped=()=>timedOut?'STOPPED_TIMEOUT':'STOPPED';
      const timer=setTimeout(()=>{timedOut=true;ctrl.abort();},timeoutMs);
      let reader=null,streamComplete=false;
      // Each POST response has one body owner. Snapshot once even if STOP
      // wins during an accessor; both race branches share one disposal fence.
      let postBody,postBodyRead=false,postBodyDisposed=false;
      function readPostBody(res){
        if(!postBodyRead){postBodyRead=true;postBody=res&&res.body;}
        return postBody;
      }
      function cancelAbandonedPost(res){
        if(postBodyDisposed)return;
        postBodyDisposed=true;
        try{
          const body=readPostBody(res);
          if(!body||typeof body.cancel!=='function')return;
          const pending=body.cancel();
          if(pending&&typeof pending.catch==='function')pending.catch(()=>{});
        }catch(_){}
      }
      try{
        // STOP and timeout must interrupt a hung preflight, not merely an SSE
        // stream. This remains a read-only probe; no local claim is native CAS.
        let onAbort;
        let preflight;
        try{
          preflight=await Promise.race([
            // STOP can occur synchronously before this queued microtask.
            // Do not issue an unnecessary GET after cancellation. Give
            // cooperative preflight transports the same AbortSignal as POST.
            Promise.resolve().then(async()=>{
              if(ctrl.signal.aborted) return {aborted:true};
              try{
                const previous=await host.readCommitted(
                  s.conversation_id,s.exchange_id,ctrl.signal);
                if(ctrl.signal.aborted){
                  // Race() may have already returned STOP, but the ignored
                  // GET still owns a body. Cancel it exactly once on settle.
                  cancelAbandonedGet(previous);
                  return {aborted:true};
                }
                return {previous};
              }catch(_){return {storageError:true};}
            }),
            new Promise(resolve=>{
              onAbort=()=>resolve({aborted:true});
              ctrl.signal.addEventListener('abort',onAbort,{once:true});
              if(ctrl.signal.aborted) onAbort();
            })
          ]);
        }finally{
          if(onAbort) ctrl.signal.removeEventListener('abort',onAbort);
        }
        if(preflight.aborted||ctrl.signal.aborted){
          // The GET can resolve immediately before STOP wins the race;
          // release its body here instead of retaining an orphaned socket.
          if(!preflight.aborted) cancelAbandonedGet(preflight.previous);
          return stopped();
        }
        if(preflight.storageError) hold('HOLD_STREAM_STORAGE');
        // Only an explicit null is an authoritative "not committed" result.
        // A falsy malformed/unknown lookup (undefined, false, 0, NaN, '')
        // must NOT authorize another model POST for this exchange.
        if(preflight.previous!==null&&!preflight.previous)
          hold('HOLD_STREAM_STORAGE');
        if(preflight.previous){
          // This preflight GET only checks whether the exchange already exists.
          // Its response body is not consumed by begin(), and the model must
          // never be POSTed again for this exchange. Release the unclaimed
          // read-only body even when cancellation rejects or never settles.
          cancelAbandonedGet(preflight.previous);
          hold('HOLD_STREAM_RECONNECT_ONLY');
        }
        if(priorReconnect) hold('HOLD_STREAM_NO_REPOST');
        // The host must ALSO enforce durable exchange idempotency across
        // tabs, reloads and devices. Never re-POST an ambiguous exchange.
        // A custom transport can ignore AbortSignal and keep post() pending
        // forever. Race that promise with STOP/timeout without retrying the
        // ambiguous exchange. A late response cannot authorize any UI delta.
        let onPostAbort;
        let posted;
        try{
          posted=await Promise.race([
            Promise.resolve().then(()=>ctrl.signal.aborted?null:transport.post(s,ctrl.signal))
              .then(res=>{
                if(ctrl.signal.aborted)cancelAbandonedPost(res);
                return {res};
              },()=>({postError:true})),
            new Promise(resolve=>{
              onPostAbort=()=>resolve({aborted:true});
              ctrl.signal.addEventListener('abort',onPostAbort,{once:true});
              if(ctrl.signal.aborted) onPostAbort();
            })
          ]);
        }finally{
          if(onPostAbort) ctrl.signal.removeEventListener('abort',onPostAbort);
        }
        if(posted.aborted||ctrl.signal.aborted){
          // The response can also settle just before the abort check.
          if(posted.res)cancelAbandonedPost(posted.res);
          return stopped();
        }
        if(posted.postError) hold('HOLD_STREAM_POST_OR_READ');
        const res=posted.res;
        let body,getReader,ok;
        try{
          body=readPostBody(res);
          if(!ctrl.signal.aborted)ok=res&&res.ok;
          if(!ctrl.signal.aborted)getReader=body&&body.getReader;
        }catch(_){
          cancelAbandonedPost(res);
          if(ctrl.signal.aborted)return stopped();
          hold('HOLD_STREAM_POST_RESPONSE');
        }
        if(ctrl.signal.aborted){
          cancelAbandonedPost(res);
          return stopped();
        }
        if(ok!==true||!body||typeof getReader!=='function'){
          cancelAbandonedPost(res);
          hold('HOLD_STREAM_POST_RESPONSE');
        }
        // Never silently replace malformed/incomplete UTF-8 with U+FFFD in
        // a model delta. An ambiguous stream must recover from canonical GET.
        // Even an HTTP-OK stream can throw while acquiring its reader. An
        // unclaimed body must be released before a fail-closed HOLD; never
        // retry the model POST or admit late SSE deltas/ACK.
        try{
          reader=getReader.call(body);
        }catch(_){
          cancelAbandonedPost(res);
          hold('HOLD_STREAM_POST_OR_READ');
        }
        const decoder=new TextDecoder('utf-8',{fatal:true});
        let buf='',swallowNextLF=false;
        while(true){
          if(ctrl.signal.aborted) return stopped();
          // reader.read() is not guaranteed to settle when a custom transport
          // ignores AbortSignal. Race the pending read against STOP/timeout;
          // never wait for stream completion, cancel(), or an old SSE frame.
          let onReadAbort;
          let outcome;
          try{
            outcome=await Promise.race([
              // STOP may win in the microtask gap before an external read.
              Promise.resolve().then(()=>ctrl.signal.aborted?null:reader.read())
                .then(part=>({part}),()=>({readError:true})),
              new Promise(resolve=>{
                onReadAbort=()=>resolve({aborted:true});
                ctrl.signal.addEventListener('abort',onReadAbort,{once:true});
                if(ctrl.signal.aborted) onReadAbort();
              })
            ]);
          }finally{
            if(onReadAbort) ctrl.signal.removeEventListener('abort',onReadAbort);
          }
          if(outcome.aborted||ctrl.signal.aborted) return stopped();
          if(outcome.readError) hold('HOLD_STREAM_POST_OR_READ');
          const part=outcome.part;
          // EventSource allows CR, LF, and CRLF. Dispatch a lone CR
          // immediately (without waiting for another chunk or EOF), but
          // swallow a following LF if CRLF was split between reads. Even
          // zero-character TextDecoder outputs must preserve this fence.
          // Read the result once: a changing done getter must not turn a
          // nonterminal chunk into EOF after its data was decoded. STOP can
          // also reenter while a custom reader exposes done or value.
          let done,value;
          try{
            if(!part||typeof part!=='object') hold('HOLD_STREAM_READ_RESULT');
            done=part.done;
            if(ctrl.signal.aborted)return stopped();
            if(typeof done!=='boolean')hold('HOLD_STREAM_READ_RESULT');
            if(!done)value=part.value;
            if(ctrl.signal.aborted)return stopped();
          }catch(err){
            if(ctrl.signal.aborted)return stopped();
            if(err instanceof HoldStream)throw err;
            hold('HOLD_STREAM_READ_RESULT');
          }
          let decoded;
          try{
            // EOF flush also rejects a truncated final multibyte sequence.
            decoded=done?decoder.decode():
              decoder.decode(value,{stream:true});
          }catch(_){hold('HOLD_STREAM_INVALID_UTF8');}
          if(swallowNextLF&&decoded.length){
            if(decoded[0]==='\n') decoded=decoded.slice(1);
            swallowNextLF=false;
          }
          if(decoded.endsWith('\r')) swallowNextLF=true;
          buf+=decoded.replace(/\r\n?/g,'\n');
          let e;
          while((e=buf.indexOf('\n\n'))>=0){
            // Bound EACH frame, not the aggregate transport read. One chunk
            // can legitimately contain many small SSE events totalling >64KiB.
            // STOP is still checked between those individual events.
            if(ctrl.signal.aborted) return stopped();
            if(e>MAX_SSE_FRAME_BYTES) hold('HOLD_STREAM_FRAME_TOO_LARGE');
            const frame=buf.slice(0,e);
            if(frameTooLarge(frame)) hold('HOLD_STREAM_FRAME_TOO_LARGE');
            buf=buf.slice(e+2);
            const lines=frame.split('\n');
            // EventSource removes at most ONE U+0020 from an event field.
            // A delta-like alias must not project a model token under a
            // normalized name. Duplicate event fields are ambiguous here.
            const eventFields=lines.filter(l=>l==='event'||l.startsWith('event:'));
            if(eventFields.length>1) hold('HOLD_STREAM_EVENT_TYPE');
            const rawEvent=eventFields.length===1?
              eventFields[0].slice(6):undefined;
            const event=rawEvent===undefined?undefined:
              rawEvent.startsWith(' ')?rawEvent.slice(1):rawEvent;
            if(event!==undefined&&event.trim()==='delta'&&event!=='delta')
              hold('HOLD_STREAM_EVENT_TYPE');
            // A colonless `data` line is a valid empty SSE data field.
            // Dropping it removes an intentional newline from multiline deltas.
            const data=lines.filter(l=>l==='data'||l.startsWith('data:'))
               // SSE removes at most one U+0020 separator after ':'. Literal
               // leading/trailing spaces are model output, not padding.
               .map(l=>l.slice(5).replace(/^ /,'')).join('\n');
            // Control/heartbeat frames can carry EventSource id resets even
            // when they contain no projected delta. Silently ignoring id:
            // (or a bare id) would discard a replay-cursor transition,
            // allowing later deltas to bypass exact-ID deduplication. NOX
            // therefore fails closed on empty/malformed or repeated IDs in
            // EVERY frame; valid control IDs and comments remain non-projecting.
            const ids=lines.filter(l=>l==='id'||l.startsWith('id:'));
            if(ids.length>1) hold('HOLD_STREAM_DELTA_EVENT_ID');
            const rawEventId=ids.length===1?ids[0].slice(3):undefined;
            const eventId=rawEventId===undefined?undefined:
              rawEventId.startsWith(' ')?rawEventId.slice(1):rawEventId;
            if(eventId!==undefined&&!ID.test(eventId))
              hold('HOLD_STREAM_DELTA_EVENT_ID');
            // B3's legacy display stream emits default JSON token events,
            // with no stable SSE id. Never silently consume it as a B1 stream
            // or invent replay IDs: the owner must select a compatible wire
            // adapter before POST. A mismatched response is GET-only HOLD.
            if((event===undefined||event==='message')&&data.startsWith('{')){
              let envelope;
              try{envelope=JSON.parse(data);}catch(_){}
              if(envelope&&envelope.type==='token'&&typeof envelope.t==='string')
                hold('HOLD_STREAM_WIRE_DELTA_ID_REQUIRED');
            }
            if(event==='delta'){
              // A named model delta must have its own stable server ID.
              // Do not delegate this wire invariant to the UI adapter.
              if(eventId===undefined) hold('HOLD_STREAM_DELTA_EVENT_ID');
              // Forward exact wire ID to the B1 abort-safe DOM replay fence.
              // UI handlers that await MUST check this signal immediately
              // before their actual DOM/state commit; this caller cannot undo
              // a UI effect already committed by an uncooperative adapter.
              // An adapter may leave onDelta() pending forever, even after
              // STOP/timeout. Its DOM commit contract must check AbortSignal
              // immediately before mutation. Race only the wait; a late
              // resolution cannot resume this stream loop or emit new frames.
              let onDeltaAbort,deltaOutcome;
              try{
                deltaOutcome=await Promise.race([
                  // Never invoke the external UI hook after a queued STOP.
                  Promise.resolve().then(()=>ctrl.signal.aborted?false:ui.onDelta(
                    s,data,ctrl.signal,eventId))
                    .then(()=>({ok:true}),()=>({uiError:true})),
                  new Promise(resolve=>{
                    onDeltaAbort=()=>resolve({aborted:true});
                    ctrl.signal.addEventListener('abort',onDeltaAbort,{once:true});
                    if(ctrl.signal.aborted) onDeltaAbort();
                  })
                ]);
              }finally{
                if(onDeltaAbort)
                  ctrl.signal.removeEventListener('abort',onDeltaAbort);
              }
              if(deltaOutcome.aborted||ctrl.signal.aborted) return stopped();
              if(deltaOutcome.uiError) hold('HOLD_STREAM_POST_OR_READ');
            }
            // Terminal SSE frames are deliberately NOT sufficient to ACK;
            // only a separately authenticated durable readback is accepted.
          }
          // The unframed tail, unlike completed events, must be bounded.
          // A single unterminated oversized event is not a valid stream.
          // One trailing LF may be the first half of the blank separator.
          // Exclude only that pending separator candidate from the tail budget.
          // A completed frame is still checked in full; EOF with a partial
          // separator remains HOLD_TRUNCATED_SSE. Never allow a second POST.
          const tail=buf.endsWith('\n')?buf.slice(0,-1):buf;
          if(frameTooLarge(tail)) hold('HOLD_STREAM_FRAME_TOO_LARGE');
          // A clean EOF cannot finalize a half-written SSE event. EventSource
          // discards unterminated data; NOX must surface uncertain delivery as
          // HOLD and recover by canonical GET, NEVER re-POST the model turn.
          // Trailing blank separators contain no event and are harmless.
          if(done){
            if(/[^\n]/.test(buf)) hold('HOLD_STREAM_TRUNCATED_SSE');
            streamComplete=true;
            break;
          }
        }
        if(ctrl.signal.aborted) return stopped();
        return 'STREAM_ENDED_READBACK_REQUIRED';
      }catch(err){
        if(ctrl.signal.aborted) return stopped();
        if(err instanceof HoldStream) throw err;
        hold('HOLD_STREAM_POST_OR_READ');
      }finally{
        clearTimeout(timer);
        active.delete(k);
        // STOP or stream HOLD can happen while awaiting an uncooperative UI
        // projection (not only inside reader.read()). Release the underlying
        // SSE connection on *every* non-EOF exit without awaiting cancel().
        // A hung cancel must never block STOP, nor permit another model POST.
        if(reader&&!streamComplete){
          try{
            const cancellation=reader.cancel();
            if(cancellation&&typeof cancellation.catch==='function')
              cancellation.catch(()=>{});
          }catch(_){}
        }
      }
    }
    function stop(raw){
      const k=key(snap(raw));
      const streamCtrl=active.get(k),reconnectCtrl=reconnectControllers.get(k);
      if(!streamCtrl&&!reconnectCtrl) return false;
      // STOP is scoped to one exchange, including a pending readback,
      // UI terminal projection, local ACK reservation or canonical GET.
      // It never starts a new model POST and cannot undo an ACK already sent.
      if(streamCtrl) streamCtrl.abort();
      if(reconnectCtrl) reconnectCtrl.abort();
      return true;
    }
    // A hung or uncooperative read-only GET/witness must not pin reconnect()
    // forever. Late resolutions have no continuation to UI/ACK after timeout.
    // Both supplied functions MUST be side-effect free: never put model POST,
    // DOM projection or ACK inside either untrusted callback.
    function boundedRead(thunk,code,deadlineMs=reconnectReadTimeoutMs,signal=null){
      if(signal&&signal.aborted) hold('HOLD_STREAM_RECONNECT_STOPPED');
      let timer,onAbort;
      const tasks=[
        Promise.resolve().then(()=>{
          if(signal&&signal.aborted) hold('HOLD_STREAM_RECONNECT_STOPPED');
          return thunk();
        }),
        new Promise((_,reject)=>{
          timer=setTimeout(()=>reject(new HoldStream(code)),deadlineMs);
        })
      ];
      if(signal) tasks.push(new Promise((_,reject)=>{
        onAbort=()=>reject(new HoldStream('HOLD_STREAM_RECONNECT_STOPPED'));
        signal.addEventListener('abort',onAbort,{once:true});
        if(signal.aborted) onAbort();
      }));
      return Promise.race(tasks).then(value=>{
        // Even a just-settled callback must not resume UI/ACK after STOP.
        if(signal&&signal.aborted) hold('HOLD_STREAM_RECONNECT_STOPPED');
        return value;
      }).finally(()=>{
        clearTimeout(timer);
        if(onAbort) signal.removeEventListener('abort',onAbort);
      });
    }
    // For a read-only GET, racing the UI await is insufficient: an aborted
    // or timed-out request can keep the browser's network socket alive.
    // Forward a per-GET AbortSignal to cooperative transports, and abort it
    // when STOP, deadline, or transport failure wins. Never repeat a POST.
    async function boundedGet(thunk,code,deadlineMs,signal){
      const controller=new AbortController();
      let completed=false,abandoned=false,received=null,discarded=false;
      // STOP can win after a GET resolves but before boundedRead settles.
      // The late callback and finally must share ONE disposal fence, so a
      // previously delivered response is never leaked or double-canceled.
      const discardIfAbandoned=value=>{
        if(discarded||!value)return;
        if(abandoned||controller.signal.aborted||(signal&&signal.aborted)){
          discarded=true;
          cancelAbandonedGet(value); // nonblocking even for hung cancel()
        }
      };
      try{
        const answer=await boundedRead(
          ()=>Promise.resolve().then(()=>thunk(controller.signal))
            .then(value=>{
              received=value;
              discardIfAbandoned(value);
              return value;
            }),code,deadlineMs,signal);
        completed=true; // ownership now belongs to reconnectOnce()
        return answer;
      }finally{
        if(!completed){
          abandoned=true;
          controller.abort();
          discardIfAbandoned(received); // resolved-before-STOP race
        }
      }
    }
    // One in-flight GET/readback + UI projection + ACK per exchange per tab.
    // Coalesce concurrent reconnect calls; after a failure, allow readback-only
    // recovery. NEVER start another model POST for an uncertain exchange.
    async function reconnectOnce(s,signal){
      let packet,witness;
      // Once the GET has returned, the witness bridge can reject, hang,
      // or lose STOP. The pending packet may still own an OPEN readback
      // response; a read timeout no longer aborts that already-finished GET.
      // Release ONLY rejected/abandoned packets; a verified witness retains
      // ownership. Never block recovery on body.cancel().
      let discardedReadback=false;
      const discardReadback=()=>{
        if(discardedReadback||!packet)return;
        discardedReadback=true;
        cancelAbandonedGet(packet);
      };
      try{
        packet=await boundedGet(getSignal=>transport.readback(s,getSignal),
          'HOLD_STREAM_READBACK_TIMEOUT',reconnectReadTimeoutMs,signal); // GET only; never model POST
        witness=await boundedRead(()=>bridge.acceptTerminal(packet,s,host),
          'HOLD_STREAM_WITNESS_TIMEOUT',reconnectReadTimeoutMs,signal); // verification only; no side effects
      }catch(err){
        discardReadback();
        if(err&&typeof err.code==='string') throw err;
        hold('HOLD_STREAM_READBACK');
      }
      // Snapshot BEFORE validation, so changing or throwing getters cannot
      // substitute a different event/cursor after approval. Preserve the
      // enumerable witness contract, but never expose the original object.
      try{
        if(!witness||typeof witness!=='object'||Array.isArray(witness))
          hold('HOLD_STREAM_UNSAFE_WITNESS');
        witness=Object.freeze({...witness});
        if(witness.safe_to_ack!==true||witness.model_post!==false||
           witness.exchange_id!==s.exchange_id||witness.conversation_id!==s.conversation_id||
           typeof witness.projection_event_id!=='string'||
           !ID.test(witness.projection_event_id)||
           typeof witness.ack_cursor!=='string'||
           witness.ack_cursor.length<1||witness.ack_cursor.length>2048||
           /[\x00-\x1f\x7f]/.test(witness.ack_cursor))
          hold('HOLD_STREAM_UNSAFE_WITNESS');
      }catch(_){
        discardReadback();
        if(signal.aborted) hold('HOLD_STREAM_RECONNECT_STOPPED');
        hold('HOLD_STREAM_UNSAFE_WITNESS');
      }
      // A getter can synchronously trigger STOP while copying the witness.
      if(signal.aborted){
        discardReadback();
        hold('HOLD_STREAM_RECONNECT_STOPPED');
      }
      // ACK must follow a *successful* idempotent UI projection. A partially
      // written UI may throw; retry must use the same event_id without POST.
      // A hung UI projection must not pin reconnect forever or authorize ACK.
      // Retrying remains GET-only and uses the SAME immutable event ID; the
      // UI adapter MUST implement an idempotent upsert and fence late commits.
      // This timeout cannot undo arbitrary uncooperative UI side effects.
      // The abort-safe DOM adapter already accepts a signal, but previous
      // reconnect timeouts did not supply one: a late beforeCommit could
      // mutate the DOM after HOLD. Fence both the await and the DOM commit.
      const projectionCtrl=new AbortController();
      let projected,proof;
      try{
        const candidate=witness.canonical_assistant_text;
        if(!candidate||typeof candidate!=='object'||Array.isArray(candidate))
          hold('HOLD_STREAM_CANONICAL_TEXT');
        proof=Object.freeze({...candidate});
        const pin=x=>typeof x==='string'&&/^[0-9a-f]{64}$/.test(x)&&new Set(x).size>1;
        if(proof.schema!=='NOX_B5_CANONICAL_ASSISTANT_TEXT_V1'||
           proof.conversation_id!==s.conversation_id||proof.exchange_id!==s.exchange_id||
           ![2,3].includes(proof.sequence)||typeof proof.assistant_text!=='string'||!proof.assistant_text||
           !['physical_dialog_id','request_id','attempt_id','s03_dialog_id','s03_session_id',
             's03_event_id','s03_turn_id','assistant_message_id'].every(k=>
                typeof proof[k]==='string'&&proof[k].length>0&&proof[k].length<=160)||
           !['served_sha256','answer_sha256','writer_sha256','readback_sha256','link_sha256'].every(k=>pin(proof[k]))||
           new Set([proof.writer_sha256,proof.readback_sha256,proof.link_sha256]).size!==3)
          hold('HOLD_STREAM_CANONICAL_TEXT');
        // The B5 projection itself explicitly has no authentication/ACK
        // authority. The independent owner verifier must bind the exact
        // frozen projection to this scope, terminal event and build.
        const approved=await boundedRead(
          ()=>host.verifyCanonicalText(proof,s,witness),
          'HOLD_STREAM_CANONICAL_TEXT_TIMEOUT',reconnectReadTimeoutMs,signal);
        if(approved!==true||signal.aborted) hold('HOLD_STREAM_CANONICAL_TEXT');
      }catch(err){
        discardReadback();
        if(err&&typeof err.code==='string')throw err;
        hold('HOLD_STREAM_CANONICAL_TEXT');
      }
      try{
        projected=await boundedRead(
          ()=>ui.upsertTerminal(s,witness.projection_event_id,projectionCtrl.signal,proof),
          'HOLD_STREAM_UI_PROJECTION_TIMEOUT',uiProjectionTimeoutMs,signal);
      }catch(err){
        projectionCtrl.abort();
        // A failed, timed-out or stopped DOM upsert has NOT assumed ownership
        // of the read-only terminal GET. Release its body before GET-only retry.
        discardReadback();
        if(err&&(err.code==='HOLD_STREAM_UI_PROJECTION_TIMEOUT'||
          err.code==='HOLD_STREAM_RECONNECT_STOPPED')) throw err;
        hold('HOLD_STREAM_UI_PROJECTION');
      }
      // Only an explicit positive DOM commit witness may precede ACK. A
      // missing return (undefined), null, string, or numeric truthy value
      // is not proof that the terminal row was actually projected.
      if(projected!==true){
        discardReadback();
        hold('HOLD_STREAM_UI_NOT_CONFIRMED');
      }
      let observed=false,recheckPreAck=null;
      function assertCurrentPreAck(){
        if(!observePreAck)return;
        if(observed!==true||typeof recheckPreAck!=='function'||recheckPreAck()!==true)
          hold('HOLD_STREAM_PREACK_OBSERVATION');
        if(signal.aborted)hold('HOLD_STREAM_RECONNECT_STOPPED');
      }
      if(observePreAck){
        const observeCtrl=new AbortController();
        try{
          observed=await boundedRead(()=>observePreAck(s,proof,witness,observeCtrl.signal,guard=>{
            if(observeCtrl.signal.aborted||recheckPreAck!==null||typeof guard!=='function')
              hold('HOLD_STREAM_PREACK_OBSERVATION');
            recheckPreAck=guard;
          }),
            'HOLD_STREAM_PREACK_OBSERVATION_TIMEOUT',uiProjectionTimeoutMs,signal);
          if(observed!==true&&observed!==false)hold('HOLD_STREAM_PREACK_OBSERVATION');
        }catch(err){discardReadback();if(err&&err.code)throw err;hold('HOLD_STREAM_PREACK_OBSERVATION');}
        finally{observeCtrl.abort();}
      }
      // Origin-local, cross-tab durable fence is opt-in. RESERVE and SENDING
      // must commit in IndexedDB BEFORE network ACK. An uncertain ACK is never
      // sent again after reload; recovery requires an independent server receipt.
      // LOCAL_DEDUP_ONLY and a successful network ACK are never server proof.
      // Only a fresh GET + externally trusted native owner/signature/S03
      // verifier may elevate this source projection to canonical completion.
      // Synthetic callback=true in a test is NOT independent native evidence.
      async function canonicalCompletion(){
        // A previously signed ACK is not proof of a NEW canonical read. Require
        // a per-GET cryptographic challenge echoed in a short-lived server
        // attestation, and an independently trusted verifier that checks the
        // signature BINDING the nonce + validity interval to that ACK.
        if(!globalThis.crypto||typeof globalThis.crypto.randomUUID!=='function')
          hold('HOLD_STREAM_FRESHNESS_CRYPTO');
        const challenge=Object.freeze({
          request_nonce:globalThis.crypto.randomUUID(),
          requested_at_ms:Date.now(),freshness_ms:canonicalFreshnessMs
        });
        let ack,freshVerified=false;
        // Second verifier success is not yet durable ACK-gate confirmation.
        // Until the gate envelope is accepted, a GET body may be unclaimed.
        // Snapshot the verifier-approved ID before an untrusted gate settles.
        let verifiedReceipt=null,verifiedAckId=null,verifiedBodyDiscarded=false;
        // Pin canonical GET identity before either external verifier can await
        // or mutate the receipt object. A later ACK envelope must not certify
        // a different nonce/expiry/ACK ID than the signed GET supplied.
        let signedIdentity=null,signedReceipt=null;
        // The cross-tab gate is external. A malicious/buggy gate may call a
        // read/verify callback twice, swallow its rejection, or invoke it after
        // returning a forged ACK envelope. Each callback is single-use.
        // Invalidation is sticky even if that external gate catches the HOLD.
        let canonicalReadUsed=false,canonicalVerifyUsed=false;
        let canonicalCallbacksInvalid=false,canonicalGateClosed=false;
        let signedBodyDisposed=false;
        const discardSignedBody=()=>{
          if(signedBodyDisposed||!signedReceipt)return;
          signedBodyDisposed=true;
          cancelAbandonedGet(signedReceipt); // once, nonblocking
        };
        const captureSignedIdentity=receipt=>{
          try{
            const fields=Object.freeze({
              request_nonce:receipt.request_nonce,
              issued_at_ms:receipt.issued_at_ms,
              expires_at_ms:receipt.expires_at_ms,
              ack_id:receipt.ack_id
            });
            if(typeof fields.ack_id!=='string'||!ID.test(fields.ack_id))
              hold('HOLD_STREAM_RECEIPT_IDENTITY');
            return fields;
          }catch(err){
            if(err&&err.code==='HOLD_STREAM_RECEIPT_IDENTITY')throw err;
            hold('HOLD_STREAM_RECEIPT_IDENTITY');
          }
        };
        const sameSignedIdentity=receipt=>{
          if(!signedIdentity)return false;
          try{
            return receipt.request_nonce===signedIdentity.request_nonce&&
              receipt.issued_at_ms===signedIdentity.issued_at_ms&&
              receipt.expires_at_ms===signedIdentity.expires_at_ms&&
              receipt.ack_id===signedIdentity.ack_id;
          }catch(_){return false;}
        };
        // Durable cross-tab ACK gates legitimately pass a normalized signed
        // proof to their second verifier: it may omit nonce/time/body fields.
        // Compare the shared ACK ID, any present freshness fields, AND the
        // original raw signed GET still pinned by this client. Do not require
        // the gate's normalized receipt to be the transport's raw object.
        const sameCanonicalProjection=proof=>{
          if(!proof||typeof proof!=='object'||Array.isArray(proof)||
             !signedReceipt||canonicalCallbacksInvalid||!sameSignedIdentity(signedReceipt))return false;
          try{
            return proof.ack_id===signedIdentity.ack_id&&
              (proof.request_nonce===undefined||
               proof.request_nonce===signedIdentity.request_nonce)&&
              (proof.issued_at_ms===undefined||
               proof.issued_at_ms===signedIdentity.issued_at_ms)&&
              (proof.expires_at_ms===undefined||
               proof.expires_at_ms===signedIdentity.expires_at_ms);
          }catch(_){return false;}
        };
        const discardVerifiedBody=()=>{
          if(verifiedBodyDiscarded||!verifiedReceipt)return;
          verifiedBodyDiscarded=true;
          discardSignedBody(); // single shared signed-GET disposal fence
        };
        try {
          // A signed canonical ACK read still involves external GET and
           // independent verification. Bound the whole trusted wait so a
           // hung GET/verifier cannot pin reconnect forever. ackGate must
           // independently fence late side effects with its durable CAS.
           ack=await boundedGet(
             lifecycleSignal=>{
              // STOP/deadline can win AFTER both verifiers succeed but while
              // durable ACK-gate CAS is still stalled.
              const onGateAbort=()=>discardVerifiedBody();
              lifecycleSignal.addEventListener('abort',onGateAbort,{once:true});
              return Promise.resolve().then(()=>ackGate.requireCanonicalAck(
                s,witness.projection_event_id,
            witness.ack_cursor,
            async expected=>{
              if(canonicalGateClosed)
                hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
              if(canonicalReadUsed){
                canonicalCallbacksInvalid=true;
                discardSignedBody();
                hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
              }
              canonicalReadUsed=true;
              // readCanonicalAck MUST be a no-store, authenticated GET. It
              // MUST forward the challenge to the server; never a model POST.
              // The canonical receipt GET must be physically cancellable; a
              // timed-out or stopped late reply cannot resume gate CAS.
              if(lifecycleSignal.aborted||signal.aborted)
                hold('HOLD_STREAM_RECONNECT_STOPPED');
              // A canonical receipt GET can ignore AbortSignal and deliver
              // an OPEN body after STOP/deadline. The enclosing gate Promise
              // may never resolve to boundedGet, so dispose here at the
              // transport boundary. Never resume verifier/CAS or model POST.
              // A rejected, malformed or stalled signed GET still holds an
              // HTTP response body. Keep one disposal fence shared by the
              // abort listener and the synchronous verifier rejection path.
              // Successful receipts remain owned by the canonical ACK gate.
              let receipt=null,discardedReceipt=false;
              const discardReceipt=value=>{
                if(discardedReceipt)return;
                discardedReceipt=true;
                cancelAbandonedGet(value); // never await rejected/hung cancel()
              };
              const onReceiptAbort=()=>{
                if(receipt){
                  if(signedReceipt===receipt)discardSignedBody();
                  else discardReceipt(receipt);
                }
              };
              lifecycleSignal.addEventListener('abort',onReceiptAbort,{once:true});
              try{
                receipt=await Promise.resolve(transport.readCanonicalAck(
                  s,expected,challenge,lifecycleSignal)).then(value=>{
                    // Non-cooperative transport may settle after deadline/STOP.
                    if(lifecycleSignal.aborted||signal.aborted)discardReceipt(value);
                    return value;
                  });
                if(lifecycleSignal.aborted||signal.aborted)
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                // The gate may have returned before this GET settled. Its
                // terminal HOLD cannot transfer ownership of a late body.
                if(canonicalGateClosed||canonicalCallbacksInvalid){
                  discardReceipt(receipt);
                  hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
                }
                const now=Date.now();
                if(!receipt||typeof receipt!=='object'||Array.isArray(receipt))
                  hold('HOLD_STREAM_RECEIPT_FRESHNESS');
                signedIdentity=captureSignedIdentity(receipt);
                // An untrusted receipt getter may synchronously trigger STOP
                // while its identity is captured. Fence that reentrant abort
                // BEFORE giving this GET to the freshness verifier: otherwise
                // a host callback runs after STOP and can double-own the body.
                if(lifecycleSignal.aborted||signal.aborted){
                  discardReceipt(receipt); // shared once-only abort disposal
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                }
                signedReceipt=receipt;
                if(canonicalCallbacksInvalid){
                  discardSignedBody();
                  hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
                }
                if(signedIdentity.request_nonce!==challenge.request_nonce||
                   !Number.isSafeInteger(signedIdentity.issued_at_ms)||
                   !Number.isSafeInteger(signedIdentity.expires_at_ms)||
                   signedIdentity.issued_at_ms<challenge.requested_at_ms-5000||
                   signedIdentity.issued_at_ms>now+5000||
                   signedIdentity.expires_at_ms<=now||
                   signedIdentity.expires_at_ms-signedIdentity.issued_at_ms>canonicalFreshnessMs)
                  hold('HOLD_STREAM_RECEIPT_FRESHNESS');
                // The host verifier must attest scope, nonce, CAS and S03;
                // if it fails or hangs, the receipt body is not acknowledged.
                const trusted=await host.verifyFreshCanonicalAck(
                  receipt,expected,s,challenge);
                if(lifecycleSignal.aborted||signal.aborted)
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                if(canonicalGateClosed||canonicalCallbacksInvalid){
                  discardSignedBody();
                  hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
                }
                if(trusted!==true)hold('HOLD_STREAM_FRESHNESS_UNVERIFIED');
                const unchanged=sameSignedIdentity(receipt);
                // Getters are untrusted: STOP can occur while comparing the
                // pinned receipt after a verifier has returned.
                if(lifecycleSignal.aborted||signal.aborted)
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                if(!unchanged)hold('HOLD_STREAM_RECEIPT_MUTATED');
                freshVerified=true;
                return receipt;
              }catch(err){
                // Invalid/failing receipts must release the unclaimed socket.
                // After timeout this shares the same once-only abort fence.
                if(receipt){
                  if(signedReceipt===receipt)discardSignedBody();
                  else discardReceipt(receipt);
                }
                throw err;
              }finally{
                lifecycleSignal.removeEventListener('abort',onReceiptAbort);
              }
            },
            async (receipt,expected)=>{
              if(canonicalGateClosed)
                hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
              if(canonicalVerifyUsed){
                canonicalCallbacksInvalid=true;
                discardSignedBody();
                hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
              }
              canonicalVerifyUsed=true;
              // Freshness is only the first proof. A rejected, throwing,
              // stalled or stopped second verifier can abandon the same
              // canonical GET response body. Close it once without awaiting.
              // A fully verified response remains owned by its caller.
              let discarded=false;
              const discard=()=>{
                if(discarded)return;
                discarded=true;
                if(signedReceipt)discardSignedBody();
                else cancelAbandonedGet(receipt);
              };
              const onAbort=()=>discard();
              lifecycleSignal.addEventListener('abort',onAbort,{once:true});
              try{
                if(lifecycleSignal.aborted||signal.aborted){
                  discard();
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                }
                if(canonicalCallbacksInvalid){
                  discard();
                  hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
                }
                const canonicalMatches=sameCanonicalProjection(receipt);
                // A synchronous signed-field getter may STOP during the
                // identity comparison. No host verifier after such STOP.
                if(lifecycleSignal.aborted||signal.aborted){
                  discard();
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                }
                if(!canonicalMatches){
                  discard();
                  hold('HOLD_STREAM_RECEIPT_MUTATED');
                }
                let trusted;
                try{
                  trusted=await host.verifyCanonicalAck(
                    receipt,expected,s,lifecycleSignal);
                }catch(err){
                  discard();
                  throw err;
                }
                if(lifecycleSignal.aborted||signal.aborted){
                  discard();
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                }
                // External ACK gate can settle before a verifier Promise.
                // Never publish late verifiedAckId into a closed gate.
                if(canonicalGateClosed||canonicalCallbacksInvalid){
                  discard();
                  hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
                }
                if(trusted!==true)discard();
                else{
                  // An untrusted normalized proof getter can invoke STOP on
                  // the SECOND comparison, after the host verifier returned.
                  // Never transfer verified GET ownership after that abort.
                  const stillMatches=sameCanonicalProjection(receipt);
                  if(lifecycleSignal.aborted||signal.aborted){
                    discard();
                    hold('HOLD_STREAM_RECONNECT_STOPPED');
                  }
                  if(canonicalGateClosed||canonicalCallbacksInvalid){
                    discard();
                    hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
                  }
                  if(!stillMatches){
                    discard();
                    hold('HOLD_STREAM_RECEIPT_MUTATED');
                  }
                  verifiedReceipt=signedReceipt;
                  verifiedAckId=signedIdentity.ack_id;
                }
                return trusted;
              }finally{
                lifecycleSignal.removeEventListener('abort',onAbort);
              }
            },lifecycleSignal)).finally(()=>{
                lifecycleSignal.removeEventListener('abort',onGateAbort);
              });
            },
             'HOLD_STREAM_CANONICAL_ACK_TIMEOUT',canonicalAckTimeoutMs,signal);
        }catch(err){
          discardSignedBody();
          discardVerifiedBody();
          if(err&&typeof err.code==='string') throw err;
          hold('HOLD_STREAM_CANONICAL_ACK');
        }finally{
          canonicalGateClosed=true;
        }
        if(canonicalCallbacksInvalid){
          discardSignedBody();
          discardReadback();
          hold('HOLD_STREAM_CANONICAL_CALLBACK_REPLAY');
        }
        if(!freshVerified){
          discardVerifiedBody();
          hold('HOLD_STREAM_FRESHNESS_UNVERIFIED');
        }
        // A durable gate can return an object with throwing or changing
        // property getters. Read each envelope field exactly once, within
        // the same failure fence that disposes the signed canonical GET.
        // A getter exception must not strand that response body or revive
        // the exchange on a later read. Never repeat network ACK/model POST.
        let canonicalStatus,canonicalAuthority,canonicalAckId;
        let validEnvelope=false;
        try{
          if(ack&&typeof ack==='object'&&!Array.isArray(ack)){
            canonicalStatus=ack.status;
            canonicalAuthority=ack.authority;
            canonicalAckId=ack.ack_id;
            validEnvelope=canonicalStatus==='CANONICAL_ACK_CONFIRMED'&&
              canonicalAuthority==='VERIFIER_CALLBACK_APPROVED'&&
              typeof canonicalAckId==='string'&&ID.test(canonicalAckId)&&
              typeof verifiedAckId==='string'&&ID.test(verifiedAckId)&&
              canonicalAckId===verifiedAckId;
          }
        }catch(_){validEnvelope=false;}
        // A gate envelope is untrusted too: its synchronous status/authority
        // getter can STOP after boundedGet() has already resolved. Recheck
        // the outer STOP before accepting the ACK or retaining either GET.
        if(signal.aborted){
          discardVerifiedBody();
          hold('HOLD_STREAM_RECONNECT_STOPPED');
        }
        if(!validEnvelope){
          // No canonical proof: close its verified GET body once, then the
          // original terminal readback GET at the enclosing HOLD boundary.
          discardVerifiedBody();
          hold('HOLD_STREAM_CANONICAL_ACK');
        }
        return Object.freeze({...witness,canonical_ack_status:canonicalStatus,
          canonical_ack_id:canonicalAckId});
      }
      // A failed canonical proof leaves the original terminal readback GET
      // unclaimed even if the separate signed-ACK GET was disposed. Release
      // only on failure; successful verification retains its ownership.
      async function completeCanonicalOrDispose(){
        try{ return await canonicalCompletion(); }
        catch(err){
          discardReadback(); // once-only, nonblocking, GET only
          throw err;
        }
      }
      let grant=null;
      if(ackGate){
        try{
          grant=await boundedRead(
            ()=>ackGate.reserve(s,witness.projection_event_id,witness.ack_cursor),
            'HOLD_STREAM_ACK_RESERVE_TIMEOUT',reconnectReadTimeoutMs,signal);
        }catch(err){
          // An uncertain SENDING ACK must NEVER be retransmitted: GET-only
          // readback, with the original event/cursor and CAS proof.
          if(err&&err.code==='HOLD_CROSSTAB_ACK_UNCERTAIN')
            return completeCanonicalOrDispose();
          // The reservation has not accepted ownership of the terminal
          // readback GET. A rejected, stopped or timed-out reserve must
          // release that open body once without waiting on cancel().
          discardReadback();
          if(err&&typeof err.code==='string') throw err;
          hold('HOLD_STREAM_ACK_GATE');
        }
        // An external durable gate can return null, a malformed grant or
        // throw from a status accessor. Normalize every such failure to HOLD
        // BEFORE beginSend or the first network ACK. Read status only once:
        // a changing accessor must not switch this turn between paths.
        let reservationStatus;
        try{
          if(!grant||typeof grant!=='object'||Array.isArray(grant))
            hold('HOLD_STREAM_ACK_GATE');
          reservationStatus=grant.status;
        }catch(_){
          discardReadback();
          hold('HOLD_STREAM_ACK_GATE');
        }
        if(reservationStatus==='ALREADY_ACKED') return completeCanonicalOrDispose();
        if(reservationStatus!=='RESERVED'){
          discardReadback();
          hold('HOLD_STREAM_ACK_GATE');
        }
        if(observePreAck&&observed!==true){discardReadback();hold('HOLD_STREAM_PREACK_OBSERVATION');}
        try{
          const sendReceipt=await boundedRead(()=>{assertCurrentPreAck();return ackGate.beginSend(grant);},
            'HOLD_STREAM_ACK_BEGIN_TIMEOUT',reconnectReadTimeoutMs,signal);
          // BeginSend is a durable CAS boundary, not an advisory response.
          // Native IndexedDB gate returns 'SENDING'; other adapters may
          // commit with true or resolve void. Reject all other results
          // before the network ACK escapes, including false and malformed.
          if(sendReceipt!=='SENDING' &&
             sendReceipt!==true && sendReceipt!==undefined){
            // beginSend rejected the durable transition: nobody owns the
            // terminal readback GET. Release it before any network ACK.
            discardReadback();
            hold('HOLD_STREAM_ACK_GATE');
          }
        }
        catch(err){
          // Rejection, STOP or timeout can abandon this same GET body.
          // The disposal fence makes the explicit-HOLD path idempotent.
          discardReadback();
          if(err&&typeof err.code==='string') throw err;
          hold('HOLD_STREAM_ACK_GATE');
        }
      }
      // Strict acknowledgment is an opt-in transport contract. Legacy ACK
      // callbacks may fulfill with undefined after an HTTP success, so enabling
      // strict true by default would break existing native adapters.
      // In strict mode without a durable gate, any ACK attempt is ambiguous
      // after reconnect. Fence same-tab replays before a second network ACK.
      // Cross-tab/reload safety STILL requires the supplied durable ackGate.
      if(strictAckNoReplay&&!ackGate){
        const attemptKey=key(s);
        if(ackAttempted.has(attemptKey)){
          // A duplicate strict ACK is fenced before any network side effect.
          // Its new GET response is unclaimed; close only that body.
          discardReadback();
          hold('HOLD_STREAM_ACK_UNCERTAIN_GET_ONLY');
        }
        ackAttempted.add(attemptKey);
      }
      try{
        // ACK may be accepted by the server even if its Promise never
        // settles. Bound this wait, but DO NOT cancel/retry a potentially
        // committed ACK: ackGate remains durably SENDING. Subsequent
        // reconnect uses canonical GET-only verification of that attempt.
        const acked=await boundedRead(
          ()=>{const send=transport.ack;assertCurrentPreAck();return send.call(transport,s,witness.ack_cursor);},
          'HOLD_STREAM_ACK_SEND_TIMEOUT',ackSendTimeoutMs,signal);
        // Strict opt-in transports must explicitly attest true. Legacy
        // transports preserve their prior void-success contract; only false
        // means explicitly unconfirmed. Neither result is canonical proof.
        if(strictAckNoReplay ? acked!==true : acked===false){
          // Explicitly unconfirmed ACK leaves this terminal readback GET
          // unclaimed. Disposing it does NOT retry or cancel the ACK.
          discardReadback();
          hold('HOLD_STREAM_ACK_UNCONFIRMED');
        }
        // Leave IndexedDB SENDING until a signed canonical GET proves ACKED.
        // A local confirm() would create ACKED without a server proof digest
        // and permanently block requireCanonicalAck() as unverified.
      }catch(err){
        // ACK may have committed remotely; never retry or abort the ACK.
        // Only the abandoned terminal *GET* body is released once and
        // nonblocking on rejection, timeout, STOP and explicit HOLD.
        discardReadback();
        if(err&&(err.code==='HOLD_STREAM_ACK_SEND_TIMEOUT'||
          err.code==='HOLD_STREAM_RECONNECT_STOPPED'||err.code==='HOLD_B1_PREACK_OBSERVATION'||
          err.code==='HOLD_STREAM_PREACK_OBSERVATION')) throw err;
        hold('HOLD_STREAM_ACK_UNCONFIRMED');
      }
      return ackGate?completeCanonicalOrDispose():witness;
    }
    function reconnect(raw){
      const s=snap(raw),k=key(s);
      if(active.has(k)) hold('HOLD_STREAM_ACTIVE_POST');
      const pending=reconnecting.get(k);
      if(pending) return pending;
      // A readback-only reconnect means this exchange may already exist on
      // the server, even when storage has not committed yet. Fence begin()
      // synchronously before any GET/await; STOP, timeout or GET failure must
      // never grant permission for another model POST of this exchange.
      reconnectSeen.add(k);
      const ctrl=new AbortController();
      const attempt=reconnectOnce(s,ctrl.signal);
      reconnecting.set(k,attempt);
      reconnectControllers.set(k,ctrl);
      const clear=()=>{
        if(reconnecting.get(k)===attempt){
          reconnecting.delete(k);
          reconnectControllers.delete(k);
        }
      };
      attempt.then(clear,clear);
      return attempt;
    }
    return Object.freeze({begin,stop,reconnect});
  }
  return Object.freeze({createClient,HoldStream});
});
;
/* NOX B1 opt-in assembly: real B1 SSE client -> abort-safe DOM projector.
 * This is source-only; the host must supply authenticated owner, ACK and S03
 * witnesses. The binding performs no fetch, POST, model or storage operation.
 * It is not itself native attestation or production installation.
 */
(function(root,factory){
  'use strict';
  const api=factory(root);
  if(typeof module==='object' && module.exports) module.exports=api;
  else root.NOXB1SseUiBinding=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(root){
  'use strict';
  class BindingHold extends Error {
    constructor(code){ super(code); this.name='BindingHold'; this.code=code; }
  }
  function hold(code){ throw new BindingHold(code); }
  function bind({container,transport,host,bridge,ackGate,beforeCommit,
    terminalTimeoutMs,deltaPrecommitTimeoutMs,
    timeoutMs,canonicalFreshnessMs,reconnectReadTimeoutMs,
    uiProjectionTimeoutMs,ackSendTimeoutMs,canonicalAckTimeoutMs}={}){
    // A UI completion is never a server ACK. Fail closed instead of silently
    // using createClient's deliberately opt-in, local-only ACK fallback.
    if(!ackGate || typeof ackGate.reserve!=='function' ||
       typeof ackGate.beginSend!=='function' ||
       typeof ackGate.requireCanonicalAck!=='function' ||
       typeof ackGate.confirm!=='function')
      hold('HOLD_B1_BINDING_CANONICAL_ACK_GATE_REQUIRED');
    if(!host || typeof host.verifyCanonicalAck!=='function' ||
       typeof host.verifyFreshCanonicalAck!=='function')
      hold('HOLD_B1_BINDING_TRUSTED_VERIFIER_REQUIRED');
    const dom=root.NOXB1AbortSafeUI;
    const stream=root.NOXB1StreamReconnect;
    if(!dom || typeof dom.createUiAdapter!=='function' ||
       !stream || typeof stream.createClient!=='function')
      hold('HOLD_B1_BINDING_DEPENDENCY');
    const options={container};
    if(beforeCommit!==undefined) options.beforeCommit=beforeCommit;
    // UI precommit and terminal deadlines must reach the abort-safe adapter.
    // Validation is performed by createUiAdapter before a stream or GET starts.
    if(terminalTimeoutMs!==undefined)
      options.terminalTimeoutMs=terminalTimeoutMs;
    if(deltaPrecommitTimeoutMs!==undefined)
      options.deltaPrecommitTimeoutMs=deltaPrecommitTimeoutMs;
    const ui=dom.createUiAdapter(options);
    const observer=root.NOXB1PreAckObserver;
    if(!observer)hold('HOLD_B1_BINDING_PREACK_OBSERVER_REQUIRED');
    const observePreAck=observer.create({container,host});
    const config={transport,host,bridge,ui,ackGate,observePreAck};
    if(timeoutMs!==undefined) config.timeoutMs=timeoutMs;
    if(canonicalFreshnessMs!==undefined)
      config.canonicalFreshnessMs=canonicalFreshnessMs;
    // Pass native caller deadlines to the one SSE client enforcing STOP,
    // reconnect, projection and ACK. Undefined retains the client's defaults.
    // createClient validates ranges before any network or DOM side effect.
    if(reconnectReadTimeoutMs!==undefined)
      config.reconnectReadTimeoutMs=reconnectReadTimeoutMs;
    if(uiProjectionTimeoutMs!==undefined)
      config.uiProjectionTimeoutMs=uiProjectionTimeoutMs;
    if(ackSendTimeoutMs!==undefined)
      config.ackSendTimeoutMs=ackSendTimeoutMs;
    if(canonicalAckTimeoutMs!==undefined)
      config.canonicalAckTimeoutMs=canonicalAckTimeoutMs;
    const client=stream.createClient(config);
    // No direct access to UI terminal promotion or transport. All durable
    // terminal projection goes via authenticated readback in reconnect().
    return Object.freeze({
      begin:raw=>client.begin(raw),
      stop:raw=>client.stop(raw),
      reconnect:raw=>client.reconnect(raw)
    });
  }
  return Object.freeze({bind,BindingHold});
});
