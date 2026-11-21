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
  class HoldStream extends Error {
    constructor(code){super(code);this.code=code;this.name='HoldStream';}
  }
  const hold=code=>{throw new HoldStream(code);};
  function snap(s){
    if(!s||typeof s!=='object'||Array.isArray(s)||
       typeof s.conversation_id!=='string'||!ID.test(s.conversation_id)||
       typeof s.exchange_id!=='string'||!ID.test(s.exchange_id))
      hold('HOLD_STREAM_SCOPE');
    return Object.freeze({conversation_id:s.conversation_id,exchange_id:s.exchange_id});
  }
  const key=s=>s.conversation_id+'\u0000'+s.exchange_id;
  function createClient({transport,host,bridge,ui,ackGate=null,timeoutMs=120000,
    canonicalFreshnessMs=30000}={}){
    if(!transport||!host||!bridge||!ui||
       typeof transport.post!=='function'||
       typeof transport.readback!=='function'||
       typeof transport.ack!=='function'||
       typeof host.readCommitted!=='function'||
       typeof bridge.acceptTerminal!=='function'||
       typeof ui.onDelta!=='function'||
       typeof ui.upsertTerminal!=='function'||
       (ackGate && (typeof ackGate.reserve!=='function'||
         typeof ackGate.beginSend!=='function'||typeof ackGate.confirm!=='function'||
         typeof ackGate.requireCanonicalAck!=='function'||
         typeof transport.readCanonicalAck!=='function'||
         typeof host.verifyCanonicalAck!=='function'||
         typeof host.verifyFreshCanonicalAck!=='function'))||
       !Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>600000||
       !Number.isSafeInteger(canonicalFreshnessMs)||
       canonicalFreshnessMs<1000||canonicalFreshnessMs>60000)
      hold('HOLD_STREAM_HOST_CONTRACT');
    const started=new Set(),active=new Map(),reconnecting=new Map();
    async function begin(raw){
      const s=snap(raw),k=key(s);
      if(started.has(k)) hold('HOLD_STREAM_NO_REPOST');
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
      try{
        // STOP and timeout must interrupt a hung preflight, not merely an SSE
        // stream. This remains a read-only probe; no local claim is native CAS.
        let onAbort;
        let preflight;
        try{
          preflight=await Promise.race([
            Promise.resolve().then(()=>host.readCommitted(
              s.conversation_id,s.exchange_id))
              .then(previous=>({previous}),()=>({storageError:true})),
            new Promise(resolve=>{
              onAbort=()=>resolve({aborted:true});
              ctrl.signal.addEventListener('abort',onAbort,{once:true});
              if(ctrl.signal.aborted) onAbort();
            })
          ]);
        }finally{
          if(onAbort) ctrl.signal.removeEventListener('abort',onAbort);
        }
        if(preflight.aborted||ctrl.signal.aborted) return stopped();
        if(preflight.storageError) hold('HOLD_STREAM_STORAGE');
        if(preflight.previous) hold('HOLD_STREAM_RECONNECT_ONLY');
        // The host must ALSO enforce durable exchange idempotency across
        // tabs, reloads and devices. Never re-POST an ambiguous exchange.
        const res=await transport.post(s,ctrl.signal);
        // A fetch/mock may resolve AFTER abort. Its body and buffered delta
        // are not authorized to reach UI once STOP or timeout has fired.
        if(ctrl.signal.aborted) return stopped();
        if(!res||res.ok!==true||!res.body||typeof res.body.getReader!=='function')
          hold('HOLD_STREAM_POST_RESPONSE');
        const reader=res.body.getReader(),decoder=new TextDecoder();
        let buf='';
        while(true){
          if(ctrl.signal.aborted) return stopped();
          // reader.read() is not guaranteed to settle when a custom transport
          // ignores AbortSignal. Race the pending read against STOP/timeout;
          // never wait for stream completion, cancel(), or an old SSE frame.
          let onReadAbort;
          let outcome;
          try{
            outcome=await Promise.race([
              Promise.resolve().then(()=>reader.read())
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
          if(outcome.aborted||ctrl.signal.aborted){
            // Best-effort stream cleanup, deliberately NOT awaited. Some
            // readers leave cancel() pending forever after network abort.
            try{
              const cancellation=reader.cancel();
              if(cancellation&&typeof cancellation.catch==='function')
                cancellation.catch(()=>{});
            }catch(_){}
            return stopped();
          }
          if(outcome.readError) hold('HOLD_STREAM_POST_OR_READ');
          const part=outcome.part;
          if(part.done) break;
          buf+=decoder.decode(part.value,{stream:true}).replace(/\r\n/g,'\n');
          if(buf.length>65536) hold('HOLD_STREAM_FRAME_TOO_LARGE');
          let e;
          while((e=buf.indexOf('\n\n'))>=0){
            // One chunk can contain multiple deltas. STOP inside an awaited UI
            // callback must fence ALL later frames, even in that same chunk.
            if(ctrl.signal.aborted) return stopped();
            const frame=buf.slice(0,e);
            buf=buf.slice(e+2);
            const lines=frame.split('\n');
            const event=lines.find(l=>l.startsWith('event:'));
            const data=lines.filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n');
            if(event && event.slice(6).trim()==='delta'){
              // The B1 DOM adapter accepts an optional immutable per-delta SSE
              // event ID. Without forwarding the wire id: field, its replay
              // dedupe never runs and reconnect can duplicate visible tokens.
              // Reject malformed/ambiguous IDs BEFORE any UI side effect.
              const ids=lines.filter(l=>l==='id'||l.startsWith('id:'));
              if(ids.length>1) hold('HOLD_STREAM_DELTA_EVENT_ID');
              const eventId=ids.length===1?ids[0].slice(3).trim():undefined;
              if(eventId!==undefined&&!ID.test(eventId))
                hold('HOLD_STREAM_DELTA_EVENT_ID');
              // UI handlers that await MUST check this signal immediately
              // before their actual DOM/state commit; this caller cannot undo
              // a UI effect already committed by an uncooperative adapter.
              await ui.onDelta(s,data,ctrl.signal,eventId);
              if(ctrl.signal.aborted) return stopped();
            }
            // Terminal SSE frames are deliberately NOT sufficient to ACK;
            // only a separately authenticated durable readback is accepted.
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
      }
    }
    function stop(raw){
      const k=key(snap(raw)),ctrl=active.get(k);
      if(!ctrl) return false;
      ctrl.abort();
      return true;
    }
    // One in-flight GET/readback + UI projection + ACK per exchange per tab.
    // Coalesce concurrent reconnect calls; after a failure, allow readback-only
    // recovery. NEVER start another model POST for an uncertain exchange.
    async function reconnectOnce(s){
      let packet,witness;
      try{
        packet=await transport.readback(s); // GET or equivalent, NEVER POST model
        witness=await bridge.acceptTerminal(packet,s,host);
      }catch(err){
        if(err&&typeof err.code==='string') throw err;
        hold('HOLD_STREAM_READBACK');
      }
      if(witness.safe_to_ack!==true||witness.model_post!==false||
         witness.exchange_id!==s.exchange_id||witness.conversation_id!==s.conversation_id)
        hold('HOLD_STREAM_UNSAFE_WITNESS');
      // ACK must follow a *successful* idempotent UI projection. A partially
      // written UI may throw; retry must use the same event_id without POST.
      let projected;
      try{projected=await ui.upsertTerminal(s,witness.projection_event_id);}
      catch(_){hold('HOLD_STREAM_UI_PROJECTION');}
      if(projected===false) hold('HOLD_STREAM_UI_NOT_CONFIRMED');
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
        try {
          ack=await ackGate.requireCanonicalAck(s,witness.projection_event_id,
            witness.ack_cursor,
            async expected=>{
              // readCanonicalAck MUST be a no-store, authenticated GET. It
              // MUST forward the challenge to the server; never a model POST.
              const receipt=await transport.readCanonicalAck(s,expected,challenge);
              const now=Date.now();
              if(!receipt||typeof receipt!=='object'||Array.isArray(receipt)||
                 receipt.request_nonce!==challenge.request_nonce||
                 !Number.isSafeInteger(receipt.issued_at_ms)||
                 !Number.isSafeInteger(receipt.expires_at_ms)||
                 receipt.issued_at_ms<challenge.requested_at_ms-5000||
                 receipt.issued_at_ms>now+5000||
                 receipt.expires_at_ms<=now||
                 receipt.expires_at_ms-receipt.issued_at_ms>canonicalFreshnessMs)
                hold('HOLD_STREAM_RECEIPT_FRESHNESS');
              // This callback MUST cryptographically attest the nonce,
              // timestamps, ACK scope, owner CAS and S03. A plain true
              // callback is acceptable ONLY in isolated synthetic tests.
              const trusted=await host.verifyFreshCanonicalAck(
                receipt,expected,s,challenge);
              if(trusted!==true) hold('HOLD_STREAM_FRESHNESS_UNVERIFIED');
              freshVerified=true;
              return receipt;
            },
            (receipt,expected)=>host.verifyCanonicalAck(receipt,expected,s));
        }catch(err){
          if(err&&typeof err.code==='string') throw err;
          hold('HOLD_STREAM_CANONICAL_ACK');
        }
        if(!freshVerified) hold('HOLD_STREAM_FRESHNESS_UNVERIFIED');
        if(!ack||ack.status!=='CANONICAL_ACK_CONFIRMED'||
           ack.authority!=='VERIFIER_CALLBACK_APPROVED'||
           typeof ack.ack_id!=='string'||!ID.test(ack.ack_id))
          hold('HOLD_STREAM_CANONICAL_ACK');
        return Object.freeze({...witness,canonical_ack_status:ack.status,
          canonical_ack_id:ack.ack_id});
      }
      let grant=null;
      if(ackGate){
        try{
          grant=await ackGate.reserve(s,witness.projection_event_id,witness.ack_cursor);
        }catch(err){
          // An uncertain SENDING ACK must NEVER be retransmitted: GET-only
          // readback, with the original event/cursor and CAS proof.
          if(err&&err.code==='HOLD_CROSSTAB_ACK_UNCERTAIN')
            return canonicalCompletion();
          if(err&&typeof err.code==='string') throw err;
          hold('HOLD_STREAM_ACK_GATE');
        }
        if(grant.status==='ALREADY_ACKED') return canonicalCompletion();
        if(grant.status!=='RESERVED') hold('HOLD_STREAM_ACK_GATE');
        try{await ackGate.beginSend(grant);}
        catch(err){
          if(err&&typeof err.code==='string') throw err;
          hold('HOLD_STREAM_ACK_GATE');
        }
      }
      try{
        const acked=await transport.ack(s,witness.ack_cursor);
        if(acked===false) hold('HOLD_STREAM_ACK_UNCONFIRMED');
        // Leave IndexedDB SENDING until a signed canonical GET proves ACKED.
        // A local confirm() would create ACKED without a server proof digest
        // and permanently block requireCanonicalAck() as unverified.
      }catch(_){hold('HOLD_STREAM_ACK_UNCONFIRMED');}
      return ackGate?canonicalCompletion():witness;
    }
    function reconnect(raw){
      const s=snap(raw),k=key(s);
      if(active.has(k)) hold('HOLD_STREAM_ACTIVE_POST');
      const pending=reconnecting.get(k);
      if(pending) return pending;
      const attempt=reconnectOnce(s);
      reconnecting.set(k,attempt);
      const clear=()=>{if(reconnecting.get(k)===attempt) reconnecting.delete(k);};
      attempt.then(clear,clear);
      return attempt;
    }
    return Object.freeze({begin,stop,reconnect});
  }
  return Object.freeze({createClient,HoldStream});
});