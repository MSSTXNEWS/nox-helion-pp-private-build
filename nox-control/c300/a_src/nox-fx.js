/* NOX · общая оболочка «вау»: пепел/искры (tsParticles), кино-переходы и появление блоков (GSAP), микро-анимации (Motion), HUD-рамки (Arwes). Всё отключается при Reduced Motion. */
(() => {
  if (window.__noxfx) return; window.__noxfx = 1;
  const U = (p) => new URL(p, document.currentScript && document.currentScript.src || import.meta.url).href;
  const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const load = (src) => new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.async = true; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  const main = () => document.querySelector('main.page, main.stage, main');
  const idle = (f, t = 800) => (window.requestIdleCallback ? requestIdleCallback(f, { timeout: t + 1500 }) : setTimeout(f, t));
  /* --- кино-переходы и появление блоков --- */
  async function motion() {
    try { await load(U('./vendor/fx/gsap.min.js')); } catch (e) { return; }
    const g = window.gsap; if (!g) return; const m = main();
    if (m) g.fromTo(m, { opacity: 0 }, { opacity: 1, duration: 0.5, ease: 'power2.out', clearProps: 'opacity' });
    const io = new IntersectionObserver((es) => { es.forEach((e) => { if (e.isIntersecting) { io.unobserve(e.target); g.fromTo(e.target, { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, ease: 'power3.out', clearProps: 'transform,opacity' }); } }); }, { threshold: 0.05 });
    const seen = new WeakSet(); const watch = () => document.querySelectorAll('main .card:not(.nox-seen), main .tile:not(.nox-seen), .cx-card:not(.nox-seen)').forEach((c) => { c.classList.add('nox-seen'); if (!seen.has(c)) { seen.add(c); io.observe(c); } });
    watch(); new MutationObserver(() => watch()).observe(document.body, { childList: true, subtree: true });
    document.addEventListener('click', (e) => {
      const a = e.target.closest && e.target.closest('a[href]'); if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || a.target || a.hasAttribute('download')) return;
      const u = new URL(a.href, location.href); if (u.origin !== location.origin || !/\.html$/.test(u.pathname) || (u.pathname === location.pathname && u.hash)) return;
      e.preventDefault(); const go = () => { location.href = u.href; }; const t = main(); if (!t) return go(); g.to(t, { opacity: 0, duration: 0.22, ease: 'power1.in', onComplete: go }); setTimeout(go, 600);
    });
    addEventListener('pageshow', (e) => { if (e.persisted && m) m.style.opacity = ''; });
  }
  /* --- микро-анимации Motion: нажатие --- */
  async function micro() {
    try { await load(U('./vendor/fx/motion.js')); } catch (e) { return; } const M = window.Motion; if (!M || !M.animate) return;
    let cur = null;
    document.addEventListener('pointerdown', (e) => { const b = e.target.closest && e.target.closest('button:not(:disabled), .tag, .chip, a.tile'); if (!b || b.closest('sl-dialog,sl-drawer,deep-chat')) return; cur = b; try { M.animate(b, { scale: 0.95 }, { duration: 0.12 }); } catch (x) { /* */ } }, true);
    const up = () => { if (cur) { try { M.animate(cur, { scale: 1 }, { duration: 0.35, type: 'spring', stiffness: 380, damping: 18 }); } catch (x) { /* */ } cur = null; } };
    addEventListener('pointerup', up, true); addEventListener('pointercancel', up, true);
  }
  /* --- пепел и искры вокруг солнца --- */
  async function ash() {
    try { await load(U('./vendor/nox-extra/tsparticles.slim.bundle.min.js')); } catch (e) { return; } const T = window.tsParticles; if (!T) return;
    const box = document.createElement('div'); box.id = 'nox-fx-ash'; box.setAttribute('aria-hidden', 'true'); document.body.prepend(box);
    const small = innerWidth < 700;
    const o = { fullScreen: { enable: false }, background: { color: 'transparent' }, fpsLimit: 40, detectRetina: true, pauseOnBlur: true, pauseOnOutsideViewport: true,
      particles: { number: { value: small ? 18 : 40 }, color: { value: ['#ff7a4c', '#ffb070', '#e8431f', '#ffd9a0'] }, shape: { type: 'circle' },
        opacity: { value: { min: 0.1, max: 0.65 }, animation: { enable: true, speed: 0.5, sync: false } }, size: { value: { min: 0.6, max: 2.1 } },
        move: { enable: true, speed: { min: 0.12, max: 0.55 }, direction: 'top', random: true, straight: false, outModes: { default: 'out' } }, twinkle: { particles: { enable: true, frequency: 0.04, opacity: 1 } } } };
    try { await T.load({ id: 'nox-fx-ash', element: box, options: o }); } catch (e) { try { await T.load('nox-fx-ash', o); } catch (e2) { box.remove(); } }
  }
  /* --- HUD-рамки Arwes --- */
  async function hud() {
    if (!document.querySelector('main .card, .cx-card')) return;
    try { const m = await import(U('./vendor/nox-fx/hud.js')); const run = () => m.hud('main .card, .cx-card'); run(); setTimeout(run, 1500); setTimeout(run, 4000); new MutationObserver(() => { clearTimeout(hud.t); hud.t = setTimeout(run, 400); }).observe(document.body, { childList: true, subtree: true }); } catch (e) { /* */ }
  }
  const start = () => { micro(); hud(); if (!RM) { motion(); idle(ash, 900); } };
  if (document.readyState === 'complete') start(); else addEventListener('load', () => setTimeout(start, 50), { once: true });
})();

/* NOX · доступность: у кнопок без текста ставим aria-label и title (из подписи иконки, класса или data-tip) */
(() => {
  const label = () => {
    document.querySelectorAll('button:not([aria-label]):not([title])').forEach((b) => {
      if (b.textContent.trim() || b.getAttribute('aria-labelledby')) return;
      const t = b.dataset.tip || (b.querySelector('title') || {}).textContent || (b.className && String(b.className).replace(/[-_]/g, ' ').trim()) || 'Кнопка';
      b.setAttribute('aria-label', t); b.title = t;
    });
  };
  let t; const run = () => { clearTimeout(t); t = setTimeout(label, 300); };
  const start = () => { label(); new MutationObserver(run).observe(document.body, { childList: true, subtree: true }); };
  if (document.readyState === 'complete') start(); else addEventListener('load', start, { once: true });
})();
