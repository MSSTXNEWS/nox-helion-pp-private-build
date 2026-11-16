/* WEB29 decorative Motion.js loader. Chat/S03/STOP never await this resource.
 * Preserves the original library in vendor/fx/motion.js, loads only when idle.
 */
(() => {'use strict';
  if (window.NoxMotionIdleLoader) return;
  const owner = document.currentScript;
  if (!owner?.src) return;
  const url = new URL('vendor/fx/motion.js', owner.src);
  if (url.origin !== location.origin) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  let chatBusy = false, voiceBusy = false, hidden = document.hidden, closed = false, stopped = false;
  let queued = false, started = false, done = !!window.Motion;
  let failed = false, idleHandle = null, fallbackHandle = null;
  let attempts = 0;
  const events = [];
  const on = (target, type, callback) => {
    target.addEventListener(type, callback);
    events.push([target, type, callback]);
  };
  const preferences = () => window.NoxWorkspace?.settings || {};
  const allowed = () => {
    const settings = preferences();
    return !closed && !hidden && !chatBusy && !voiceBusy && !stopped && !failed && !started && !done &&
      !reduce.matches && settings.motion !== 'reduce' && settings.mode !== 'ECO';
  };
  const cancel = () => {
    if (idleHandle !== null && window.cancelIdleCallback) cancelIdleCallback(idleHandle);
    if (fallbackHandle !== null) clearTimeout(fallbackHandle);
    idleHandle = fallbackHandle = null;
    queued = false;
  };
  function admit() {
    queued = false;
    idleHandle = fallbackHandle = null;
    if (!allowed()) return;
    if (window.Motion) { done = true; return; }
    started = true;
    attempts++;
    const script = document.createElement('script');
    script.async = true;
    script.src = url.href;
    script.dataset.noxDecorativeOnly = 'true';
    script.addEventListener('load', () => { done = true; });
    script.addEventListener('error', () => { failed = true; });
    document.head.appendChild(script);
  }
  function schedule() {
    if (!allowed() || queued) return;
    queued = true;
    if (typeof requestIdleCallback === 'function') {
      idleHandle = requestIdleCallback(admit, {timeout: 4000});
    } else {
      fallbackHandle = setTimeout(admit, 1400);
    }
  }
  on(window, 'nox-chat-activity', e => {chatBusy = e.detail?.active !== false; if (chatBusy) cancel(); else {stopped = false; schedule();}});
  on(window, 'nox-voice-activity', e => {voiceBusy = e.detail?.active !== false; if (voiceBusy) cancel(); else schedule();});
  on(window, 'nox-stop-requested', () => {stopped = true; cancel();});
  on(window, 'nox-settings', () => {if (!allowed()) cancel(); else schedule();});
  on(reduce, 'change', () => {if (!allowed()) cancel(); else schedule();});
  on(document, 'visibilitychange', () => {hidden = document.hidden; if (hidden) cancel(); else schedule();});
  on(window, 'pagehide', e => {cancel(); if (!e.persisted) {closed = true; for (const [host,type,fn] of events) host.removeEventListener(type,fn);}});
  on(window, 'pageshow', e => {if (e.persisted) {stopped = false; schedule();}});
  window.NoxMotionIdleLoader = Object.freeze({
    diagnostics: () => ({decorativeOnly: true, nonBlocking: true, originalLibraryPreserved: true,
      busy: chatBusy || voiceBusy, chatBusy, voiceBusy, stopped, queued, started, loaded: done, failed, attempts})
  });
  if (document.readyState === 'complete') schedule();
  else on(window, 'load', schedule);
})();
