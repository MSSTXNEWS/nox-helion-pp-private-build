/* Owner E01 · native-only route dispatcher. Never equate a click to a host ACK. */
const ROUTE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
// Mirror the immutable native PACK01 owner/risk floor. Every sensitive or
// dangerous approved route requires native consent here as defense in depth.
// Native host still independently enforces ACL, consent and signed ACK.
const NATIVE_SENSITIVE = new Set([
  "chat.history",
  "chat.attach",
  "chat.voice",
  "models.pull",
  "models.gguf.import",
  "models.retry",
  "rag.import",
  "memory.manage",
  "training.start",
  "training.resume",
  "training.checkpoints",
  "translate.ru_es",
  "calls.dial",
  "calls.history",
  "media.player",
  "browser.open",
  "images.generate",
  "system.update",
  "system.backup",
  "system.pc_control",
  "mobile.connect"
]);
const LEGACY_SENSITIVE = /^(?:system\.(?:restart|uninstall|clean|delete)|(?:sip|phone)\.|files\.delete|models\.remove)/i;
const denied = reason => Object.freeze({ok:false,reason});
export function createP01RouteDispatcher(port) {
  if (!port || typeof port.isAvailable !== 'function' || typeof port.invokeRoute !== 'function')
    throw Error('E06_PORT_REQUIRED');
  const busy = new Set();
  let closed = false;
  return Object.freeze({
    async invoke(routeId) {
      if (closed) return denied('PORT_CLOSED');
      if (typeof routeId !== 'string' || !ROUTE.test(routeId)) return denied('INVALID_ROUTE');
      if (busy.has(routeId)) return denied('PENDING');
      // Reserve first: isAvailable is a host callback and may reenter this dispatcher.
      busy.add(routeId);
      try {
        let enabled;
        try { enabled = port.isAvailable(routeId) === true; }
        catch { return denied('CAPABILITY_CHECK_FAILED'); }
        if (!enabled) return denied('NATIVE_CAPABILITY_HOLD');
        if (NATIVE_SENSITIVE.has(routeId) || LEGACY_SENSITIVE.test(routeId)) {
          // Only the trusted E06 host may supply this callback. Never manufacture approval in JS.
          if (typeof port.authorizeSensitive !== 'function') return denied('NATIVE_CONSENT_REQUIRED');
          let approved;
          try { approved = await port.authorizeSensitive(Object.freeze({routeId,origin:'P01'})); }
          catch { return denied('NATIVE_CONSENT_DENIED'); }
          if (closed || approved !== true) return denied('NATIVE_CONSENT_DENIED');
          // A native authorization can expire during user confirmation.
          try { if (port.isAvailable(routeId) !== true) return denied('NATIVE_CAPABILITY_HOLD'); }
          catch { return denied('CAPABILITY_CHECK_FAILED'); }
        }
        if (closed) return denied('PORT_CLOSED');
        const ack = await port.invokeRoute(Object.freeze({routeId,origin:'P01'}));
        if (closed) return denied('PORT_CLOSED');
        if (ack?.ok !== true || ack.routeId !== routeId ||
            typeof ack.receiptId !== 'string' || !ROUTE.test(ack.receiptId))
          return denied('ACK_MISSING');
        return Object.freeze({ok:true,routeId,receiptId:ack.receiptId});
      } catch { return denied('NATIVE_ERROR'); }
      finally { busy.delete(routeId); }
    },
    isPending(routeId) { return busy.has(routeId); },
    close() { closed = true; }
  });
}
