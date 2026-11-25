/* TH-MOTION: stagger-появление карточек + мягкий отклик фона на курсор. Без зависимостей; no-op при prefers-reduced-motion. */
(function () {
  var d = document.documentElement;
  if (d.getAttribute('data-nox-theme') !== 'graphite') return;
  var mq = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)');
  if (mq && mq.matches) return;
  var SEL = '.card, sl-card', seen = new WeakSet(), n = 0, t0 = 0;
  function mark(el, i) {
    if (seen.has(el)) return; seen.add(el);
    el.style.setProperty('--nxi', Math.min(i, 14));
    el.classList.add('nx-m-in');
    el.addEventListener('animationend', function f(e) { if (e.target !== el) return; el.classList.remove('nx-m-in'); el.style.removeProperty('--nxi'); el.removeEventListener('animationend', f); });
  }
  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (es) {
    var k = 0; es.forEach(function (e) { if (e.isIntersecting) { io.unobserve(e.target); mark(e.target, k++); } });
  }, { threshold: .05 }) : null;
  function scan(root) {
    (root.querySelectorAll ? root.querySelectorAll(SEL) : []).forEach(function (el) {
      if (seen.has(el) || el.__nxo) return; el.__nxo = 1;
      if (io) io.observe(el); else mark(el, n++);
    });
  }
  function start() {
    scan(document);
    var q = 0, mo = new MutationObserver(function (ms) {
      if (++q > 400) { mo.disconnect(); return; }
      ms.forEach(function (m) { m.addedNodes.forEach(function (x) { if (x.nodeType === 1) { if (x.matches && x.matches(SEL) && !x.__nxo) { x.__nxo = 1; io ? io.observe(x) : mark(x, 0); } scan(x); } }); });
    });
    mo.observe(document.body, { childList: true, subtree: true });
    setTimeout(function () { mo.disconnect(); }, 8000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  /* курсор: цель сглаживается, обновление только когда есть заметная дельта */
  var tx = 50, ty = 30, cx = 50, cy = 30, raf = 0;
  function tick() {
    cx += (tx - cx) * .06; cy += (ty - cy) * .06;
    d.style.setProperty('--mx', cx.toFixed(2) + '%'); d.style.setProperty('--my', cy.toFixed(2) + '%');
    raf = (Math.abs(tx - cx) + Math.abs(ty - cy) > .05) ? requestAnimationFrame(tick) : 0;
  }
  addEventListener('pointermove', function (e) {
    tx = e.clientX / innerWidth * 100; ty = e.clientY / innerHeight * 100; if (!raf) raf = requestAnimationFrame(tick);
  }, { passive: true });
})();
