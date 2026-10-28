// Owner E01 V16 P01. Real native route invocations only; no UI fake success.
export function createP01RouteDispatcher(port) {
  if (!port || typeof port.isAvailable !== "function" || typeof port.invokeRoute !== "function") throw Error("E06_PORT_REQUIRED");
  const busy = new Set();
  return Object.freeze({async invoke(routeId) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(routeId)) return {ok:false,reason:"INVALID_ROUTE"};
    if (busy.has(routeId)) return {ok:false,reason:"PENDING"};
    if (port.isAvailable(routeId) !== true) return {ok:false,reason:"NATIVE_CAPABILITY_HOLD"};
    busy.add(routeId);
    try {
      const ack = await port.invokeRoute(Object.freeze({routeId,origin:"P01"}));
      if (ack?.ok !== true || ack.routeId !== routeId ||
          !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(ack.receiptId||"")) return {ok:false,reason:"ACK_MISSING"};
      return {ok:true,routeId,receiptId:ack.receiptId};
    } catch { return {ok:false,reason:"NATIVE_ERROR"}; }
    finally { busy.delete(routeId); }
  },isPending(routeId){return busy.has(routeId)}});
}
