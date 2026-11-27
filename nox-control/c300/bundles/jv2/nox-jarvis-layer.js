/* NOX · слой JARVIS: HUD-виджеты с реальными данными на HOME, SYSTEM, TRAINING, MODELS, MEMORY. Откат: ?jarvis=0 (запоминается), ?jarvis=1 вернуть. Нет данных -> HOLD. demo=1 только для скриншотов. */
(function () {
  'use strict';
  var Q = location.search, LSK = 'nox.jarvis';
  try { if (/[?&]jarvis=0/.test(Q)) localStorage.setItem(LSK, '0'); if (/[?&]jarvis=1/.test(Q)) localStorage.removeItem(LSK); if (localStorage.getItem(LSK) === '0') return; } catch (e) { if (/[?&]jarvis=0/.test(Q)) return; }
  if (window.__noxJvLayer) return; window.__noxJvLayer = 1;
  var P = ({ index: 'home', home: 'home', sys: 'system', system: 'system', train: 'training', training: 'training', models: 'models', mem: 'memory', memory: 'memory' })[document.body && document.body.dataset.page] || ({ 'index.html': 'home', '': 'home', 'system.html': 'system', 'training.html': 'training', 'models.html': 'models', 'memory.html': 'memory' })[location.pathname.split('/').pop()];
  if (!P) return;
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
  var EX = { /* страница -> реальные источники сверх /api/nox-live; нет ответа -> HOLD */
    home: [['/api/chat/health', function (j) { return [['ЯДРО ЧАТА', j.core ? (j.core.up ? 'UP' : 'DOWN') : null], ['RTE', j.rte ? (j.rte.up ? 'UP' : 'DOWN') : null]]; }]],
    system: [['/api/pc-metrics', function (j) { return [['CPU', j.cpu_percent != null ? Math.round(j.cpu_percent) + '%' : null], ['CPU °C', j.cpu_temperature_c != null ? Math.round(j.cpu_temperature_c) + '°C' : null], ['SHM', j.shm && j.shm.percent != null ? Math.round(j.shm.percent) + '%' : null], ['VRAM ГБ', j.vram_used_gb != null ? j.vram_used_gb.toFixed(1) + '/' + (j.vram_total_gb || 0).toFixed(0) : null]]; }]],
    training: [['/api/nox/training/status', function (j) { return [['ФАЗА', j.phase || j.status || null], ['РАУНД / ШАГ', j.round != null ? j.round + ' / ' + (j.step != null ? j.step : '-') : null], ['СТРОК', j.rows_total != null ? j.rows_total : null], ['ЛУЧШИЙ', j.best != null ? Number(j.best).toFixed(3) : null], ['ЧЕКПОИНТЫ', j.checkpoint_count != null ? j.checkpoint_count : null], ['ГЕНЕРАЦИИ', j.generation_slots ? j.generation_slots.active_generations : null]]; }]],
    models: [['/glm/props', function (j) { return [['GLM', j.hold ? 'HOLD' : (j.status || (j.ok ? 'OK' : null))], ['ПРИЧИНА', j.hold_reason ? String(j.hold_reason).slice(0, 40) : null]]; }]],
    memory: [['/memory/health', function (j) { var k = Object.keys(j || {}); return [['ПАМЯТЬ', j.ok === true ? 'OK' : (j.status || (k.length ? 'ОТВЕТ' : null))], ['ПОЛЕЙ', k.length || null]]; }]]
  };
  var DEMOX = { home: [['ЯДРО ЧАТА', 'UP'], ['RTE', 'UP']], system: [['CPU', '34%'], ['CPU °C', '52°C'], ['SHM', '12%'], ['VRAM ГБ', '9.8/24']], training: [['ФАЗА', 'train'], ['РАУНД / ШАГ', '12 / 340'], ['СТРОК', '4820'], ['ЛУЧШИЙ', '0.412'], ['ЧЕКПОИНТЫ', '6'], ['ГЕНЕРАЦИИ', '2']], models: [['GLM', 'HOLD'], ['ПРИЧИНА', 'демо']], memory: [['ПАМЯТЬ', 'OK'], ['ПОЛЕЙ', '8']] };
  function build() {
    var J = window.NOXjv; if (!J || !window.echarts) return;
    var box = el('section', 'jv-hudrow'); var gcard = el('section', 'jv-f'); gcard.innerHTML = '<div class="jv-h">ТЕЛЕМЕТРИЯ<i></i><em id="jvlD">LIVE</em></div><div class="jv-g5"><div></div><div></div><div></div><div></div><div></div></div>';
    var ccard = el('section', 'jv-f'); ccard.innerHTML = '<div class="jv-h">' + ({ home: 'СТАТУС', system: 'ЖЕЛЕЗО', training: 'ОБУЧЕНИЕ', models: 'МОДЕЛИ', memory: 'ПАМЯТЬ' })[P] + '<i></i><em>API</em></div><div class="jv-chips"></div>';
    box.appendChild(gcard); box.appendChild(ccard);
    if (P === 'home') { var f = el('div'); f.id = 'jvFloat'; f.appendChild(gcard); f.appendChild(ccard); ccard.style.marginTop = '10px'; var op = false; try { op = localStorage.getItem('nox.jv.hud') === '1' || DEMO; } catch (e) {} f.hidden = !op; document.body.appendChild(f); var t = el('button'); t.id = 'jvTog'; t.type = 'button'; t.textContent = 'HUD'; t.setAttribute('aria-label', 'Панель JARVIS'); t.onclick = function () { f.hidden = !f.hidden; try { localStorage.setItem('nox.jv.hud', f.hidden ? '0' : '1'); } catch (e) {} }; document.body.appendChild(t); }
    else { var wrap = document.querySelector('.page .wrap') || document.querySelector('main'); if (!wrap) return; var ph = wrap.querySelector('.ph'); wrap.insertBefore(box, ph ? ph.nextSibling : wrap.firstChild); }
    var g = gcard.querySelectorAll('.jv-g5>div'); var D = SM ? 100 : 100;
    J.gauge(g[0], 'gpu_util_pct', 'GPU', 100, '%'); J.gauge(g[1], 'gpu_vram_pct', 'VRAM', 100, '%'); J.gauge(g[2], 'gpu_temp_c', 'TEMP', 100, '°'); J.gauge(g[3], 'ram_used_pct', 'RAM', 100, '%'); J.gauge(g[4], 'disk_used_pct', 'DISK', 100, '%');
    var chips = ccard.querySelector('.jv-chips'); function paint(list) { chips.textContent = ''; (list || []).forEach(function (x) { var c = el('div', 'jv-chip' + (x[1] == null ? ' hold' : '')); c.innerHTML = '<small></small><b></b>'; c.firstChild.textContent = x[0]; c.lastChild.textContent = x[1] == null ? 'HOLD' : x[1]; chips.appendChild(c); }); }
    if (DEMO) { document.getElementById('jvlD').textContent = 'ДЕМО'; document.getElementById('jvlD').className = 'jv-demo'; J.start(); paint(DEMOX[P]); return; }
    J.start();
    function ex() { var d = EX[P][0], hold = d[2]; J.get(d[0]).then(function (j) { if (j && (j.hold && P !== 'models')) throw 0; paint(d[1](j || {})); }).catch(function () { paint(d[1] === EX[P][0][1] ? [['ИСТОЧНИК', null]] : []); }); }
    ex(); setInterval(ex, 15000);
    if (!RM && window.gsap) gsap.from(box.children, { opacity: 0, y: 14, duration: .6, stagger: .08, ease: 'power3.out', clearProps: 'opacity,transform' });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
