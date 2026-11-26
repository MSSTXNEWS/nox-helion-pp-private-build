/* NOX · Резонанс: «вау»-адаптер. Тонкий слой: фон-аврора, text reveal (Motion), spotlight/beam/дыхание в Shadow DOM Deep Chat. Откат ?wow=0 */
(function () {
  'use strict';
  if (/[?&]wow=0/.test(location.search)) return;
  var RM = matchMedia('(prefers-reduced-motion: reduce)').matches, SM = innerWidth < 700;
  var dc = document.querySelector('deep-chat'); if (!dc) return;
  var ab = document.createElement('div'); ab.className = 'nxw-aurora'; ab.setAttribute('aria-hidden', 'true'); ab.innerHTML = '<i></i><i></i><i></i>'; document.body.insertBefore(ab, document.body.firstChild);
  var SH = '' +
    /* убираем горизонтальную полосу под полем ввода (виновник: #text-input-container overflow:auto при ширине призрака) */
    '#text-input-container{overflow:hidden!important;position:relative}#text-input{overflow-x:hidden!important}' +
    /* цели 44 px */
    'div[style*="clamp(30px"]{font-size:clamp(34px,4.4vw,64px)!important;letter-spacing:-.03em!important}@media(min-width:1000px){.deep-chat-suggestion-button{min-height:64px!important;font-size:16px!important}}' +
    '#microphone-button,#submit-icon-container,#upload-mixed-files-icon-container,.input-button,.dc-seg button{min-width:44px;min-height:44px}.dc-seg button{height:44px!important;min-height:44px!important}' +
    /* дыхание поля ввода + луч */
    '@keyframes nxwb{0%,100%{opacity:.35;transform:scale(1)}50%{opacity:.85;transform:scale(1.012)}}' +
    '#text-input-container::before{content:"";position:absolute;inset:-6px;border-radius:20px;z-index:-1;pointer-events:none;background:radial-gradient(60% 120% at 50% 50%,rgba(var(--nxw-rgb,157,177,209),.22),transparent 75%);animation:nxwb 5.5s ease-in-out infinite;will-change:opacity,transform}' +
    '#text-input-container:focus-within::before{opacity:1!important;animation:none}' +
    '#text-input-container::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;border:1px solid transparent;-webkit-mask-clip:padding-box,border-box;mask-clip:padding-box,border-box;-webkit-mask-composite:intersect;mask-composite:intersect;-webkit-mask-image:linear-gradient(transparent,transparent),linear-gradient(#000,#000);mask-image:linear-gradient(transparent,transparent),linear-gradient(#000,#000);background:conic-gradient(from var(--nxw-a,0deg),transparent 0 72%,rgba(var(--nxw-rgb,157,177,209),.95) 100%);animation:nxwr 7s linear infinite}@keyframes nxwr{to{--nxw-a:360deg}}' +
    /* плитки: spotlight по курсору */
    '.deep-chat-suggestion-button{position:relative;overflow:hidden;isolation:isolate;transition:transform .2s,border-color .2s}.deep-chat-suggestion-button:hover{transform:translateY(-2px);border-color:rgba(var(--nxw-rgb,157,177,209),.55)!important}' +
    '.deep-chat-suggestion-button::before{content:"";position:absolute;inset:0;z-index:-1;opacity:0;transition:opacity .25s;background:radial-gradient(200px circle at var(--mx,50%) var(--my,50%),rgba(var(--nxw-rgb,157,177,209),.24),transparent 70%)}.deep-chat-suggestion-button:hover::before{opacity:1}' +
    '.nxw-w{display:inline-block;background:linear-gradient(180deg,#fff,rgba(var(--nxw-rgb,157,177,209),.9));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;will-change:transform,opacity,filter}' +
    '@media(max-width:700px){div[style*="repeat(auto-fit"]{grid-template-columns:1fr 1fr!important;gap:8px!important;margin-top:14px!important}.deep-chat-suggestion-button{font-size:14px!important;padding:8px 12px!important}.dc-seg{display:none}#text-input-container::before{animation:none;opacity:.5}.deep-chat-suggestion-button{min-height:48px!important}}' +
    '@media(prefers-reduced-motion:reduce){#text-input-container::before{animation:none;opacity:.5}.deep-chat-suggestion-button{transition:none}}';
  var beamCSS = RM || SM ? '#text-input-container::after{display:none}' : '';
  function rgbVars() { var cs = getComputedStyle(document.documentElement), v = cs.getPropertyValue('--nxw-rgb').trim(); return v; }
  function inject(sr) {
    if (sr.getElementById && sr.getElementById('nxwow')) return true;
    var s = document.createElement('style'); s.id = 'nxwow'; s.textContent = ':host{--nxw-rgb:' + (rgbVars() || '157,177,209') + '}' + SH + beamCSS; sr.appendChild(s); return true;
  }
  /* text reveal: слова Motion (stagger), старт с opacity .01 чтобы не задерживать LCP */
  function reveal(sr) {
    var t = sr.querySelector('div[style*="font-size:clamp(30px"]'); if (!t || t.dataset.nxw) return; t.dataset.nxw = '1';
    var words = t.textContent.trim().split(/\s+/); t.textContent = '';
    var sp = words.map(function (w, i) { var s = document.createElement('span'); s.className = 'nxw-w'; s.textContent = w; t.appendChild(s); if (i < words.length - 1) t.appendChild(document.createTextNode(' ')); return s; });
    var M = window.Motion;
    if (RM) return;
    if (M && M.animate && M.stagger) { sp.forEach(function (s) { s.style.opacity = '.01'; }); M.animate(sp, { opacity: [0.01, 1], y: [18, 0], filter: ['blur(10px)', 'blur(0px)'] }, { duration: 0.7, delay: M.stagger(0.09), ease: [0.22, 1, 0.36, 1] }); }
    else sp.forEach(function (s, i) { s.animate([{ opacity: .01, transform: 'translateY(18px)', filter: 'blur(10px)' }, { opacity: 1, transform: 'none', filter: 'blur(0)' }], { duration: 700, delay: i * 90, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'backwards' }); });
    var sub = t.nextElementSibling; if (sub && sub.animate) sub.animate([{ opacity: .01, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: 700, delay: 350 + words.length * 90, easing: 'ease-out', fill: 'backwards' });
  }
  /* spotlight: --mx/--my по pointermove (rAF) */
  function spot(root, sel) {
    var raf = 0, ev;
    root.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return; ev = e; if (raf) return;
      raf = requestAnimationFrame(function () { raf = 0; var el = ev.target.closest && ev.target.closest(sel); if (!el) return; var r = el.getBoundingClientRect(); el.style.setProperty('--mx', (ev.clientX - r.left) + 'px'); el.style.setProperty('--my', (ev.clientY - r.top) + 'px'); });
    }, { passive: true });
  }
  function wire() {
    var sr = dc.shadowRoot; if (!sr) return false;
    inject(sr); reveal(sr);
    if (!sr.__nxws) { sr.__nxws = 1; spot(sr, '.deep-chat-suggestion-button'); }
    return true;
  }
  var n = 0; (function tick() { var ok = wire(); if (++n < 40) setTimeout(tick, ok ? 600 : 150); })();
  var mo = 0; try { mo = new MutationObserver(function () { var sr = dc.shadowRoot; if (sr) { reveal(sr); } }); dc.shadowRoot && mo.observe(dc.shadowRoot, { childList: true, subtree: true }); } catch (e) {}
  spot(document.body, '.nxw-spot');


  /* общий wow-слой проекта грузим после load в простое: LCP не страдает */
  function lazy() {
    function css(h) { var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.appendChild(l); }
    function js(s, mod, attr) { var e = document.createElement('script'); e.src = s; if (mod) e.type = 'module'; else e.defer = true; if (attr) e.setAttribute(attr, '1'); document.head.appendChild(e); }
    css('./nox-wow-max.css'); js('./nox-wow-max.js', 0, 'data-nox-wow-max'); js('nox-fastwow/nox-fastwow.js', 0, 'data-nox-fastwow'); js('./nox-select-tiles.js'); js('./nox-fx.js', 1);
  }
  function whenIdle() { (window.requestIdleCallback || function (f) { setTimeout(f, 600); })(lazy, { timeout: 2500 }); }
  if (document.readyState === 'complete') whenIdle(); else addEventListener('load', whenIdle, { once: true });
  /* FASTWOW (index): общий фон nox-wow-max (Canvas2D частицы/свечение) вместо пепла nox-fx; док FASTWOW переносим наверх и красим в графит */
  var FW = '.nfx-dock{bottom:auto!important;top:calc(60px + env(safe-area-inset-top,0px))!important;border-color:rgba(255,255,255,.14)!important;background:rgba(24,25,27,.72)!important;box-shadow:0 8px 25px #0006!important}.nfx-dock button,.nfx-panel button{min-height:44px;min-width:44px;background:rgba(255,255,255,.06)!important;color:#edeef0!important;border-color:rgba(255,255,255,.14)!important}.nfx-dock button:hover,.nfx-panel button:hover{background:rgba(255,255,255,.14)!important}.nfx-dock .primary{background:rgba(var(--gx-acc-rgb,157,177,209),.22)!important;border-color:rgba(var(--gx-acc-rgb,157,177,209),.6)!important}';
  function fw() { var h = document.getElementById('nox-fastwow-host'), sr = h && h.shadowRoot; if (!sr) return false; if (!sr.getElementById('nxwfw')) { var s = document.createElement('style'); s.id = 'nxwfw'; s.textContent = FW; sr.appendChild(s); } return true; }
  var fn = 0; (function t() { if (!fw() && ++fn < 40) setTimeout(t, 400); })();
  var kn = 0; (function k() { var a = document.getElementById('nox-fx-ash'); try { if (a && window.tsParticles && tsParticles.items && tsParticles.items.length) { tsParticles.items.slice().forEach(function (c) { c.destroy(); }); a.remove(); return; } } catch (e) {} if (++kn < 30) setTimeout(k, 1000); })();
  /* HUD Arwes (vendor/nox-fx/hud.js, createFrame): уголки на панелях, цвет графит */
  if (!RM && !SM) setTimeout(function () {
    var cards = document.querySelectorAll('#dcFill sl-card'); if (!cards.length) return;
    cards.forEach(function (c) { if (c.querySelector('svg.nxw-hud')) return; var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('class', 'nxw-hud'); s.setAttribute('aria-hidden', 'true'); c.appendChild(s); });
    import(new URL('./vendor/nox-fx/hud.js', location.href).href).then(function (m) {
      m.hud('svg.nxw-hud'); document.querySelectorAll('svg.nxw-hud').forEach(function (s) { s.style.setProperty('--arwes-frames-line-color', 'rgba(var(--gx-acc-rgb,157,177,209),.55)'); });
    }).catch(function () {});
  }, 2500);
  window.NOXdcWow = { wire: wire };
})();
