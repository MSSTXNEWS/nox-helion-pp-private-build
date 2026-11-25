/* C: Ghost-Tab во всех текстовых полях страницы. Использует NOXGhost.attach (nox-ghost.js). Исключения: [data-noghost], password/file/number/hidden, readonly/disabled. */
(function () {
  'use strict';
  const BAD = /^(password|file|number|hidden|checkbox|radio|range|color|date|time|datetime-local|month|week|submit|button)$/i;
  const SEL = 'textarea, input, sl-input, sl-textarea';
  function ok(el) {
    if (el.__ghost || el.closest('[data-noghost]') || el.disabled || el.readOnly || el.hasAttribute('readonly')) return false;
    const t = (el.getAttribute('type') || 'text'); if (BAD.test(t)) return false;
    if (el.tagName === 'INPUT' && el.closest('sl-input')) return false;
    return true;
  }
  function scan(root) {
    if (!window.NOXGhost) return;
    (root.querySelectorAll ? root.querySelectorAll(SEL) : []).forEach((el) => {
      if (!ok(el)) return;
      try { NOXGhost.attach(el, { page: (el.id || el.getAttribute('name') || el.getAttribute('placeholder') || 'field').toString().slice(0, 40) + '@' + (document.title || 'page').slice(0, 30) }); } catch (e) { }
    });
  }
  let t = 0; const later = () => { clearTimeout(t); t = setTimeout(() => scan(document), 400); };
  new MutationObserver(later).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('load', later); document.addEventListener('focusin', (e) => { const el = e.target && e.target.closest && e.target.closest(SEL); if (el && ok(el)) scan(el.parentNode || document); }, true);
  later();
})();
