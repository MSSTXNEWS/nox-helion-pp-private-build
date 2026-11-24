/* B1 R74 opt-in transport guard, pre-POST only. Host supplies authenticated read-only verifier, same physical route/bytes and durable server idempotency. Existing B1 R71 owns STOP signal and GET/ACK. No native admission or synthetic event IDs. */
(function(root){'use strict';
function createWireGuard({transport,verifyWire,contract,deadlineMs=5000}={}){
  const fail=code=>{throw Object.assign(new Error(code),{code});};
  const id=/^[A-Za-z0-9._:-]{1,128}$/;
  const sha=/^[a-f0-9]{64}$/;
  if(!transport||typeof transport.post!=="function"||typeof transport.readback!=="function"||typeof transport.ack!=="function"||typeof verifyWire!=="function"||!contract||!Number.isSafeInteger(deadlineMs)||deadlineMs<1||deadlineMs>60000)fail("HOLD_B1_WIRE_CONFIG");
  const pin=Object.freeze({wire:contract.wire,route:contract.route,served_sha256:contract.served_sha256,server_sha256:contract.server_sha256});
  if(pin.wire!=="named-delta-stable-server-id-v1"||typeof pin.route!=="string"||!id.test(pin.route)||typeof pin.served_sha256!=="string"||!sha.test(pin.served_sha256)||typeof pin.server_sha256!=="string"||!sha.test(pin.server_sha256))fail("HOLD_B1_WIRE_PROFILE");
  const send=transport.post.bind(transport), seen=new Set();
  if(typeof root.AbortController!=="function"||!root.performance||typeof root.performance.now!=="function")fail("HOLD_B1_WIRE_CONFIG");
  const now=root.performance.now.bind(root.performance);
  async function post(raw,signal){
    if(!raw||typeof raw!=="object"||!signal||typeof signal.aborted!=="boolean"||typeof signal.addEventListener!=="function"||typeof signal.removeEventListener!=="function")fail("HOLD_B1_WIRE_SCOPE");
    const s=Object.freeze({conversation_id:raw.conversation_id,exchange_id:raw.exchange_id});
    if(typeof s.conversation_id!=="string"||!id.test(s.conversation_id)||typeof s.exchange_id!=="string"||!id.test(s.exchange_id))fail("HOLD_B1_WIRE_SCOPE");
    const k=s.conversation_id+"\0"+s.exchange_id;
    if(seen.has(k))fail("HOLD_B1_WIRE_NO_REPOST");
    seen.add(k);
    if(signal.aborted)fail("HOLD_B1_WIRE_STOPPED");
    const started=now();
    const expired=()=>{const current=now();return !Number.isFinite(started)||!Number.isFinite(current)||current<started||current-started>=deadlineMs;};
    const verifier=new root.AbortController();
    let timer,onAbort,closed=false;
    try{
      const outcome=await Promise.race([
        Promise.resolve().then(()=>closed||signal.aborted?false:verifyWire(pin,s,verifier.signal)).then(ok=>ok===true?"verified":"denied",()=>"denied"),
        new Promise(resolve=>{onAbort=()=>{closed=true;resolve("stopped");};signal.addEventListener("abort",onAbort,{once:true});if(signal.aborted)onAbort();}),
        new Promise(resolve=>{timer=setTimeout(()=>{closed=true;resolve("timeout");},deadlineMs);})
      ]);
      if(signal.aborted||outcome==="stopped")fail("HOLD_B1_WIRE_STOPPED");
      if(outcome==="timeout"||expired())fail("HOLD_B1_WIRE_TIMEOUT");
      if(closed||outcome!=="verified")fail("HOLD_B1_WIRE_UNVERIFIED");
    }finally{closed=true;clearTimeout(timer);if(onAbort)signal.removeEventListener("abort",onAbort);verifier.abort();}
    if(signal.aborted)fail("HOLD_B1_WIRE_STOPPED");
    // The trusted verifier must bind the same authenticated physical route and
    // exact pinned bytes used by send; a local true is not native owner admission.
    // No async boundary between the final STOP fence and the original transport.
    if(expired())fail("HOLD_B1_WIRE_TIMEOUT");
    return send(s,signal);
  }
  const out={post,readback:transport.readback.bind(transport),ack:transport.ack.bind(transport)};
  if(typeof transport.readCanonicalAck==="function")out.readCanonicalAck=transport.readCanonicalAck.bind(transport);
  return Object.freeze(out);
}
const api=Object.freeze({createWireGuard});if(typeof module==='object'&&module.exports)module.exports=api;else root.NOXB1WireGuard=api;
})(typeof globalThis!=='undefined'?globalThis:this);
