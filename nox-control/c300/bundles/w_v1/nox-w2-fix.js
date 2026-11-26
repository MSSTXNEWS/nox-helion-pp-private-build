/* ACCEPT 26.11: unload-политика, Transition aborted, битые превью. Откат ?w2=0 */
(function () {
  'use strict';
  if (/[?&]w2=0/.test(location.search)) return;
  addEventListener('unhandledrejection', function (e) { var m = String((e.reason && (e.reason.message || e.reason)) || ''); if (/Transition was aborted|invalid state|AbortError/i.test(m)) e.preventDefault(); });
  function guard(img) {
    if (img.dataset.nxg) return; img.dataset.nxg = '1';
    img.addEventListener('error', function () { img.style.visibility = 'hidden'; var p = img.parentElement; if (p && !p.dataset.nxph) { p.dataset.nxph = '1'; p.style.background = 'rgba(255,255,255,.06)'; } }, { once: true });
    if (img.complete && img.naturalWidth === 0 && img.currentSrc) img.dispatchEvent(new Event('error'));
  }
  function scan() { document.querySelectorAll('img').forEach(guard); }
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
  scan();
})();
