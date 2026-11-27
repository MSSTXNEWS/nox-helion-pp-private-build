/* NOX · JARVIS KIT: переиспользуемые компоненты поверх NOXjv (nox-jarvis.js): ring, bars, spectrum, checklist, kv, dock, orbState.
   Каждый компонент берёт данные из NOXjv.on (нет данных -> HOLD), ничего не рисует сам по себе. Подключать ПОСЛЕ nox-jarvis.js. */
(function () {
  'use strict';
  var J = window.NOXjv; if (!J) return; var NS = 'http://www.w3.org/2000/svg', RM = J.RM, DEMO = J.DEMO;
  function sv(t, a, p) { var e = document.createElementNS(NS, t); for (var k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
  /* ---- круговой индикатор: <div class="jv-ring" data-key="gpu_util_pct" data-label="GPU" data-max="100" data-unit="%"> ---- */
  J.ring = function (el, key, label, max, unit) {
    key = key || el.dataset.key; label = label || el.dataset.label || ''; max = +(max || el.dataset.max || 100); unit = unit != null ? unit : (el.dataset.unit || '%');
    var s = sv('svg', { viewBox: '0 0 100 100', 'aria-hidden': 'true' }); el.textContent = ''; el.appendChild(s);
    var R = 38, L = 2 * Math.PI * R, ticks = sv('g', { class: 'tk' }, s);
    for (var i = 0; i < 40; i++) { var a = i / 40 * 2 * Math.PI, r1 = 46, r2 = i % 5 ? 44.2 : 43; sv('line', { x1: 50 + Math.cos(a) * r1, y1: 50 + Math.sin(a) * r1, x2: 50 + Math.cos(a) * r2, y2: 50 + Math.sin(a) * r2 }, ticks); }
    sv('circle', { class: 'tr', cx: 50, cy: 50, r: R }, s); var pg = sv('circle', { class: 'pg', cx: 50, cy: 50, r: R, 'stroke-dasharray': L, 'stroke-dashoffset': L, transform: 'rotate(-90 50 50)' }, s);
    var tv = sv('text', { class: 'v', x: 50, y: 52, 'text-anchor': 'middle' }, s), tl = sv('text', { class: 'l', x: 50, y: 66, 'text-anchor': 'middle' }, s); tl.textContent = label;
    el.setAttribute('role', 'img'); J.on(function (c) { var v = c[key], ok = v != null; el.classList.toggle('hold', !ok); tv.textContent = ok ? Math.round(v) + unit : 'HOLD'; pg.setAttribute('stroke-dashoffset', ok ? L * (1 - Math.max(0, Math.min(1, v / max))) : L); el.setAttribute('aria-label', label + ': ' + (ok ? Math.round(v) + unit : 'нет данных')); });
    return el;
  };
  /* ---- гистограмма (CSS, без библиотек): history ключа -> столбики ---- */
  J.bars = function (el, key, max, n) {
    n = n || 24; max = max || 100; el.textContent = ''; var cols = []; for (var i = 0; i < n; i++) { var b = document.createElement('i'); el.appendChild(b); cols.push(b); }
    J.on(function () { var d = (J.hist[key] || []).slice(-n), ok = d.length > 1; el.classList.toggle('hold', !ok); cols.forEach(function (b, i) { var v = d[i - (n - d.length)]; b.style.height = (ok && v != null ? Math.max(4, Math.min(100, v / max * 100)) : 4) + '%'; }); el.setAttribute('role', 'img'); el.setAttribute('aria-label', key + (ok ? '' : ': нет данных')); });
    return el;
  };
  /* ---- спектр голоса: AnalyserNode из NOXjv.mic.an (кнопка микрофона у J.wave); без него HOLD, в демо синтетика с меткой ---- */
  J.spectrum = function (cv) {
    var g = cv.getContext('2d'), T = 0, N = 32, sm = new Float32Array(N);
    function fit() { var r = cv.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2); cv.width = Math.max(1, r.width * d); cv.height = Math.max(1, r.height * d); g.setTransform(d, 0, 0, d, 0, 0); } fit(); addEventListener('resize', fit);
    function draw() { var w = cv.clientWidth, h = cv.clientHeight; g.clearRect(0, 0, w, h); var an = J.mic.an, live = !!an, buf = null; if (live) { buf = new Uint8Array(an.frequencyBinCount); an.getByteFrequencyData(buf); }
      var bw = w / N; for (var i = 0; i < N; i++) { var v; if (live) v = buf[Math.floor(Math.pow(i / N, 1.6) * buf.length * .5)] / 255; else if (DEMO) v = .18 + .6 * Math.abs(Math.sin(i * .35 + T * 2.2) * Math.sin(i * .11 - T * .8)); else v = 0; sm[i] += (v - sm[i]) * .35;
        var bh = Math.max(2, sm[i] * (h - 4)); var gr = g.createLinearGradient(0, h, 0, h - bh); gr.addColorStop(0, 'rgba(0,214,255,.15)'); gr.addColorStop(1, live || DEMO ? 'rgba(0,214,255,.95)' : 'rgba(111,163,184,.5)'); g.fillStyle = gr; g.fillRect(i * bw + 1.5, h - bh, Math.max(1, bw - 3), bh); }
      g.fillStyle = '#6fa3b8'; g.font = '600 10px ui-monospace,monospace'; if (!live && !DEMO) g.fillText('HOLD', 6, 12); else if (!live && DEMO) { g.fillStyle = '#ffaa3c'; g.fillText('ДЕМО', w - 34, 12); } }
    function loop(t) { T = t / 1000; if (!document.hidden) draw(); if (!RM) requestAnimationFrame(loop); } requestAnimationFrame(loop); if (RM) draw(); return cv;
  };
  /* ---- список задач с чекбоксами (цель >=44px): items или повестка /api/nox/agenda; отметка хранится локально ---- */
  var DK = 'nox.jv.done'; function done() { try { return JSON.parse(localStorage.getItem(DK) || '{}'); } catch (e) { return {}; } }
  J.checklist = function (ul, items) {
    function render(list) { ul.textContent = ''; var dn = done();
      if (!list.length) { var h = document.createElement('li'); h.className = 'hold'; h.textContent = 'HOLD: повестка недоступна'; ul.appendChild(h); return; }
      list.slice(0, 6).forEach(function (t, i) { var id = 't' + i + String(t).length, li = document.createElement('li'), lb = document.createElement('label'), cb = document.createElement('input'), sp = document.createElement('span'); cb.type = 'checkbox'; cb.checked = !!dn[id]; sp.textContent = String(t).slice(0, 48);
        cb.addEventListener('change', function () { var d = done(); d[id] = cb.checked; try { localStorage.setItem(DK, JSON.stringify(d)); } catch (e) {} li.classList.toggle('dn', cb.checked); }); li.classList.toggle('dn', cb.checked); lb.appendChild(cb); lb.appendChild(sp); li.appendChild(lb); ul.appendChild(li); }); }
    if (items) { render(items); return ul; }
    J.on(function (c, a) { render(a && Array.isArray(a.ideas) ? a.ideas.filter(function (i) { return i && i.title && !/done|closed|reject|dismiss/i.test(String(i.status || '')); }).map(function (i) { return i.title; }) : []); }); return ul;
  };
  /* ---- ключ-значение: [[подпись, ключ, единица]] ---- */
  J.kv = function (box, defs) { box.textContent = ''; var vs = defs.map(function (d) { var r = document.createElement('div'), k = document.createElement('span'), v = document.createElement('b'); k.textContent = d[0]; r.appendChild(k); r.appendChild(v); box.appendChild(r); return v; });
    J.on(function (c) { defs.forEach(function (d, i) { var v = c[d[1]]; vs[i].textContent = v == null ? 'HOLD' : Math.round(v) + (d[2] || ''); vs[i].classList.toggle('hold', v == null); }); }); return box; };
  /* ---- док: кнопки с aria-pressed, одна активна; onSelect(name) ---- */
  J.dock = function (nav, onSelect) { nav.querySelectorAll('.jv-btn').forEach(function (b) { b.setAttribute('aria-pressed', b.classList.contains('on') ? 'true' : 'false'); b.addEventListener('click', function () { nav.querySelectorAll('.jv-btn').forEach(function (x) { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); }); b.classList.add('on'); b.setAttribute('aria-pressed', 'true'); onSelect && onSelect(b.dataset.name || b.textContent.trim()); }); }); return nav; };
  /* ---- состояния сферы: idle|listen|think|speak -> метка + пульс сферы (J.pulse задаёт core()) ---- */
  J.orbState = function (labelEl, st) { var M = { idle: ['ОЖИДАНИЕ', 0], listen: ['СЛУШАЕТ', .35], think: ['ДУМАЕТ', .55], speak: ['ГОВОРИТ', .8] }, m = M[st] || M.idle; if (labelEl) labelEl.textContent = m[0]; if (J.pulse) J.pulse(m[1]); };
})();
