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
    if(!s||typeof s!=='object'||Array.isArray(s)||
       typeof s.conversation_id!=='string'||!ID.test(s.conversation_id)||
       typeof s.exchange_id!=='string'||!ID.test(s.exchange_id))
      hold('HOLD_STREAM_SCOPE');
    return Object.freeze({conversation_id:s.conversation_id,exchange_id:s.exchange_id});
  }
  const key=s=>s.conversation_id+'\u0000'+s.exchange_id;
  function createClient({transport,host,bridge,ui,ackGate=null,
    strictAckNoReplay=false,timeoutMs=120000,
    canonicalFreshnessMs=30000,reconnectReadTimeoutMs=30000,
    uiProjectionTimeoutMs=30000,ackSendTimeoutMs=30000,
    canonicalAckTimeoutMs=30000}={}){
    if(!transport||!host||!bridge||!ui||
       typeof transport.post!=='function'||
       typeof transport.readback!=='function'||
       typeof transport.ack!=='function'||
       typeof host.readCommitted!=='function'||
       typeof bridge.acceptTerminal!=='function'||
       typeof ui.onDelta!=='function'||
       typeof ui.upsertTerminal!=='function'||
       typeof strictAckNoReplay!=='boolean'||
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
    function cancelAbandonedPost(res){
      try{
        const body=res&&res.body;
        if(!body||typeof body.cancel!=='function')return;
        const pending=body.cancel();
        if(pending&&typeof pending.catch==='function')pending.catch(()=>{});
      }catch(_){}
    }
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
            Promise.resolve().then(()=>transport.post(s,ctrl.signal))
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
        if(!res||res.ok!==true||!res.body||typeof res.body.getReader!=='function'){
          // A non-2xx or malformed POST can still own an open response body.
          // Dispose of it without blocking STOP, or touching UI, ACK or POST.
          cancelAbandonedPost(res);
          hold('HOLD_STREAM_POST_RESPONSE');
        }
        // Never silently replace malformed/incomplete UTF-8 with U+FFFD in
        // a model delta. An ambiguous stream must recover from canonical GET.
        // Even an HTTP-OK stream can throw while acquiring its reader. An
        // unclaimed body must be released before a fail-closed HOLD; never
        // retry the model POST or admit late SSE deltas/ACK.
        try{
          reader=res.body.getReader();
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
          if(outcome.aborted||ctrl.signal.aborted) return stopped();
          if(outcome.readError) hold('HOLD_STREAM_POST_OR_READ');
          const part=outcome.part;
          // EventSource allows CR, LF, and CRLF. Dispatch a lone CR
          // immediately (without waiting for another chunk or EOF), but
          // swallow a following LF if CRLF was split between reads. Even
          // zero-character TextDecoder outputs must preserve this fence.
          let decoded;
          try{
            // EOF flush also rejects a truncated final multibyte sequence.
            decoded=part.done?decoder.decode():
              decoder.decode(part.value,{stream:true});
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
            if(event==='delta'){
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
                  Promise.resolve().then(()=>ui.onDelta(
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
          if(frameTooLarge(buf)) hold('HOLD_STREAM_FRAME_TOO_LARGE');
          // A clean EOF cannot finalize a half-written SSE event. EventSource
          // discards unterminated data; NOX must surface uncertain delivery as
          // HOLD and recover by canonical GET, NEVER re-POST the model turn.
          // Trailing blank separators contain no event and are harmless.
          if(part.done){
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
      let completed=false,abandoned=false;
      try{
        // The transport may ignore AbortSignal and resolve after a STOP or
        // deadline with an unclaimed HTTP response body. Race() prevents
        // resuming UI/ACK but does not close that late GET connection.
        const answer=await boundedRead(
          ()=>Promise.resolve().then(()=>thunk(controller.signal))
            .then(value=>{
              if(abandoned||controller.signal.aborted||
                 (signal&&signal.aborted)) cancelAbandonedGet(value);
              return value;
            }),code,deadlineMs,signal);
        completed=true;
        return answer;
      }finally{
        if(!completed){
          abandoned=true;
          controller.abort();
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
      // The bridge is external to this opt-in client. An invalid witness
      // must HOLD before DOM projection or ACK, not escape as a TypeError.
      // Capture its complete trust-relevant scalar fields BEFORE awaiting
      // UI/ACK callbacks: the original bridge object can be mutated while
      // projection is pending, causing an event/cursor split-brain.
      if(!witness||typeof witness!=='object'||Array.isArray(witness)||
         witness.safe_to_ack!==true||witness.model_post!==false||
         witness.exchange_id!==s.exchange_id||witness.conversation_id!==s.conversation_id||
         typeof witness.projection_event_id!=='string'||
         !ID.test(witness.projection_event_id)||
         typeof witness.ack_cursor!=='string'||
         witness.ack_cursor.length<1||witness.ack_cursor.length>2048||
         /[\x00-\x1f\x7f]/.test(witness.ack_cursor)){
        discardReadback();
        hold('HOLD_STREAM_UNSAFE_WITNESS');
      }
      witness=Object.freeze({...witness});
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
      let projected;
      try{
        projected=await boundedRead(
          ()=>ui.upsertTerminal(s,witness.projection_event_id,projectionCtrl.signal),
          'HOLD_STREAM_UI_PROJECTION_TIMEOUT',uiProjectionTimeoutMs,signal);
      }catch(err){
        projectionCtrl.abort();
        if(err&&(err.code==='HOLD_STREAM_UI_PROJECTION_TIMEOUT'||
          err.code==='HOLD_STREAM_RECONNECT_STOPPED')) throw err;
        hold('HOLD_STREAM_UI_PROJECTION');
      }
      // Only an explicit positive DOM commit witness may precede ACK. A
      // missing return (undefined), null, string, or numeric truthy value
      // is not proof that the terminal row was actually projected.
      if(projected!==true) hold('HOLD_STREAM_UI_NOT_CONFIRMED');
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
        const discardVerifiedBody=()=>{
          if(verifiedBodyDiscarded||!verifiedReceipt)return;
          verifiedBodyDiscarded=true;
          cancelAbandonedGet(verifiedReceipt); // nonblocking, once only
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
              // readCanonicalAck MUST be a no-store, authenticated GET. It
              // MUST forward the challenge to the server; never a model POST.
              // The canonical receipt GET must be physically cancellable; a
              // timed-out or stopped late reply cannot resume gate CAS.
              if(lifecycleSignal.aborted)
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
                if(receipt)discardReceipt(receipt);
              };
              lifecycleSignal.addEventListener('abort',onReceiptAbort,{once:true});
              try{
                receipt=await Promise.resolve(transport.readCanonicalAck(
                  s,expected,challenge,lifecycleSignal)).then(value=>{
                    // Non-cooperative transport may settle after deadline/STOP.
                    if(lifecycleSignal.aborted)discardReceipt(value);
                    return value;
                  });
                if(lifecycleSignal.aborted)
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
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
                // The host verifier must attest scope, nonce, CAS and S03;
                // if it fails or hangs, the receipt body is not acknowledged.
                const trusted=await host.verifyFreshCanonicalAck(
                  receipt,expected,s,challenge);
                if(lifecycleSignal.aborted)
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                if(trusted!==true)hold('HOLD_STREAM_FRESHNESS_UNVERIFIED');
                freshVerified=true;
                return receipt;
              }catch(err){
                // Invalid/failing receipts must release the unclaimed socket.
                // After timeout this shares the same once-only abort fence.
                if(receipt)discardReceipt(receipt);
                throw err;
              }finally{
                lifecycleSignal.removeEventListener('abort',onReceiptAbort);
              }
            },
            async (receipt,expected)=>{
              // Freshness is only the first proof. A rejected, throwing,
              // stalled or stopped second verifier can abandon the same
              // canonical GET response body. Close it once without awaiting.
              // A fully verified response remains owned by its caller.
              let discarded=false;
              const discard=()=>{
                if(discarded)return;
                discarded=true;
                cancelAbandonedGet(receipt);
              };
              const onAbort=()=>discard();
              lifecycleSignal.addEventListener('abort',onAbort,{once:true});
              try{
                if(lifecycleSignal.aborted){
                  discard();
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                }
                let trusted;
                try{
                  trusted=await host.verifyCanonicalAck(
                    receipt,expected,s,lifecycleSignal);
                }catch(err){
                  discard();
                  throw err;
                }
                if(lifecycleSignal.aborted){
                  discard();
                  hold('HOLD_STREAM_RECONNECT_STOPPED');
                }
                if(trusted!==true)discard();
                else{
                  verifiedReceipt=receipt;
                  verifiedAckId=receipt.ack_id;
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
          discardVerifiedBody();
          if(err&&typeof err.code==='string') throw err;
          hold('HOLD_STREAM_CANONICAL_ACK');
        }
        if(!freshVerified){
          discardVerifiedBody();
          hold('HOLD_STREAM_FRESHNESS_UNVERIFIED');
        }
        if(!ack||ack.status!=='CANONICAL_ACK_CONFIRMED'||
           ack.authority!=='VERIFIER_CALLBACK_APPROVED'||
           typeof ack.ack_id!=='string'||!ID.test(ack.ack_id)||
           typeof verifiedAckId!=='string'||!ID.test(verifiedAckId)||
           ack.ack_id!==verifiedAckId){
          // A syntactically valid ACK for another exchange is NOT proof
          // for this verifier-approved GET receipt. Cancel its body once.
          discardVerifiedBody();
          hold('HOLD_STREAM_CANONICAL_ACK');
        }
        return Object.freeze({...witness,canonical_ack_status:ack.status,
          canonical_ack_id:ack.ack_id});
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
            return canonicalCompletion();
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
        }catch(_){hold('HOLD_STREAM_ACK_GATE');}
        if(reservationStatus==='ALREADY_ACKED') return canonicalCompletion();
        if(reservationStatus!=='RESERVED') hold('HOLD_STREAM_ACK_GATE');
        try{
          const sendReceipt=await boundedRead(()=>ackGate.beginSend(grant),
            'HOLD_STREAM_ACK_BEGIN_TIMEOUT',reconnectReadTimeoutMs,signal);
          // BeginSend is a durable CAS boundary, not an advisory response.
          // Native IndexedDB gate returns 'SENDING'; other adapters may
          // commit with true or resolve void. Reject all other results
          // before the network ACK escapes, including false and malformed.
          if(sendReceipt!=='SENDING' &&
             sendReceipt!==true && sendReceipt!==undefined)
            hold('HOLD_STREAM_ACK_GATE');
        }
        catch(err){
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
        if(ackAttempted.has(attemptKey))
          hold('HOLD_STREAM_ACK_UNCERTAIN_GET_ONLY');
        ackAttempted.add(attemptKey);
      }
      try{
        // ACK may be accepted by the server even if its Promise never
        // settles. Bound this wait, but DO NOT cancel/retry a potentially
        // committed ACK: ackGate remains durably SENDING. Subsequent
        // reconnect uses canonical GET-only verification of that attempt.
        const acked=await boundedRead(
          ()=>transport.ack(s,witness.ack_cursor),
          'HOLD_STREAM_ACK_SEND_TIMEOUT',ackSendTimeoutMs,signal);
        // Strict opt-in transports must explicitly attest true. Legacy
        // transports preserve their prior void-success contract; only false
        // means explicitly unconfirmed. Neither result is canonical proof.
        if(strictAckNoReplay ? acked!==true : acked===false)
          hold('HOLD_STREAM_ACK_UNCONFIRMED');
        // Leave IndexedDB SENDING until a signed canonical GET proves ACKED.
        // A local confirm() would create ACKED without a server proof digest
        // and permanently block requireCanonicalAck() as unverified.
      }catch(err){
        if(err&&(err.code==='HOLD_STREAM_ACK_SEND_TIMEOUT'||
          err.code==='HOLD_STREAM_RECONNECT_STOPPED')) throw err;
        hold('HOLD_STREAM_ACK_UNCONFIRMED');
      }
      return ackGate?canonicalCompletion():witness;
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