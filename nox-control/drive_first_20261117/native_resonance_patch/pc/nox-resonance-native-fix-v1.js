/* Read-only DOM compatibility. No network, model calls, storage or chat handlers. */
(function (root) {
  'use strict';
  function insetFor(top, previousExtra, headerBottom, limit) {
    if (![top, previousExtra, headerBottom, limit].every(Number.isFinite)) return 0;
    return Math.min(Math.max(0, limit), Math.max(0, Math.ceil(headerBottom + 12 - (top - previousExtra))));
  }
  function pageLabel(location) {
    if (!location || !/^https?:$/.test(location.protocol)) return 'NOX HELION · Резонанс';
    const host = typeof location.host === 'string' ? location.host.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 180) : '';
    return host ? 'NOX HELION · ' + host : 'NOX HELION · Резонанс';
  }
  if (typeof module === 'object' && module.exports) module.exports = {insetFor, pageLabel};
  if (!root.document) return;
  function start() {
    const document = root.document, body = document.body;
    if (!body || body.dataset.noxView !== 'resonance-v24' || body.dataset.noxReadabilityFix !== '1') return;
    const badge = document.getElementById('nox-public-safe-preview');
    if (badge) {
      badge.textContent = pageLabel(root.location);
      badge.title = 'Адрес открытой страницы';
    }
    const messages = document.getElementById('messages');
    if (!messages) return;
    const computed = root.getComputedStyle(messages);
    const base = parseFloat(computed.marginBlockStart || computed.marginTop) || 0;
    body.style.setProperty('--nox-message-base-margin', base + 'px');
    body.dataset.noxLayoutInset = 'ready';
    let extra = 0, frame = 0, disposed = false;
    const headers = Array.from(document.querySelectorAll('.nox-v28-pc-return, .nox-shared-header-v10, .v24-top'));
    function measure() {
      frame = 0;
      if (disposed || document.hidden) return;
      const box = messages.getBoundingClientRect();
      if (box.width <= 0 || box.height <= 0) return;
      let bottom = 0;
      for (const header of headers) {
        const rect = header.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0 && rect.right > box.left && rect.left < box.right) bottom = Math.max(bottom, rect.bottom);
      }
      const limit = Math.min(320, Math.max(0, root.innerHeight * 0.4));
      const next = insetFor(box.top, extra, bottom, limit);
      body.dataset.noxInsetState = next >= limit && bottom + 12 - (box.top - extra) > limit ? 'needs-layout-review' : 'measured';
      if (Math.abs(next - extra) >= 1) {
        extra = next;
        body.style.setProperty('--nox-message-header-inset', next + 'px');
      }
    }
    function schedule() { if (!frame && !disposed) frame = root.requestAnimationFrame(measure); }
    const observer = typeof root.ResizeObserver === 'function' ? new root.ResizeObserver(schedule) : null;
    if (observer) { headers.forEach(element => observer.observe(element)); observer.observe(messages); }
    root.addEventListener('resize', schedule, {passive: true});
    root.addEventListener('pageshow', schedule);
    document.addEventListener('visibilitychange', schedule);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(schedule);
    schedule();
    function onPageHide(event) {
      if (event.persisted) return; // BFCache freezes this document; keep its observers for restore.
      disposed = true;
      if (frame) root.cancelAnimationFrame(frame);
      if (observer) observer.disconnect();
      root.removeEventListener('resize', schedule);
      root.removeEventListener('pageshow', schedule);
      root.removeEventListener('pagehide', onPageHide);
      document.removeEventListener('visibilitychange', schedule);
    }
    root.addEventListener('pagehide', onPageHide);
  }
  if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})(typeof window === 'object' ? window : globalThis);
