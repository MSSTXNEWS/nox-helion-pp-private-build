/* NOX presence: живой орб/HUD от mood JSON. Без CDN и зависимостей. Состояния: idle | thinking | listening | speaking.
   Источник данных: GET /presence/state (presence.py), реплики-инициативы: GET /presence/outbox + POST /presence/ack.
   API: NoxPresence.mount(el?, opts) -> {setState, setMood, setTags, setLevel, nudge, destroy}
        opts: { base:'/presence', poll:5000, onMessage(msg), autoBind:true, speakInitiatives:false }
   События: window 'nox:presence-message' {detail: msg} (msg.voice=true -> озвучить через speaker.push), 'nox:presence-state'. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(); else root.NoxPresence = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  var STATES = ['idle', 'thinking', 'listening', 'speaking'];
  var RU = { idle: 'ПОКОЙ', thinking: 'ДУМАЕТ', listening: 'СЛУШАЕТ', speaking: 'ГОВОРИТ' };
  var clamp = function (x, a, b) { return Math.max(a, Math.min(b, x)); };
  var lerp = function (a, b, t) { return a + (b - a) * t; };

  /* mood {p,a,d} (-1..1) + fears {имя:0..1} -> параметры отрисовки. Чистая функция (тестируется в node). */
  function moodToVisual(mood, fears) {
    var m = mood || {}, p = clamp(+m.p || 0, -1, 1), a = clamp(+m.a || 0, -1, 1), d = clamp(+m.d || 0, -1, 1);
    var fmax = 0, k; for (k in (fears || {})) if (fears[k] > fmax) fmax = fears[k];
    var warm = clamp((-p + 1) / 2 * 0.55 + fmax * 0.6, 0, 1);              // 0 циан .. 1 янтарь
    var cy = [127, 245, 239], am = [255, 180, 84], mg = [255, 95, 138];
    var base = [0, 1, 2].map(function (i) { return Math.round(lerp(cy[i], am[i], warm)); });
    var rgb = fmax > 0.85 ? [0, 1, 2].map(function (i) { return Math.round(lerp(base[i], mg[i], (fmax - 0.85) / 0.15)); }) : base;
    return {
      rgb: rgb,
      period: +lerp(6.5, 2.4, (a + 1) / 2).toFixed(2),                     // период «дыхания», с
      amp: +lerp(0.03, 0.09, (a + 1) / 2).toFixed(3),                      // глубина дыхания
      jitter: +clamp(fmax * 0.9 + Math.max(0, -d) * 0.3, 0, 1).toFixed(2), // дрожь контура: тревога/неуверенность
      glow: +clamp(0.45 + 0.3 * p + 0.15 * a, 0.2, 1).toFixed(2),
      fear: +fmax.toFixed(2)
    };
  }

  function stateBadge(state, label) { return (RU[state] || RU.idle) + (label ? ' · ' + String(label).toUpperCase() : ''); }

  /* Опрос без DOM: тестируется подменой fetch/timers. */
  function createPoller(o) {
    var base = o.base || '/presence', f = o.fetch, stopped = false, timer = null, fails = 0;
    function j(path, init) { return f(base + path, init).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }); }
    function tick() {
      if (stopped) return;
      j('/state').then(function (s) { fails = 0; o.onState(s); if (s.outbox > 0) return j('/outbox').then(function (b) {
        var ids = []; (b.messages || []).forEach(function (m) { ids.push(m.id); try { o.onMessage(m); } catch (e) { /* UI не должен ломать опрос */ } });
        if (ids.length) return j('/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: ids }) });
      }); }).catch(function (e) { fails++; if (o.onError) o.onError(e, fails); })
        .then(function () { if (!stopped) timer = (o.setTimeout || setTimeout)(tick, Math.min((o.poll || 5000) * Math.pow(2, Math.min(fails, 4)), 60000)); });
    }
    return {
      start: tick, stop: function () { stopped = true; if (timer && (o.clearTimeout || clearTimeout)) (o.clearTimeout || clearTimeout)(timer); },
      post: function (path, body) { return j(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }).catch(function () { return null; }); }
    };
  }

  function mount(host, opts) {
    opts = opts || {};
    if (typeof document === 'undefined') return null;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var el = document.createElement('div'); el.id = 'nox-presence'; el.className = 'npr';
    el.innerHTML = '<canvas class="npr-orb" width="160" height="160" aria-hidden="true"></canvas>' +
      '<div class="npr-badge mono" role="status" aria-live="polite"></div><div class="npr-tags" aria-live="polite"></div>';
    (host || document.body).appendChild(el);
    var cv = el.querySelector('canvas'), cx = cv.getContext('2d'), badge = el.querySelector('.npr-badge'), tagsEl = el.querySelector('.npr-tags');
    var st = { state: 'idle', mood: { p: 0.1, a: 0, d: 0.1, label: 'ровный' }, fears: {}, level: 0, vis: moodToVisual({}, {}), tgt: moodToVisual({}, {}),
               gaze: [0, 0], nudgeAt: -9, blinkAt: 8, t0: 0, raf: 0, dead: false };
    var poller = null;

    function setState(s) {
      if (STATES.indexOf(s) < 0 || s === st.state) return; st.state = s; el.setAttribute('data-state', s);
      badge.textContent = stateBadge(s, st.mood.label); el.setAttribute('aria-label', 'NOX: ' + RU[s].toLowerCase());
      window.dispatchEvent(new CustomEvent('nox:presence-state', { detail: { state: s } }));
      if (poller) poller.post('/ui', { state: s });
    }
    function setMood(m, fears) { st.mood = m || st.mood; st.fears = fears || st.fears; st.tgt = moodToVisual(st.mood, st.fears); el.style.setProperty('--npr-rgb', st.tgt.rgb.join(',')); badge.textContent = stateBadge(st.state, st.mood.label); }
    function setLevel(x) { st.level = clamp(+x || 0, 0, 1); }
    function nudge() { st.nudgeAt = (performance.now() - st.t0) / 1000; }
    function setTags(tags) {
      tagsEl.textContent = '';
      (tags || []).slice(0, 6).forEach(function (t) {
        var c = document.createElement('div'); c.className = 'npr-tag' + (t.importance >= 0.85 ? ' hot' : ''); c.setAttribute('data-id', t.id);
        var s = document.createElement('span'); s.textContent = t.text; c.appendChild(s);
        var x = document.createElement('button'); x.type = 'button'; x.className = 'npr-x'; x.setAttribute('aria-label', 'Убрать: ' + t.text); x.textContent = '×';
        x.addEventListener('click', function () { c.classList.add('gone'); if (poller) poller.post('/dismiss', { id: t.id }); setTimeout(function () { c.remove(); }, 260); });
        c.appendChild(x); tagsEl.appendChild(c);
      });
    }

    function draw(now) {
      if (st.dead) return; st.raf = requestAnimationFrame(draw);
      if (document.hidden) return;
      var t = (now - st.t0) / 1000, v = st.vis, g = st.tgt, k = 0.04, i;
      for (i = 0; i < 3; i++) v.rgb[i] += (g.rgb[i] - v.rgb[i]) * k;
      v.period += (g.period - v.period) * k; v.amp += (g.amp - v.amp) * k; v.jitter += (g.jitter - v.jitter) * k; v.glow += (g.glow - v.glow) * k;
      var W = 160, c = W / 2, rgb = v.rgb.map(Math.round).join(','), s = st.state;
      var breath = reduce ? 0 : Math.sin(t * 2 * Math.PI / v.period) * v.amp;
      var lvl = s === 'speaking' ? (st.level || (0.35 + 0.25 * Math.sin(t * 9) * Math.sin(t * 3.1))) : s === 'listening' ? st.level : 0;
      var blink = (t > st.blinkAt && t < st.blinkAt + 0.18) ? 0.55 : 1; if (t > st.blinkAt + 0.2) st.blinkAt = t + 7 + Math.random() * 6;
      var pulse = Math.max(0, 1 - (t - st.nudgeAt) / 1.2) * 0.14;
      var r = 36 * (1 + breath + lvl * 0.22 + pulse);
      cx.clearRect(0, 0, W, W);
      var gx = c + st.gaze[0], gy = c + st.gaze[1];
      var grad = cx.createRadialGradient(gx - 6, gy - 8, 2, gx, gy, r * 1.9);
      grad.addColorStop(0, 'rgba(' + rgb + ',' + (0.95 * blink) + ')'); grad.addColorStop(0.45, 'rgba(' + rgb + ',' + (0.28 * v.glow) + ')'); grad.addColorStop(1, 'rgba(' + rgb + ',0)');
      cx.fillStyle = grad; cx.beginPath(); cx.arc(gx, gy, r * 1.9, 0, 7); cx.fill();
      cx.strokeStyle = 'rgba(' + rgb + ',.85)'; cx.lineWidth = 1.2; cx.beginPath();           // контур с дрожью тревоги
      for (i = 0; i <= 64; i++) { var a = i / 64 * 2 * Math.PI, w = reduce ? 0 : v.jitter * 2.6 * Math.sin(a * 7 + t * 11) * Math.sin(a * 3 - t * 5), rr = r + w; cx[i ? 'lineTo' : 'moveTo'](gx + Math.cos(a) * rr, gy + Math.sin(a) * rr); }
      cx.closePath(); cx.stroke();
      cx.lineWidth = 1; cx.strokeStyle = 'rgba(' + rgb + ',.35)';
      if (s === 'thinking') { for (i = 0; i < 3; i++) { var a0 = t * (reduce ? 0 : 1.6) * (i % 2 ? -1 : 1) + i * 2.1; cx.beginPath(); cx.arc(c, c, 56 + i * 7, a0, a0 + 1.1); cx.stroke(); } }
      else if (s === 'listening') { cx.beginPath(); cx.arc(c, c, 56 + lvl * 14, 0, 7); cx.stroke(); cx.beginPath(); cx.arc(c, c, 64 + lvl * 22, 0, 7); cx.globalAlpha = 0.5; cx.stroke(); cx.globalAlpha = 1; }
      else if (s === 'speaking') { for (i = 0; i < 3; i++) { var ph = (t * 0.9 + i / 3) % 1; cx.globalAlpha = (1 - ph) * 0.5; cx.beginPath(); cx.arc(c, c, r + ph * 38, 0, 7); cx.stroke(); } cx.globalAlpha = 1; }
      else { cx.beginPath(); cx.arc(c, c, 56, 0, 7); cx.stroke(); }
      if (v.jitter > 0.05) { cx.strokeStyle = 'rgba(255,180,84,' + clamp(v.jitter, 0, 0.8) + ')'; cx.lineWidth = 2; cx.beginPath(); cx.arc(c, c, 72, -1.2, -1.2 + 2.2 * v.jitter); cx.stroke(); }
    }
    function onMove(e) { var b = cv.getBoundingClientRect(), dx = e.clientX - (b.left + b.width / 2), dy = e.clientY - (b.top + b.height / 2), n = Math.hypot(dx, dy) || 1, m = Math.min(6, n / 80); st.gaze = [dx / n * m, dy / n * m]; }
    if (!reduce) window.addEventListener('pointermove', onMove, { passive: true });

    var mo = null, pend = 0;
    function bind() {                                       // без правок nox-wow.js: смотрим на его DOM
      var v = document.getElementById('eVoice'), vt = v ? v.textContent : '', ns = 'idle';
      if (document.querySelector('.think')) ns = 'thinking';
      if (/ГОВОРИТ/.test(vt)) ns = 'speaking'; else if (/СЛУШАЕТ|ЗАПИСЬ/.test(vt)) ns = 'listening';
      setState(ns);
    }
    if (opts.autoBind !== false && window.MutationObserver) {
      mo = new MutationObserver(function () { if (!pend) pend = requestAnimationFrame(function () { pend = 0; bind(); }); });
      mo.observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    if (opts.base !== false && typeof fetch === 'function') {
      poller = createPoller({ base: opts.base || '/presence', poll: opts.poll || 5000, fetch: function (u, i) { return fetch(u, i); },
        onState: function (s) { setMood(s.mood, s.fears); setTags(s.tags); if (s.state && s.state !== 'idle' && st.state === 'idle') setState(s.state); },
        onMessage: function (m) { nudge(); if (opts.onMessage) opts.onMessage(m); window.dispatchEvent(new CustomEvent('nox:presence-message', { detail: m })); } });
      poller.start();
    }
    el.setAttribute('data-state', 'idle'); badge.textContent = stateBadge('idle', st.mood.label);
    st.t0 = performance.now(); st.raf = requestAnimationFrame(draw);
    return {
      setState: setState, setMood: setMood, setTags: setTags, setLevel: setLevel, nudge: nudge, el: el,
      destroy: function () { st.dead = true; cancelAnimationFrame(st.raf); if (mo) mo.disconnect(); if (poller) poller.stop(); window.removeEventListener('pointermove', onMove); el.remove(); }
    };
  }

  return { mount: mount, moodToVisual: moodToVisual, createPoller: createPoller, stateBadge: stateBadge, STATES: STATES };
});
