/* Появление карточек: GSAP из vendor (оригинал), fade+slide, один раз, prefers-reduced-motion уважается. Откат ?reveal=0 */
(function () {
  'use strict';
  if (/[?&]reveal=0/.test(location.search) || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  var done = new WeakSet();
  function pick() {
    var out = []; document.querySelectorAll('.card,sl-card,.tile,.nox-card,section.panel,.fld-card').forEach(function (e) {
      if (done.has(e) || out.length >= 24) return; var r = e.getBoundingClientRect(); if (r.width < 60 || r.height < 30 || r.top > innerHeight * 1.1 || r.bottom < 0) return;
      var cs = getComputedStyle(e); if ((cs.transform && cs.transform !== 'none') || +cs.opacity < 1 || e.getAnimations().length) return; if (cs.position === 'fixed' || cs.position === 'sticky' || cs.display === 'none' || e.closest('deep-chat,.nox-sheet,[hidden]')) return;
      if (e.closest('.card,sl-card') && e.parentElement.closest('.card,sl-card')) return;
      done.add(e); out.push(e);
    }); return out;
  }
  function run() {
    var g = window.gsap; if (!g) return; var els = pick(); if (!els.length) return;
    g.from(els, { opacity: 0, y: 14, duration: 0.55, stagger: 0.05, ease: 'power2.out', clearProps: 'opacity,transform' });
  }
  function load(cb) {
    if (window.gsap) return cb(); var s = document.createElement('script'); s.src = './vendor/gsap/gsap.min.js'; s.onload = cb; s.onerror = function () {}; document.head.appendChild(s);
  }
  function start() { setTimeout(function () { load(function () { run(); setTimeout(run, 1200); setTimeout(run, 3000); }); }, 400); }
  if (document.readyState === 'complete') start(); else addEventListener('load', start);
})();
