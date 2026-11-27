/* NOX · слой JARVIS: HUD-виджеты с реальными данными на HOME, SYSTEM, TRAINING, MODELS, MEMORY. Откат: ?jarvis=0 (запоминается), ?jarvis=1 вернуть. Нет данных -> HOLD. demo=1 только для скриншотов. */
(function () {
  'use strict';
  var Q = location.search, LSK = 'nox.jarvis';
  try { if (/[?&]jarvis=0/.test(Q)) localStorage.setItem(LSK, '0'); if (/[?&]jarvis=1/.test(Q)) localStorage.removeItem(LSK); if (localStorage.getItem(LSK) === '0') return; } catch (e) { if (/[?&]jarvis=0/.test(Q)) return; }
  if (window.__noxJvLayer) return; window.__noxJvLayer = 1;
  var OLD = { index: 'home', home: 'home', sys: 'system', train: 'training', mem: 'memory' }, BN = location.pathname.split('/').pop().replace(/\.html$/, '') || 'index';
  var P = BN; if (document.body && OLD[document.body.dataset.page] && /^(index|system|training|memory)$/.test(BN)) P = BN;
  if (/^(chat|chat-dc|chat-dc-old|chat-jarvis|qa|offline)$/.test(P) || /-s1\.main$/.test(P)) return;
  var RM = matchMedia('(prefers-reduced-motion: reduce)').matches, SM = innerWidth < 900, DEMO = /[?&]demo=1/.test(Q);
  var root = document.documentElement; root.classList.add('jv-on');
  function css(h) { var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.appendChild(l); }
  function js(s, cb) { var e = document.createElement('script'); e.src = s; e.onload = cb; e.onerror = function () {}; document.head.appendChild(e); }
  css('./nox-jarvis-layer.css?v=j1');
  function mount() {
    if (!document.body) return setTimeout(mount, 50);
    ['jv-gridbg', 'jv-scanbg'].forEach(function (c) { var d = document.createElement('div'); d.className = c; d.setAttribute('aria-hidden', 'true'); document.body.insertBefore(d, document.body.firstChild); });
    var idle = window.requestIdleCallback || function (f) { setTimeout(f, 300); };
    idle(function () { js('./vendor/echarts/echarts.min.js', function () { js('./nox-jarvis.js?v=j1', build); }); }, { timeout: 2500 });
  }
  function el(t, c, h) { var e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; }
  /* источники данных (реальные ключи проверены на сервере); нет ответа -> HOLD */
  function pct(v) { return v == null ? null : Math.round(v) + '%'; }
  var SRC = {
    health: ['/api/chat/health', function (j) { return [['ЯДРО ЧАТА', j.core ? (j.core.up ? 'UP' : 'DOWN') : null], ['RTE', j.rte ? (j.rte.up ? 'UP' : 'DOWN') : null]]; }],
    pc: ['/api/pc-metrics', function (j) { return [['CPU', pct(j.cpu_percent)], ['CPU °C', j.cpu_temperature_c != null ? Math.round(j.cpu_temperature_c) + '°C' : null], ['SHM', j.shm ? pct(j.shm.percent) : null], ['VRAM ГБ', j.vram_used_gb != null ? j.vram_used_gb.toFixed(1) + '/' + (j.vram_total_gb || 0).toFixed(0) : null]]; }],
    train: ['/api/nox/training/status', function (j) { return [['ФАЗА', j.phase || j.status || null], ['РАУНД / ШАГ', j.round != null ? j.round + ' / ' + (j.step != null ? j.step : '-') : null], ['СТРОК', j.rows_total != null ? j.rows_total : null], ['ЛУЧШИЙ', j.best != null ? Number(j.best).toFixed(3) : null], ['ЧЕКПОИНТЫ', j.checkpoint_count != null ? j.checkpoint_count : null], ['ГЕНЕРАЦИИ', j.generation_slots ? j.generation_slots.active_generations : null]]; }],
    glm: ['/glm/props', function (j) { return [['GLM', j.hold ? 'HOLD' : (j.status || (j.ok ? 'OK' : null))], ['ПРИЧИНА', j.hold_reason ? String(j.hold_reason).slice(0, 40) : null]]; }],
    mem: ['/memory/health', function (j) { var s = j && j.stats; return [['ПАМЯТЬ', j && j.ok === true ? 'OK' : (s ? 'ОТВЕТ' : null)]]; }],
    live: ['/api/nox/self_now', function (j) { var d = j && j.data || {}, t = d.telemetry || {}; return [['ЖИВОСТЬ', d.aliveness_score != null ? Number(d.aliveness_score).toFixed(2) : null], ['ТИШИНА, Ч', t.silence_h != null ? Number(t.silence_h).toFixed(1) : null], ['ОБУЧЕНИЕ', t.train_running != null ? (t.train_running ? 'ИДЁТ' : 'НЕТ') : null], ['LOAD/ЯДРО', t.load1_per_core != null ? Number(t.load1_per_core).toFixed(2) : null]]; }],
    act: ['/api/nox/activity', function (j) { var c = j.counts || {}; return [['В РАБОТЕ', c['В работе']], ['ОЧЕРЕДЬ', c['Очередь']], ['НУЖЕН ТЫ', c['Нужен ты']], ['ГОТОВО', c['Готово']]].map(function (x) { return [x[0], x[1] == null ? null : x[1]]; }); }],
    notif: ['/api/notifications', function (j) { return [['НЕПРОЧИТАННЫХ', j.unread != null ? j.unread : null], ['СОБЫТИЙ', Array.isArray(j.events) ? j.events.length : null]]; }],
    agenda: ['/api/nox/agenda', function (j) { var n = Array.isArray(j.ideas) ? j.ideas.filter(function (i) { return i && i.title && !/done|closed|reject|dismiss/i.test(String(i.status || '')); }).length : null; return [['ЗАДАЧ В ПОВЕСТКЕ', n]]; }],
    brief: ['/api/nox/briefs', function (j) { var m = j.morning && j.morning.data && j.morning.data.lines, e = j.evening && j.evening.data && j.evening.data.lines; return [['УТРО, СТРОК', Array.isArray(m) ? m.length : null], ['ВЕЧЕР, СТРОК', Array.isArray(e) ? e.length : null]]; }],
    stat: ['/api/nox/status', function (j) { var s = j.services, k = s ? Object.keys(s) : null; return [['СЕРВИСЫ UP', k ? k.filter(function (x) { return s[x].up; }).length + '/' + k.length : null], ['ВЕРСИЯ', j.health && j.health.version ? String(j.health.version).slice(0, 14) : null]]; }],
    glms: ['/glm/v1/nox/stats', function (j) { var u = j.upstreams || {}; return [['GLM CORE', u.core == null ? null : (u.core ? 'UP' : 'DOWN')], ['FAST', u.fast == null ? null : (u.fast ? 'UP' : 'DOWN')], ['ЗАПРОСОВ КЭШ', j.cache ? j.cache.requests : null]]; }]
  };
  var PG = { index: ['health'], system: ['pc'], training: ['train'], models: ['glm', 'glms'], memory: ['mem', 'live'],
    resonance: ['live'], consciousness: ['live'], selffeel: ['live'], soul: ['live'], growth: ['live'], organism: ['live', 'act'], dispatcher: ['act', 'stat'],
    downloads: ['stat'], install: ['stat'], settings: ['stat'], projects: ['act'], assistant: ['agenda'], calendar: ['agenda', 'notif'], board: ['act', 'agenda'], intents: ['agenda'], events: ['notif'], notifications: ['notif'],
    news: ['brief'], widgets: ['brief'], glance: ['brief', 'notif'], about: ['stat'], integrations: ['stat'], nexus: ['stat'], map: ['stat'], 'g01-status': ['stat'] };
  var FLOAT = /^(index|scene|planets|effects|cinema|tv|live|map|nexus|atlas|mini|studio|photo|creative|editor|pdf|writer|tools|constructor|browser|games|music|voice|book-reader|assistant|calendar|board)$/;
  var DEMOX = { health: [['ЯДРО ЧАТА', 'UP'], ['RTE', 'UP']], pc: [['CPU', '34%'], ['CPU °C', '52°C'], ['SHM', '12%'], ['VRAM ГБ', '9.8/24']], train: [['ФАЗА', 'train'], ['РАУНД / ШАГ', '12 / 340'], ['СТРОК', '4820'], ['ЛУЧШИЙ', '0.412']], glm: [['GLM', 'HOLD']], glms: [['GLM CORE', 'UP'], ['FAST', 'UP']], mem: [['ПАМЯТЬ', 'OK']], live: [['ЖИВОСТЬ', '0.74'], ['ТИШИНА, Ч', '1.2'], ['ОБУЧЕНИЕ', 'ИДЁТ']], act: [['В РАБОТЕ', 2], ['ОЧЕРЕДЬ', 5], ['НУЖЕН ТЫ', 1], ['ГОТОВО', 14]], notif: [['НЕПРОЧИТАННЫХ', 3]], agenda: [['ЗАДАЧ В ПОВЕСТКЕ', 4]], brief: [['УТРО, СТРОК', 6]], stat: [['СЕРВИСЫ UP', '6/7']] };
  var TITLE = { index: 'СТАТУС', system: 'ЖЕЛЕЗО', training: 'ОБУЧЕНИЕ', models: 'МОДЕЛИ', memory: 'ПАМЯТЬ' };
  function build() {
    var J = window.NOXjv; if (!J || !window.echarts) return;
    var srcs = Object.prototype.hasOwnProperty.call(PG, P) ? PG[P] : [], hasC = srcs.length > 0;
    var box = el('section', 'jv-hudrow' + (hasC ? '' : ' solo')), gcard = el('section', 'jv-f');
    gcard.innerHTML = '<div class="jv-h">ТЕЛЕМЕТРИЯ<i></i><em id="jvlD">LIVE</em></div><div class="jv-g5"><div></div><div></div><div></div><div></div><div></div></div>';
    box.appendChild(gcard); var ccard = null, chips = null;
    if (hasC) { ccard = el('section', 'jv-f'); ccard.innerHTML = '<div class="jv-h">' + (TITLE[P] || 'ДАННЫЕ СТРАНИЦЫ') + '<i></i><em>API</em></div><div class="jv-chips"></div>'; box.appendChild(ccard); chips = ccard.querySelector('.jv-chips'); }
    var wrap = !FLOAT.test(P) && (document.querySelector('.page .wrap') || document.querySelector('.wrap') || document.querySelector('main.page'));
    if (!wrap) { var f = el('div'); f.id = 'jvFloat'; f.appendChild(gcard); if (ccard) { ccard.style.marginTop = '10px'; f.appendChild(ccard); } var op = false; try { op = localStorage.getItem('nox.jv.hud') === '1' || DEMO; } catch (e) {} f.hidden = !op; document.body.appendChild(f);
      var t = el('button'); t.id = 'jvTog'; t.type = 'button'; t.textContent = 'HUD'; t.setAttribute('aria-label', 'Панель JARVIS'); t.onclick = function () { f.hidden = !f.hidden; try { localStorage.setItem('nox.jv.hud', f.hidden ? '0' : '1'); } catch (e) {} }; document.body.appendChild(t); }
    else { var ph = wrap.querySelector('.ph, header, h1'); if (ph && ph.parentNode !== wrap) ph = null; wrap.insertBefore(box, ph ? ph.nextSibling : wrap.firstChild); }
    var g = gcard.querySelectorAll('.jv-g5>div');
    J.gauge(g[0], 'gpu_util_pct', 'GPU', 100, '%'); J.gauge(g[1], 'gpu_vram_pct', 'VRAM', 100, '%'); J.gauge(g[2], 'gpu_temp_c', 'TEMP', 100, '°'); J.gauge(g[3], 'ram_used_pct', 'RAM', 100, '%'); J.gauge(g[4], 'disk_used_pct', 'DISK', 100, '%');
    var res = {}; function paint() { if (!chips) return; chips.textContent = ''; srcs.forEach(function (k) { (res[k] || SRC[k][1]({})).forEach(function (x) { var c = el('div', 'jv-chip' + (x[1] == null ? ' hold' : '')); c.innerHTML = '<small></small><b></b>'; c.firstChild.textContent = x[0]; c.lastChild.textContent = x[1] == null ? 'HOLD' : x[1]; chips.appendChild(c); }); }); }
    if (DEMO) { var d = document.getElementById('jvlD'); d.textContent = 'ДЕМО'; d.className = 'jv-demo'; J.start(); srcs.forEach(function (k) { res[k] = DEMOX[k]; }); paint(); return; }
    J.start(); paint();
    function ex() { srcs.forEach(function (k) { J.get(SRC[k][0]).then(function (j) { if (j && j.hold && k !== 'glm') throw 0; res[k] = SRC[k][1](j || {}); paint(); }).catch(function () { res[k] = null; delete res[k]; paint(); }); }); }
    if (hasC) { ex(); setInterval(ex, 15000); }
    if (!RM && window.gsap) gsap.from(box.children, { opacity: 0, y: 14, duration: .6, stagger: .08, ease: 'power3.out', clearProps: 'opacity,transform' });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
