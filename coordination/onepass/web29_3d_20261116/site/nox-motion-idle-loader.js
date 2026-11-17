/* WEB29 decorative Motion.js loader. Chat/S03/STOP never await this resource.
 * Preserves the original library in vendor/fx/motion.js, loads only when proven idle.
 */
(() => {'use strict';
  if (window.NoxMotionIdleLoader) return;
  const owner = document.currentScript;
  if (!owner?.src) return;
  const url = new URL('vendor/fx/motion.js', owner.src);
  if (url.origin !== location.origin) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  let chatBusy = false, voiceBusy = false, mediaBusy = false, runtimeBusy = false;
  // Native owner pages must observe a quiet runtime before decorative fetch.
  let runtimeKnown = window.NOX_NATIVE_OWNER !== true;
  let hidden = document.hidden, closed = false, stopped = false;
  let queued = false, started = false, done = !!window.Motion;
  let failed = false, idleHandle = null, fallbackHandle = null, inflight = null;
  let attempts = 0;
  const events = [];
  const on = (target, type, callback) => {
    target.addEventListener(type, callback);
    events.push([target, type, callback]);
  };
  const preferences = () => window.NoxWorkspace?.settings || {};
  const editing = () => document.documentElement?.dataset?.typing === 'true' ||
    !!document.activeElement?.closest?.('textarea,input,[contenteditable="true"],loquix-chat-composer');
  const training = () => document.body?.dataset?.trainingActive === 'true';
  // Quiet state is separate from admission: an in-flight script sets started=true,
  // but a harmless settings/runtime event must not abort that same request.
  const quiet = () => {
    const settings = preferences();
    return !closed && !hidden && !chatBusy && !voiceBusy && !mediaBusy && runtimeKnown &&
      !runtimeBusy && !editing() && !training() && !stopped && !reduce.matches &&
      settings.motion !== 'reduce' && settings.mode !== 'ECO';
  };
  const allowed = () => quiet() && !failed && !started && !done;
  const cancel = () => {
    if (idleHandle !== null && window.cancelIdleCallback) cancelIdleCallback(idleHandle);
    if (fallbackHandle !== null) clearTimeout(fallbackHandle);
    idleHandle = fallbackHandle = null;
    queued = false;
    // Decorative fetch is best-effort canceled when a native request or STOP
    // takes priority. Removing <script> is not a guarantee the network stopped.
    if (inflight) {
      const {script, onLoad, onError} = inflight;
      inflight = null;
      script.removeEventListener('load', onLoad);
      script.removeEventListener('error', onError);
      script.remove();
      started = false;
    }
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
    const onLoad = () => {
      if (inflight?.script !== script) return;
      inflight = null;
      done = true;
    };
    const onError = () => {
      if (inflight?.script !== script) return;
      inflight = null;
      failed = true;
    };
    inflight = {script, onLoad, onError};
    script.addEventListener('load', onLoad);
    script.addEventListener('error', onError);
    document.head.appendChild(script);
  }
  function schedule() {
    if (!allowed() || queued) return;
    queued = true;
    if (typeof requestIdleCallback === 'function') {
      // Never force a decorative fetch during prolonged token rendering/input.
      idleHandle = requestIdleCallback(admit);
    } else {
      fallbackHandle = setTimeout(admit, 1400);
    }
  }
  on(window, 'nox-chat-activity', e => {
    const active = e.detail?.active !== false;
    if (active) {
      // Only a NEW busy->idle generation can resume decoration after STOP.
      // Duplicate 'active' events during the aborted generation keep STOP.
      if (!chatBusy && stopped) stopped = false;
      chatBusy = true;
      cancel();
    } else {
      chatBusy = false;
      // The aborted stream's final idle event cannot undo STOP.
      schedule();
    }
  });
  on(window, 'nox-voice-activity', e => {voiceBusy = e.detail?.active !== false; if (voiceBusy) cancel(); else schedule();});
  on(window, 'nox-media-activity', e => {mediaBusy = e.detail?.active !== false; if (mediaBusy) cancel(); else schedule();});
  on(window, 'nox-runtime-observed', e => {
    runtimeKnown = e.detail?.known === true;
    runtimeBusy = e.detail?.busy !== false;
    if (!quiet()) cancel(); else schedule();
  });
  on(window, 'nox-typing', () => {if (!quiet()) cancel(); else schedule();});
  on(window, 'nox-training-activity', () => {if (!quiet()) cancel(); else schedule();});
  on(window, 'nox-stop-requested', () => {stopped = true; cancel();});
  on(window, 'nox-settings', () => {if (!quiet()) cancel(); else schedule();});
  on(reduce, 'change', () => {if (!quiet()) cancel(); else schedule();});
  on(document, 'visibilitychange', () => {hidden = document.hidden; if (hidden) cancel(); else schedule();});
  on(window, 'pagehide', e => {cancel(); if (!e.persisted) {closed = true; for (const [host,type,fn] of events) host.removeEventListener(type,fn);}});
  // BFCache re-entry is not a new owner/chat generation: a prior STOP stays
  // latched until an explicitly new chat-active transition clears it.
  // The normal no-STOP BFCache restore still admits decorative idle work.
  on(window, 'pageshow', e => {if (e.persisted) schedule();});
  window.NoxMotionIdleLoader = Object.freeze({
    diagnostics: () => ({decorativeOnly: true, nonBlocking: true, originalLibraryPreserved: true,
      busy: chatBusy || voiceBusy || mediaBusy || runtimeBusy || editing() || training(),
      chatBusy, voiceBusy, mediaBusy, runtimeKnown, runtimeBusy,
      stopped, queued, started, inFlight: !!inflight, loaded: done, failed, attempts})
  });
  if (document.readyState === 'complete') schedule();
  else on(window, 'load', schedule);
})();
