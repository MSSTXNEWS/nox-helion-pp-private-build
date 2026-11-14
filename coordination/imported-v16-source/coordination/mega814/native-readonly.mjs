/* NOX V16 E06 real read-only P02 transport. Only host-generated replies
 * grant COMPLETED. This object is not an authority to approve, grant ACL,
 * open files, or attest E07. No page-defined backend success is allowed.
 */
const ID=/^[0-9a-f]{32}$/;
const VALID=new Set(["chat.model","chat.stop"]);
const HOLD=(reason,route)=>Object.freeze({ok:false,reason,route});
export function createNativeReadOnlyPort(host,options={}){
 const setTimeoutFn=options.setTimeout||setTimeout;
 const clearTimeoutFn=options.clearTimeout||clearTimeout;
 const expires=Number.isFinite(options.timeoutMs)&&options.timeoutMs>1000?
   Math.min(options.timeoutMs,30000):12000;
 const pending=new Map();
 let closed=false;
 if(typeof host?.postMessage!=="function"||
    typeof host?.addEventListener!=="function"||
    typeof host?.removeEventListener!=="function"){
   return Object.freeze({available:false,request:async(route)=>HOLD("NATIVE_WEBVIEW2_UNAVAILABLE",route),
     close(){},pendingCount:()=>0});
 }
 function onMessage(evt){
   const msg=evt?.data;
   if(msg?.kind!=="p02NativeResult"||!ID.test(msg?.requestId))return;
   const item=pending.get(msg.requestId);
   if(!item||item.route!==msg.routeId)return;
   pending.delete(msg.requestId);clearTimeoutFn(item.timer);
   // Native STOP is an acknowledgement of the request, not proof that
   // inference has stopped. Preserve this distinction in the UI.
   if(item.route==="chat.stop" && msg.state==="STOP_REQUESTED" && msg.errorCode==null){
     item.resolve(Object.freeze({ok:true,route:item.route,
       requestId:msg.requestId,stopRequested:true,hostReported:true,e07Accepted:false}));
     return;
   }
   if(msg.state==="COMPLETED" && msg.errorCode==null &&
      msg.result!==undefined && msg.result!==null){
      const payload=msg.result;
      if(item.route==="chat.model"&&
         (typeof payload!=="object"||!Array.isArray(payload.models))){
        item.resolve(HOLD("MODEL_CATALOG_SCHEMA_HOLD",item.route));
        return;
      }
      item.resolve(Object.freeze({ok:true,route:item.route,
          requestId:msg.requestId,value:payload,hostReported:true,e07Accepted:false}));
   }else item.resolve(HOLD(
     typeof msg.errorCode==="string"?msg.errorCode:"NATIVE_HOLD",item.route));
 }
 host.addEventListener("message",onMessage);
 async function request(route,payload={}){
  if(closed)return HOLD("PORT_CLOSED",route);
  if(!VALID.has(route)||payload===null||typeof payload!=="object"||
     Array.isArray(payload)||Object.keys(payload).length!==0)return HOLD("UNSUPPORTED_NATIVE_REQUEST",route);
  if(pending.size>=8)return HOLD("NATIVE_BACKPRESSURE",route);
  if(!globalThis.crypto?.getRandomValues)return HOLD("SECURE_NONCE_UNAVAILABLE",route);
  const bytes=crypto.getRandomValues(new Uint8Array(16));
  const requestId=Array.from(bytes).map(v=>v.toString(16).padStart(2,"0")).join("");
  if(!ID.test(requestId)||pending.has(requestId))return HOLD("REQUEST_NONCE_HOLD",route);
  return new Promise(resolve=>{
   const timer=setTimeoutFn(()=>{
      pending.delete(requestId);resolve(HOLD("NATIVE_TIMEOUT_HOLD",route));
   },expires);
   pending.set(requestId,{route,resolve,timer});
   try{host.postMessage({kind:"p02.native",requestId,routeId:route,payload:{}})}
   catch{clearTimeoutFn(timer);pending.delete(requestId);resolve(HOLD("NATIVE_TRANSPORT_HOLD",route))}
  });
 }
 function close(){
  if(closed)return;closed=true;
  host.removeEventListener("message",onMessage);
  for(const item of pending.values()){
    clearTimeoutFn(item.timer);item.resolve(HOLD("NATIVE_PORT_CLOSED",item.route));
  }
  pending.clear();
 }
 return Object.freeze({available:true,request,close,pendingCount:()=>pending.size});
}
