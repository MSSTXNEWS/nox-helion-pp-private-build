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
  function scope(s){
    if(!s||typeof s!=='object'||Array.isArray(s)||
       typeof s.conversation_id!=='string'||!ID.test(s.conversation_id)||
       typeof s.exchange_id!=='string'||!ID.test(s.exchange_id))
      hold('HOLD_B1_UI_SCOPE');
    return {conversation_id:s.conversation_id,exchange_id:s.exchange_id};
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
      if(terminalIntents.has(k)) return false;
      // SSE reconnect may replay the final event. Reserve the event ID before
      // the first await, across all adapters sharing this DOM container.
      // Equal IDs with different payloads are corrupt: fail closed.
      const replayKey=eventId===undefined?null:k+'\u0000'+eventId;
      if(replayKey!==null){
        const known=deltaEvents.get(replayKey);
        if(known){
          if(known.delta!==delta) hold('HOLD_B1_UI_REPLAY_PAYLOAD');
          if(known.committed) return false;
          return known.promise.then(ok=>
            ok===true?false:onDelta(s,delta,signal,eventId));
        }
      }
      const previous=deltaTails.get(k)||Promise.resolve();
      let reservation=null;
      const job=previous.catch(()=>{}).then(async()=>{
        if(signal.aborted) return false;
        let onAbort,timeoutId=null;
        let outcome;
        try{
          outcome=await Promise.race([
            Promise.resolve().then(()=>beforeCommit('delta',s))
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
      return job;
    }
    // The SSE caller may pass the exchange STOP signal. Legacy callers still
    // have a finite precommit timeout and cannot commit after it has expired.
    function upsertTerminal(raw,eventId,signal){
      const s=scope(raw);
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
        if(pending.eventId!==eventId)
          hold('HOLD_B1_UI_CONFLICTING_TERMINAL');
        // A reconnect with a fresh STOP signal must not inherit false from
        // an already-aborted terminal projection. Wait for its reservation to
        // settle, then project the same server-verified event via GET-only
        // readback. Never overlap two writers or accept a different event ID.
        if(signal&&pending.signal&&pending.signal!==signal){
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
              return projected===true?true:upsertTerminal(s,eventId,signal);
            },
            error=>{
              if(signal.aborted) return false;
              if(pending.signal.aborted) return upsertTerminal(s,eventId,signal);
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
          await previous;
          if(closed||(signal&&signal.aborted)) return {kind:'aborted'};
          await beforeCommit('terminal',s);
          // No asynchronous gap between this fence and the DOM mutation.
          if(closed||(signal&&signal.aborted)) return {kind:'aborted'};
          let el=find(s);
          if(el&&el.dataset.noxB1EventId&&el.dataset.noxB1EventId!==eventId)
            hold('HOLD_B1_UI_CONFLICTING_TERMINAL');
          if(!el) el=create(s);
          el.dataset.noxB1EventId=eventId;
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
      const intent={eventId,promise:job,signal};
      terminalIntents.set(k,intent);
      const release=()=>{if(terminalIntents.get(k)===intent) terminalIntents.delete(k);};
      job.then(release,release);
      return job;
    }
    return Object.freeze({onDelta,upsertTerminal});
  }
  return Object.freeze({createUiAdapter,UiHold});
});
