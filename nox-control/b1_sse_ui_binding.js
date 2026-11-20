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
    timeoutMs,canonicalFreshnessMs}={}){
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
    const ui=dom.createUiAdapter(options);
    const config={transport,host,bridge,ui,ackGate};
    if(timeoutMs!==undefined) config.timeoutMs=timeoutMs;
    if(canonicalFreshnessMs!==undefined)
      config.canonicalFreshnessMs=canonicalFreshnessMs;
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
