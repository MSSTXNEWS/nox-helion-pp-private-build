/* E01 C1: host-only dispatcher. UI visibility never proves native authorization. */
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SENSITIVE=/^(system\.(update|backup|pc_control|clean|restart)|sip\.|phone\.|filesystem\.|files\.delete)/i;
const deny=(reason)=>Object.freeze({ok:false,reason});
export function createP01RouteDispatcher(port){
  if(!port||typeof port.isAvailable!=="function"||typeof port.invokeRoute!=="function")
    throw Error("E06_PORT_REQUIRED");
  const pending=new Set();let closed=false;
  return Object.freeze({
    async invoke(routeId){
      if(closed)return deny("PORT_CLOSED");
      if(typeof routeId!=="string"||!ID.test(routeId))return deny("INVALID_ROUTE");
      if(pending.has(routeId))return deny("PENDING");
      pending.add(routeId); // Atomic reserve before host callbacks, including reentrant callbacks.
      try{
        let available;
        try{available=port.isAvailable(routeId);}catch{return deny("CAPABILITY_CHECK_FAILED");}
        if(available!==true)return deny("NATIVE_CAPABILITY_HOLD");
        if(SENSITIVE.test(routeId)){
          if(typeof port.authorizeSensitive!=="function")return deny("NATIVE_CONSENT_REQUIRED");
          let approval;
          try{approval=await port.authorizeSensitive(Object.freeze({routeId,origin:"P01"}));}
          catch{return deny("NATIVE_CONSENT_DENIED");}
          if(closed||approval!==true)return deny("NATIVE_CONSENT_DENIED");
        }
        if(closed)return deny("PORT_CLOSED");
        const ack=await port.invokeRoute(Object.freeze({routeId,origin:"P01"}));
        if(closed)return deny("PORT_CLOSED");
        if(ack?.ok!==true||ack.routeId!==routeId||
           typeof ack.receiptId!=="string"||!ID.test(ack.receiptId))
          return deny("ACK_MISSING");
        return Object.freeze({ok:true,routeId,receiptId:ack.receiptId});
      }catch{return deny("NATIVE_ERROR");}
      finally{pending.delete(routeId);}
    },
    isPending:routeId=>pending.has(routeId),
    close(){closed=true;},
    get isClosed(){return closed;}
  });
}
