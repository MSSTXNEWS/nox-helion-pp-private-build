/* NOX · kit-motion (V2-33): каскад появления, подъём карточек при наведении, count-up только на реальных числах.
   Подключение без переписывания страниц: <script src="/web/v2/kit-motion.js" defer>. Только Web Animations API, без зависимостей.
   Выключается: prefers-reduced-motion, html[data-q=eco], html[data-motion=off]; на страницах кита (там своя анимация) не делает ничего. */
(() => {
  if (window.__kitMotion) return; window.__kitMotion = 1;
  const rm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const off = () => rm || document.documentElement.dataset.q === 'eco' || document.documentElement.dataset.motion === 'off';
  if (off()) return;
  const CARD = '[class*="card" i],[class*="panel" i],[class*="tile" i],[class*="widget" i],[class*="glass" i],main section,main article,#page section,#page article';
  const NUM = '[class*="kpi" i],[class*="stat" i],[class*="metric" i],[class*="num" i],[data-count]';
  const st = document.createElement('style');
  st.textContent = '.km-lift{transition:transform .25s cubic-bezier(.2,.8,.2,1),box-shadow .25s}.km-lift:hover{transform:translateY(-2px);box-shadow:0 12px 34px rgba(0,0,0,.45),0 0 22px rgba(255,150,40,.12)}@media(hover:none){.km-lift:hover{transform:none}}';
  document.head.appendChild(st);
  const seen = new WeakSet(); let stagger = 0, tmo = 0;
  const reveal = new IntersectionObserver((es) => { es.forEach((e) => { if (!e.isIntersecting) return; reveal.unobserve(e.target); const d = Math.min(stagger++, 10) * 55; clearTimeout(tmo); tmo = setTimeout(() => { stagger = 0; }, 400);
    e.target.animate([{ opacity: 0, transform: 'translateY(16px) scale(.985)' }, { opacity: 1, transform: 'none' }], { duration: 520, delay: d, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'backwards' }); }); }, { threshold: 0.08 });
  const countUp = (el) => { const t = el.textContent.trim(); const m = t.match(/^(-?\d+(?:[.,]\d+)?)(\s?(?:%|°|°C|ГБ|МБ|Вт|мс|с|шт\.?|x)?)$/); if (!m) return; const dec = (m[1].split(/[.,]/)[1] || '').length, v = parseFloat(m[1].replace(',', '.')), suf = m[2]; if (!isFinite(v) || v === 0) return;
    const t0 = performance.now(), D = 800; const f = (n) => { const k = Math.min(1, (n - t0) / D), e = 1 - Math.pow(1 - k, 3); el.textContent = (v * e).toFixed(dec).replace('.', t.includes(',') ? ',' : '.') + suf; if (k < 1) requestAnimationFrame(f); else el.textContent = t; }; requestAnimationFrame(f); };
  const cnt = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { cnt.unobserve(e.target); countUp(e.target); } }), { threshold: 0.3 });
  const scan = (root) => {
    if (off() || document.querySelector('.rz-glass')) return;
    root.querySelectorAll(CARD).forEach((el) => { if (seen.has(el)) return; seen.add(el); const r = el.getBoundingClientRect(); if (r.width < 120 || r.height < 40 || r.height > innerHeight * 1.4) return; if (el.closest('nav,header,footer,#nxdock,#nox-m-tab,.nmx')) return; el.classList.add('km-lift'); reveal.observe(el); });
    root.querySelectorAll(NUM).forEach((el) => { if (seen.has(el)) return; seen.add(el); if (el.children.length === 0 && /^-?\d/.test(el.textContent.trim())) cnt.observe(el); });
  };
  let q = 0; const sched = () => { clearTimeout(q); q = setTimeout(() => scan(document), 250); };
  new MutationObserver(sched).observe(document.body, { childList: true, subtree: true });
  addEventListener('load', () => setTimeout(() => scan(document), 400)); scan(document);
})();
