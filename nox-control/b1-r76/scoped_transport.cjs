/* B1 opt-in integration seam. No native authority: the owner must supply
 * an independent authenticated binding provider and the matching transport.
 * Offline B3 consistency is necessary, never sufficient for admission. */
(function(root){
'use strict';
function createScopedTransport({createWireGuard,checkScope,readBinding,authenticateBinding,transport,contract,deadlineMs}={}){
 if([createWireGuard,checkScope,readBinding,authenticateBinding].some(f=>typeof f!=='function'))
   throw Object.assign(new Error('HOLD_B1_SCOPE_PROVIDER'),{code:'HOLD_B1_SCOPE_PROVIDER'});
 function freeze(v){if(v&&typeof v==='object'){Object.values(v).forEach(freeze);Object.freeze(v);}return v;}
 return createWireGuard({transport,contract,deadlineMs,verifyWire:async(pin,scope,signal)=>{
   if(signal.aborted)return false;
   // Snapshot once; the independently trusted authenticator must approve these
   // exact bytes and trusted expected turn, not caller-supplied success flags.
   const raw=await readBinding(pin,scope,signal);
   if(signal.aborted||!raw)return false;
   const binding=freeze(JSON.parse(JSON.stringify(raw)));
   if(signal.aborted)return false;
   const result=checkScope({wire:pin,scope,physical:binding.physical,mapping:binding.mapping,expectedTurn:binding.expectedTurn});
   if(!result||result.consistent!==true||signal.aborted)return false;
   const approved=await authenticateBinding(binding,pin,scope,signal);
   return approved===true&&!signal.aborted;
 }});
}
const api=Object.freeze({createScopedTransport});
if(typeof module==='object'&&module.exports)module.exports=api;else root.NOXB1ScopedTransport=api;
})(typeof globalThis!=='undefined'?globalThis:this);
