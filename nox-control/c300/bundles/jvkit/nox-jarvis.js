/*nox-credfix*/(function(){if(window.__noxCred)return;window.__noxCred=1;var f=window.fetch;window.fetch=function(u,o){try{if(typeof u==="string"&&u.charAt(0)==="/"&&u.charAt(1)!=="/")u=location.origin+u;}catch(e){}return f.call(this,u,o)};})();
/* NOX · дизайн-система JARVIS: данные (/api/nox-live, /api/nox/agenda, /api/nox/status), gauge/графики ECharts, волна микрофона, рамки Arwes, GSAP-появление.
   Правило: нет данных -> HOLD. ?demo=1 только для скриншотов (метка ДЕМО). */
(function () {
  'use strict';
  var Q = new URLSearchParams(location.search), DEMO = Q.has('demo'), RM = matchMedia('(prefers-reduced-motion: reduce)').matches, SM = innerWidth < 900;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  function flat(o, p, out) { out = out || {}; for (var k in o || {}) { var v = o[k], n = p ? p + '_' + k : k; if (typeof v === 'number' && isFinite(v)) out[n] = v; else if (v && typeof v === 'object' && !Array.isArray(v) && (p || '').split('_').length < 3) flat(v, n, out); } return out; } /* gpu.util_pct -> gpu_util_pct (имена ключей проверены на сервере) */
  var H = { gpu_util_pct: [], gpu_vram_pct: [], gpu_temp_c: [], gpu_power_w: [] }, cur = {}, subs = [], agenda = null, status = null;
  var J = { DEMO: DEMO, RM: RM, SM: SM, mic: { level: 0, on: false }, hist: H };
  function demoSeed() { for (var i = 0; i < 40; i++) { H.gpu_util_pct.push(48 + 22 * Math.sin(i / 4) + 6 * Math.sin(i * 1.7)); H.gpu_vram_pct.push(38 + 8 * Math.sin(i / 7 + 1)); H.gpu_temp_c.push(56 + 4 * Math.sin(i / 5)); H.gpu_power_w.push(190 + 40 * Math.sin(i / 3)); } cur = { gpu_util_pct: 63, gpu_vram_pct: 41, gpu_temp_c: 58, gpu_power_w: 212, ram_used_pct: 47, disk_used_pct: 61 }; agenda = { ideas: [{ title: 'Свести отчёт по обучению', status: 'open' }, { title: 'Проверить голосовой ввод', status: 'open' }, { title: 'Разобрать входящие', status: 'new' }, { title: 'Обновить датасет', status: 'open' }] }; status = { services: { chat: { up: true }, bridge: { up: true }, memory: { up: true }, training: { up: true }, voice: { up: false } } }; }
  function emit() { subs.forEach(function (f) { try { f(cur, agenda, status); } catch (e) {} }); }
  function jget(u) { return fetch(u, { cache: 'no-store', credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw 0; return r.json(); }); }
  function poll() {
    jget('/api/nox-live').then(function (j) { cur = flat(j, ''); if (cur.ram_total_gb && cur.ram_avail_gb != null) cur.ram_used_pct = Math.max(0, 100 * (1 - cur.ram_avail_gb / cur.ram_total_gb)); for (var k in H) if (cur[k] != null) { H[k].push(cur[k]); if (H[k].length > 40) H[k].shift(); } }).catch(function () { cur = {}; }).then(function () { return jget('/api/nox/agenda').then(function (j) { agenda = j && !j.hold ? j : null; }).catch(function () { agenda = null; }); })
      .then(function () { return jget('/api/nox/status').then(function (j) { status = j; }).catch(function () { status = null; }); }).then(emit);
  }
  J.get = jget; J.flat = flat;
  J.on = function (f) { subs.push(f); f(cur, agenda, status); };
  J.start = function () { if (DEMO) { demoSeed(); emit(); } else { poll(); setInterval(poll, 10000); } var d = $('#jvDemo'); if (d) d.hidden = !DEMO; };
  /* ---- рамки: Arwes createFrame из vendor/arwes-frames ---- */
  J.frames = function (root) {
    (root || document).querySelectorAll('.jv-f').forEach(function (f) { if (f.querySelector(':scope>svg.jv-hudf')) return; var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('class', 'jv-hudf'); s.setAttribute('aria-hidden', 'true'); f.appendChild(s); });
    if (SM && !Q.has('hud')) return;
    /* Arwes: vendor/arwes-frames (реальная сборка @arwes/frames), вариант рамки в data-jv-frame: corners|octagon|kranox|nefrex|lines|underline|nero|header|circle */
    import(new URL('./vendor/arwes-frames/arwes-frames.esm.js', location.href).href).then(function (m) {
      var mk = { corners: function () { return m.createFrameCornersSettings({ styled: true, padding: 1, strokeWidth: 1, cornerLength: 12 }); }, octagon: function () { return m.createFrameOctagonSettings({ styled: true, padding: 1, strokeWidth: 1, squareSize: 12 }); }, kranox: function () { return m.createFrameKranoxSettings({ styled: true, padding: 1, strokeWidth: 1, squareSize: 12 }); }, nefrex: function () { return m.createFrameNefrexSettings({ styled: true, padding: 1, strokeWidth: 1, squareSize: 10, smallLineLength: 10, largeLineLength: 40 }); }, lines: function () { return m.createFrameLinesSettings({ styled: true, padding: 1, largeLineWidth: 2, smallLineWidth: 1, smallLineLength: 14 }); }, underline: function () { return m.createFrameUnderlineSettings({ styled: true, padding: 1, strokeWidth: 1, squareSize: 10 }); }, nero: function () { return m.createFrameNeroSettings({ styled: true, padding: 1, cornerLength: 14, cornerWidth: 2 }); }, header: function () { return m.createFrameHeaderSettings({ styled: true, padding: 1, strokeWidth: 1, decoWidth: 24, contentLength: 120 }); }, circle: function () { return m.createFrameCircleSettings({ styled: true, padding: 1, strokeWidth: 1 }); } };
      (root || document).querySelectorAll('svg.jv-hudf').forEach(function (s) {
        if (s.__jvArwes) return; s.__jvArwes = 1; var v = (s.parentNode && s.parentNode.getAttribute('data-jv-frame')) || 'corners';
        s.style.setProperty('--arwes-frames-line-color', 'rgba(0,214,255,.95)'); s.style.setProperty('--arwes-frames-bg-color', 'transparent'); s.style.setProperty('--arwes-frames-deco-color', 'rgba(127,233,255,1)'); s.style.color = '#00d6ff';
        try { m.createFrame(s, (mk[v] || mk.corners)()); } catch (e) { console.warn('[jv] arwes frame', v, e); }
      });
    }).catch(function () {});
  };
  /* ---- gauge ---- */
  var C = '#00d6ff';
  J.gauge = function (el, key, label, max, unit) {
    if (!window.echarts) return; var ch = echarts.init(el, null, { renderer: 'canvas' }); var small = SM;
    function draw(c) { var v = c[key], ok = v != null; ch.setOption({ animationDurationUpdate: 600, series: [{ type: 'gauge', startAngle: 220, endAngle: -40, min: 0, max: max, radius: '92%', center: ['50%', '56%'], progress: { show: ok, width: 7, itemStyle: { color: C, shadowColor: C, shadowBlur: 10 } }, axisLine: { lineStyle: { width: 7, color: [[1, ok ? 'rgba(0,214,255,.14)' : 'rgba(120,140,150,.2)']] } }, axisTick: { show: false }, splitLine: { length: 5, distance: 1, lineStyle: { color: 'rgba(0,214,255,.5)', width: 1 } }, splitNumber: 5, axisLabel: { show: false }, pointer: { show: false }, anchor: { show: false },
      title: { offsetCenter: [0, '78%'], fontSize: small ? 9 : 10, color: '#6fa3b8', fontFamily: 'Tektur,monospace' }, detail: { offsetCenter: [0, '8%'], fontSize: small ? 15 : 18, fontWeight: 600, color: ok ? '#fff' : '#6fa3b8', fontFamily: 'Tektur,monospace', formatter: function (x) { return ok ? Math.round(x) + unit : 'HOLD'; } }, data: [{ value: ok ? v : 0, name: label }], animation: !RM }] }); }
    J.on(draw); addEventListener('resize', function () { ch.resize(); }); return ch;
  };
  /* ---- график/гистограмма ---- */
  J.chart = function (el, key, kind, max) {
    if (!window.echarts) return; var ch = echarts.init(el); function draw() { var d = H[key] || [], ok = d.length > 1;
      ch.setOption({ animation: !RM, grid: { left: 26, right: 6, top: 8, bottom: 14 }, xAxis: { type: 'category', data: d.map(function (_, i) { return i; }), axisLine: { lineStyle: { color: 'rgba(0,214,255,.3)' } }, axisLabel: { show: false }, axisTick: { show: false } }, yAxis: { type: 'value', min: 0, max: max, splitNumber: 3, axisLabel: { color: '#6fa3b8', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(0,214,255,.12)' } } },
        graphic: ok ? [] : [{ type: 'text', left: 'center', top: 'middle', style: { text: 'HOLD', fill: '#6fa3b8', font: '600 14px Tektur' } }],
        series: [kind === 'bar' ? { type: 'bar', data: d, barWidth: '60%', itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#00d6ff' }, { offset: 1, color: 'rgba(0,214,255,.15)' }] } } } : { type: 'line', data: d, smooth: true, showSymbol: false, lineStyle: { color: C, width: 2, shadowColor: C, shadowBlur: 8 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,214,255,.35)' }, { offset: 1, color: 'rgba(0,214,255,0)' }] } } }] }, true); }
    J.on(draw); addEventListener('resize', function () { ch.resize(); }); return ch;
  };
  /* ---- звуковая волна: AnalyserNode (микрофон); без микрофона HOLD, в демо синусоида с пометкой ---- */
  J.wave = function (cv, micBtn) {
    var g = cv.getContext('2d'), an = null, buf = null, T = 0, st = null;
    function fit() { var r = cv.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2); cv.width = r.width * d; cv.height = r.height * d; g.setTransform(d, 0, 0, d, 0, 0); } fit(); addEventListener('resize', fit);
    function draw() { var w = cv.clientWidth, h = cv.clientHeight; g.clearRect(0, 0, w, h); g.strokeStyle = 'rgba(0,214,255,.9)'; g.shadowColor = '#00d6ff'; g.shadowBlur = 8; g.lineWidth = 1.5; g.beginPath(); var N = 96, lv = 0;
      if (an) { an.getByteTimeDomainData(buf); for (var i = 0; i < N; i++) { var s = (buf[Math.floor(i / N * buf.length)] - 128) / 128; lv += s * s; g.lineTo(i / (N - 1) * w, h / 2 + s * h * .45 * 1.6); } J.mic.level = Math.min(1, Math.sqrt(lv / N) * 5); }
      else if (DEMO) { for (var j = 0; j < N; j++) { var e = Math.sin(j / N * Math.PI), y = Math.sin(j * .5 + T * 3) * Math.sin(j * .13 - T) * e * h * .38; g.lineTo(j / (N - 1) * w, h / 2 + y); } J.mic.level = .3 + .2 * Math.sin(T * 3); }
      else { g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke(); g.shadowBlur = 0; g.fillStyle = '#6fa3b8'; g.font = '600 11px Tektur,monospace'; g.fillText('MIC HOLD: нажмите МИКРОФОН', 8, h / 2 - 8); J.mic.level = 0; return; }
      g.stroke(); g.shadowBlur = 0; if (DEMO) { g.fillStyle = '#ffaa3c'; g.font = '600 10px ui-monospace'; g.fillText('ДЕМО', w - 36, 12); } }
    function loop(t) { T = t / 1000; if (!document.hidden) draw(); if (!RM) requestAnimationFrame(loop); } requestAnimationFrame(loop); if (RM) draw();
    if (micBtn) micBtn.addEventListener('click', function () { if (an) { st.getTracks().forEach(function (x) { x.stop(); }); an = null; J.mic.an = null; J.mic.on = false; return; } navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) { st = s; var ac = new AudioContext(), a = ac.createAnalyser(); a.fftSize = 512; ac.createMediaStreamSource(s).connect(a); an = a; J.mic.an = a; buf = new Uint8Array(a.fftSize); J.mic.on = true; }).catch(function () {}); });
  };
  /* ---- списки: задачи (agenda) и сервисы (status) ---- */
  J.tasks = function (ul) { J.on(function (c, a) { ul.textContent = ''; var it = a && Array.isArray(a.ideas) ? a.ideas.filter(function (i) { return i && i.title && !/done|closed|reject|dismiss/i.test(String(i.status || '')); }).slice(0, 5) : []; if (!it.length) { var l = document.createElement('li'); l.className = 'hold'; l.textContent = 'HOLD: повестка недоступна'; ul.appendChild(l); return; } it.forEach(function (i) { var l = document.createElement('li'); l.textContent = String(i.title).slice(0, 40); var s = document.createElement('small'); s.textContent = String(i.status || '').toUpperCase().slice(0, 6); l.appendChild(s); ul.appendChild(l); }); }); };
  J.events = function (ul) { J.on(function (c, a, s) { ul.textContent = ''; var sv = s && s.services; if (!sv) { var l = document.createElement('li'); l.className = 'hold'; l.textContent = 'HOLD: статус недоступен'; ul.appendChild(l); return; } Object.keys(sv).slice(0, 6).forEach(function (k) { var l = document.createElement('li'); if (!sv[k].up) l.className = 'dn'; l.textContent = k; var m = document.createElement('small'); m.textContent = sv[k].up ? 'UP' : 'DOWN'; l.appendChild(m); ul.appendChild(l); }); }); };
  /* мини-виджеты: горизонтальная лента на узком экране */
  J.strip = function (box) {
    var defs = [['GPU', 'gpu_util_pct', '%'], ['VRAM', 'gpu_vram_pct', '%'], ['TEMP', 'gpu_temp_c', '°C'], ['PWR', 'gpu_power_w', 'Вт']];
    var els = defs.map(function (d) { var c = document.createElement('div'); c.className = 'jv-chip jv-f'; c.innerHTML = '<small>' + d[0] + '</small><b>HOLD</b>'; box.appendChild(c); return c; });
    var tk = document.createElement('div'); tk.className = 'jv-chip jv-f'; tk.innerHTML = '<small>ЗАДАЧИ</small><b>HOLD</b>'; box.appendChild(tk);
    var sv = document.createElement('div'); sv.className = 'jv-chip jv-f'; sv.innerHTML = '<small>СЕРВИСЫ</small><b>HOLD</b>'; box.appendChild(sv);
    function set(e, v) { var b = e.querySelector('b'); b.textContent = v == null ? 'HOLD' : v; e.classList.toggle('hold', v == null); }
    J.on(function (c, a, s) { defs.forEach(function (d, i) { set(els[i], c[d[1]] != null ? Math.round(c[d[1]]) + d[2] : null); });
      set(tk, a && Array.isArray(a.ideas) ? a.ideas.filter(function (i) { return i && i.title && !/done|closed|reject|dismiss/i.test(String(i.status || '')); }).length : null);
      var x = s && s.services ? Object.keys(s.services) : null; set(sv, x ? x.filter(function (k) { return s.services[k].up; }).length + '/' + x.length : null); });
  };
  J.intro = function () { if (RM || !window.gsap) return; gsap.from('.jv-f', { opacity: 0, y: 18, duration: .7, ease: 'power3.out', stagger: .07, clearProps: 'opacity,transform' }); gsap.from('.jv-btn', { opacity: 0, y: 30, duration: .6, stagger: .06, delay: .4, ease: 'back.out(1.6)', clearProps: 'all' }); };
  window.NOXjv = J;
})();
