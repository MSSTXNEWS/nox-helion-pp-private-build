/* NOX · «вау»-навигация: снизу категории со всплывающими стеклянными неон-кнопками, сверху — системное меню.
   Подключается из nox-nav.js (import) и напрямую на страницах без него. Оригинальный док скрыт, его STOP используется. */
(function () {
  'use strict';
  if (window.__noxDockWow) return; window.__noxDockWow = 1;
  var V = './vendor/', IC = V + 'tabler-icons/icons/outline/';
  var here = location.pathname.split('/').pop() || 'index.html';
  var CATS = [
    { id: 'home', n: 'Главная', i: 'home', href: 'index.html' },
    { id: 'mind', n: 'Интеллект', i: 'brain', hue: 195, items: [['chat.html', 'Резонанс', 'message-chatbot'], ['consciousness.html', 'Сознание', 'sparkles'], ['selffeel.html', 'Самочувствие', 'heartbeat'], ['soul.html', 'Душа', 'flame'], ['organism.html', 'Организм', 'dna'], ['memory.html', 'Память', 'database']] },
    { id: 'work', n: 'Работа', i: 'briefcase', hue: 160, items: [['projects.html', 'Проекты', 'layout-kanban'], ['board.html', 'Доска', 'chalkboard'], ['calendar.html', 'Календарь', 'calendar'], ['assistant.html', 'Ассистент', 'robot'], ['constructor.html', 'Конструктор', 'puzzle'], ['widgets.html', 'Виджеты', 'layout-dashboard'], ['tools.html', 'Инструменты', 'tools']] },
    { id: 'art', n: 'Творчество', i: 'palette', hue: 290, items: [['photo.html', 'Фотостудия', 'photo-edit'], ['studio.html', 'Студия', 'brush'], ['music.html', 'Музыка', 'music'], ['effects.html', 'Эффекты', 'wand'], ['scene.html', 'Сцена', 'cube-3d-sphere'], ['tools.html#slides', 'Презентации', 'presentation'], ['tools.html#board', 'Наброски', 'pencil']] },
    { id: 'fun', n: 'Развлечения', i: 'confetti', hue: 330, items: [['cinema.html', 'Кинотеатр', 'movie'], ['tv.html', 'Проектор', 'device-tv'], ['planets.html', 'Планеты', 'planet'], ['tools.html#visual', 'Визуализатор', 'wave-sine'], ['tools.html#synth', 'Синтезатор', 'piano'], ['tools.html#globe', 'Глобус', 'world']] },
    { id: 'link', n: 'Связь', i: 'antenna', hue: 35, items: [['voice.html', 'Голос', 'microphone'], ['tools.html#voice', 'Разговор', 'messages'], ['integrations.html', 'Интеграции', 'plug-connected'], ['/drive/', 'Google Диск', 'brand-google-drive'], ['downloads.html', 'Загрузки', 'download']] }
  ];
  var SYS = [['training.html', 'Обучение'], ['growth.html', 'Рост'], ['models.html', 'Модели'], ['system.html', 'Сервер'], ['dispatcher.html', 'Диспетчер'], ['intents.html', 'Намерения'], ['install.html', 'Установка'], ['settings.html', 'Настройки'], ['about.html', 'О сборке']];

  var css = [
    '@property --nw-a{syntax:"<angle>";inherits:false;initial-value:0deg}',
    'body{padding-bottom:calc(78px + env(safe-area-inset-bottom,0px))!important}',
    '.nox-dock{display:none!important}',
    '.nw-dock{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(10px + env(safe-area-inset-bottom,0px));z-index:9998;display:flex;gap:8px;padding:7px 10px;border-radius:20px;',
    ' background:rgba(8,12,22,.5);border:1px solid rgba(140,190,255,.18);backdrop-filter:blur(18px) saturate(160%);-webkit-backdrop-filter:blur(18px) saturate(160%);box-shadow:0 10px 40px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.07)}',
    '.nw-cat{position:relative}',
    '.nw-btn{--h:195;position:relative;display:flex;flex-direction:column;align-items:center;gap:3px;min-width:74px;padding:8px 10px 6px;border-radius:14px;cursor:pointer;color:#e6f1ff;text-decoration:none;font:600 11px/1.1 system-ui,sans-serif;letter-spacing:.06em;text-transform:uppercase;',
    ' background:linear-gradient(160deg,hsla(var(--h),90%,60%,.16),rgba(10,14,26,.35));border:1px solid hsla(var(--h),90%,70%,.25);isolation:isolate;overflow:hidden;transition:transform .2s,box-shadow .2s}',
    '.nw-btn::before{content:"";position:absolute;inset:-1px;border-radius:inherit;padding:1px;background:conic-gradient(from var(--nw-a),transparent 0 70%,hsl(var(--h),100%,70%) 80%,#fff 84%,hsl(calc(var(--h) + 60),100%,65%) 88%,transparent 94%);',
    ' -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;animation:nw-spin 3.6s linear infinite;opacity:.85;z-index:-1}',
    '.nw-btn::after{content:"";position:absolute;top:0;left:-60%;width:40%;height:100%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.28),transparent);transform:skewX(-20deg);animation:nw-sweep 4.5s ease-in-out infinite;pointer-events:none}',
    '.nw-btn img{width:22px;height:22px;filter:invert(1) drop-shadow(0 0 6px hsl(var(--h),100%,65%)) drop-shadow(0 0 12px hsla(var(--h),100%,60%,.6));animation:nw-glow 2.8s ease-in-out infinite}',
    '.nw-btn:hover,.nw-cat.open>.nw-btn{transform:translateY(-3px);box-shadow:0 0 18px hsla(var(--h),100%,60%,.55),0 0 42px hsla(var(--h),100%,60%,.25)}',
    '.nw-btn[aria-current=page]{box-shadow:0 0 14px hsla(var(--h),100%,60%,.6);border-color:hsla(var(--h),100%,75%,.6)}',
    '.nw-stop{--h:350}.nw-stop img{filter:invert(1) drop-shadow(0 0 8px #ff4d6d)}',
    '.nw-pop{position:absolute;left:50%;bottom:calc(100% + 12px);transform:translateX(-50%) translateY(8px) scale(.96);opacity:0;pointer-events:none;transition:opacity .18s,transform .22s cubic-bezier(.2,.9,.3,1.3);',
    ' display:grid;grid-template-columns:repeat(2,minmax(128px,1fr));gap:8px;padding:10px;border-radius:18px;background:rgba(8,12,22,.62);border:1px solid rgba(140,190,255,.2);backdrop-filter:blur(20px) saturate(170%);-webkit-backdrop-filter:blur(20px) saturate(170%);box-shadow:0 18px 60px rgba(0,0,0,.6)}',
    '.nw-cat.open .nw-pop{opacity:1;pointer-events:auto;transform:translateX(-50%) translateY(0) scale(1)}',
    '.nw-pop::after{content:"";position:absolute;left:0;right:0;top:100%;height:14px}',
    '.nw-pop .nw-btn{flex-direction:row;justify-content:flex-start;gap:9px;min-width:0;padding:10px 12px;font-size:12px;letter-spacing:.03em;text-transform:none;opacity:0;transform:translateY(6px)}',
    '.nw-cat.open .nw-pop .nw-btn{opacity:1;transform:none;transition:opacity .25s,transform .3s;transition-delay:calc(var(--i)*35ms)}',
    '.nw-pop .nw-btn img{width:20px;height:20px}',
    '.nw-top{display:flex;gap:2px;flex-wrap:wrap}',
    '.nw-top a{color:#bcd3ee;text-decoration:none;font:600 11px/1 system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;padding:8px 10px;border-radius:9px;transition:color .15s,background .15s,text-shadow .15s}',
    '.nw-top a:hover,.nw-top a[aria-current=page]{color:#fff;background:rgba(124,200,255,.1);text-shadow:0 0 10px rgba(124,200,255,.8)}',
    '.nw-topbar{position:fixed;top:0;left:0;right:0;z-index:9998;display:flex;align-items:center;gap:14px;padding:6px 14px;background:rgba(6,9,18,.55);border-bottom:1px solid rgba(140,190,255,.14);backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%)}',
    '.nw-brand{color:#e6f1ff;text-decoration:none;font:700 12px/1 system-ui,sans-serif;letter-spacing:.32em;text-shadow:0 0 12px rgba(124,200,255,.7)}',
    'body.nw-has-top{padding-top:44px!important}',
    '@media (max-width:760px){.nw-topbar{overflow-x:auto}.nw-top{flex-wrap:nowrap}}',
    '@keyframes nw-spin{to{--nw-a:360deg}}',
    '@keyframes nw-sweep{0%,55%{left:-60%}85%,100%{left:140%}}',
    '@keyframes nw-glow{0%,100%{opacity:.85}50%{opacity:1;transform:scale(1.06)}}',
    '@media (max-width:760px){.nw-dock{left:6px;right:6px;transform:none;justify-content:space-between;gap:4px;padding:6px}.nw-btn{min-width:0;flex:1;padding:7px 4px;font-size:9px}.nw-pop{grid-template-columns:1fr 1fr;position:fixed;left:8px;right:8px;transform:translateY(8px);bottom:84px}.nw-cat.open .nw-pop{transform:none}}',
    '@media (prefers-reduced-motion:reduce){.nw-btn::before,.nw-btn::after,.nw-btn img{animation:none}}'
  ].join('');
  var st = document.createElement('style'); st.id = 'nw-css'; st.textContent = css; document.head.appendChild(st);

  function isCur(h) { var f = h.split('#')[0].split('/').pop(); return f && f === here; }
  function btn(tag, href, label, icon, hue, extra) {
    var a = document.createElement(tag); a.className = 'nw-btn' + (extra ? ' ' + extra : ''); if (href) a.href = href.charAt(0) === '/' ? href : './' + href;
    if (hue != null) a.style.setProperty('--h', hue);
    a.innerHTML = '<img alt="" src="' + IC + icon + '.svg"><span>' + label + '</span>';
    if (href && isCur(href)) a.setAttribute('aria-current', 'page'); return a;
  }
  function buildDock() {
    var d = document.createElement('nav'); d.className = 'nw-dock'; d.setAttribute('aria-label', 'Разделы NOX');
    CATS.forEach(function (c) {
      var w = document.createElement('div'); w.className = 'nw-cat';
      if (!c.items) { w.appendChild(btn('a', c.href, c.n, c.i, 210)); d.appendChild(w); return; }
      var b = btn('button', null, c.n, c.i, c.hue); b.type = 'button'; b.setAttribute('aria-haspopup', 'true');
      if (c.items.some(function (x) { return isCur(x[0]); })) b.setAttribute('aria-current', 'page');
      var pop = document.createElement('div'); pop.className = 'nw-pop';
      c.items.forEach(function (x, k) { var a = btn('a', x[0], x[1], x[2], c.hue + k * 12); a.style.setProperty('--i', k); pop.appendChild(a); });
      w.appendChild(b); w.appendChild(pop); d.appendChild(w);
      var t = 0; function open() { clearTimeout(t); document.querySelectorAll('.nw-cat.open').forEach(function (o) { if (o !== w) o.classList.remove('open'); }); w.classList.add('open'); }
      function shut() { t = setTimeout(function () { w.classList.remove('open'); }, 220); }
      w.addEventListener('mouseenter', open); w.addEventListener('mouseleave', shut);
      b.addEventListener('click', function () { w.classList.contains('open') ? w.classList.remove('open') : open(); });
      if (window.VanillaTilt) window.VanillaTilt.init(pop.querySelectorAll('.nw-btn'), { max: 12, speed: 400, glare: true, 'max-glare': .25, scale: 1.04 });
    });
    var sw = document.createElement('div'); sw.className = 'nw-cat'; var sb = btn('button', null, 'Стоп', 'player-stop', 350, 'nw-stop'); sb.type = 'button'; sb.title = 'Остановить NOX';
    sb.onclick = function () { var o = document.querySelector('.nox-dock .nox-stopbtn'); if (o) o.click(); else fetch('/api/chat/stop', { method: 'POST' }).catch(function () {}); };
    sw.appendChild(sb); d.appendChild(sw);
    document.addEventListener('click', function (e) { if (!e.target.closest('.nw-cat')) document.querySelectorAll('.nw-cat.open').forEach(function (o) { o.classList.remove('open'); }); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') document.querySelectorAll('.nw-cat.open').forEach(function (o) { o.classList.remove('open'); }); });
    document.body.appendChild(d);
  }
  function buildTop() {
    var bar = document.querySelector('.bar'); if (!bar) return false;
    var links = Array.prototype.filter.call(bar.querySelectorAll('a[href]'), function (a) { return /\.html(\?|#|$)/.test(a.getAttribute('href')) && !/index\.html/.test(a.getAttribute('href')) || /ГЛАВНАЯ|РЕЗОНАНС|ПРОЕКТЫ/i.test(a.textContent); });
    if (!links.length) return false;
    var host = links[0].parentElement; if (host.querySelector('.nw-top')) return true;
    var nav = document.createElement('nav'); nav.className = 'nw-top'; nav.setAttribute('aria-label', 'Система');
    SYS.forEach(function (s) { var a = document.createElement('a'); a.href = './' + s[0]; a.textContent = s[1]; if (isCur(s[0])) a.setAttribute('aria-current', 'page'); nav.appendChild(a); });
    links.forEach(function (a) { a.style.display = 'none'; });
    host.insertBefore(nav, host.firstChild); return true;
  }
  function topFallback() {
    if (document.querySelector('.nw-topbar')) return;
    var t = document.createElement('header'); t.className = 'nw-topbar';
    t.innerHTML = '<a class="nw-brand" href="./index.html">NOX HELION</a>';
    var nav = document.createElement('nav'); nav.className = 'nw-top'; nav.setAttribute('aria-label', 'Система');
    SYS.forEach(function (s) { var a = document.createElement('a'); a.href = './' + s[0]; a.textContent = s[1]; if (isCur(s[0])) a.setAttribute('aria-current', 'page'); nav.appendChild(a); });
    t.appendChild(nav); document.body.appendChild(t); document.body.classList.add('nw-has-top');
  }
  function loadTilt(cb) { if (window.VanillaTilt) return cb(); var s = document.createElement('script'); s.src = V + 'nox-x/fx2/vanilla-tilt.min.js'; s.onload = cb; s.onerror = cb; document.head.appendChild(s); }
  function go() { loadTilt(buildDock); var n = 0; (function tryTop() { if (buildTop()) return; if (n++ < 12) setTimeout(tryTop, 150); else topFallback(); })(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
})();
