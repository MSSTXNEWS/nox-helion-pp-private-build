/* Система: реальные метрики. Отклик служб (опрос каждые 5 с) и скорость шлюза, метрики браузера, ресурсы сервера из /api/pc-metrics (если панель подключена). Графики uPlot. */
import { $, esc, call, apiProbe, probeAll, hhmmss, download, toast } from './nox-api.js';
import { space } from './nox-nav.js';
const N = 120, SV = ['gw', 'mem', 'stt', 'tts'], NAMES = { gw: 'шлюз', mem: 'память', stt: 'STT', tts: 'TTS' }, COLORS = ['#7ff5ef', '#ffb454', '#ff5f8a', '#a99bff'];
let paused = false, t = [], lat = { gw: [], mem: [], stt: [], tts: [] }, fps = [], heap = [], tpsD = [], prev = {}, c1 = null, c2 = null, fcount = 0, fpsNow = 0;
const evt = []; const logEv = (m, bad) => { evt.unshift('<li><span class="t">' + hhmmss() + '</span><span class="' + (bad ? 'err' : 'okc') + '">' + esc(m) + '</span></li>'); $('#log').innerHTML = evt.slice(0, 60).join(''); };
(function loop() { fcount++; requestAnimationFrame(loop); })(); setInterval(() => { fpsNow = fcount; fcount = 0; }, 1000);
function mk(id, series, scales) {
  const el = $(id), w = () => Math.max(260, el.clientWidth), ax = { stroke: '#8fa0ad', grid: { stroke: 'rgba(150,225,235,.08)' }, ticks: { stroke: 'rgba(150,225,235,.12)' }, font: '10px JetBrains Mono, monospace' };
  const u = new window.uPlot({ width: w(), height: 220, legend: { show: true }, cursor: { drag: { x: false, y: false } }, scales: Object.assign({ x: { time: true } }, scales || {}), axes: [ax, Object.assign({ size: 48 }, ax)], series: [{}].concat(series.map((s, i) => Object.assign({ stroke: COLORS[i], width: 1.6, points: { show: false }, spanGaps: false }, s))) }, [[], ...series.map(() => [])], el);
  addEventListener('resize', () => u.setSize({ width: w(), height: 220 })); return u;
}
const push = (a, v) => { a.push(v); if (a.length > N) a.shift(); };
function draw() { const x = t.slice(); c1.setData([x, ...SV.map((k) => lat[k])]); c2.setData([x, fps, heap]); }
async function sample() {
  if (paused) return; const P = await probeAll(false), now = Date.now() / 1000;
  const map = { gw: P.stats, mem: P.mem, stt: P.stt, tts: P.tts };
  push(t, now); SV.forEach((k) => push(lat[k], map[k].ok ? map[k].ms : null)); push(fps, fpsNow); const h = performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null; push(heap, h);
  P.services.forEach((s) => { if (prev[s.id] && prev[s.id] !== s.state) logEv(s.name + ': ' + prev[s.id] + ' → ' + s.state + (s.error ? ' (' + s.error + ')' : ''), s.state === 'bad'); prev[s.id] = s.state; });
  const S = P.stats.ok && P.stats.data;
  $('#tiles').innerHTML = [['Отклик шлюза', P.stats.ok ? P.stats.ms + ' мс' : 'нет', !P.stats.ok], ['Скорость глубокого', S && S.speed ? S.speed.deep.tps + ' ток/с' : '—', !S], ['Скорость быстрого', S ? (S.fast_available ? S.speed.fast.tps + ' ток/с' : 'не подключён') : '—', !S], ['Активных запросов', S ? (S.active || []).length : '—', !S], ['Кадров/с (браузер)', fpsNow, false], ['Память JS', h == null ? 'н/д' : h + ' МБ', false]].map((x) => '<section class="card c4 flat"><h2>' + x[0] + '</h2><div class="big ' + (x[2] ? 'err' : '') + '">' + esc(x[1]) + '</div></section>').join('');
  $('#lat1').textContent = hhmmss(); $('#lat2').textContent = h == null ? 'ПАМЯТЬ JS: НЕ ОТДАЁТ БРАУЗЕР' : '';
  draw(); pc(false);
}
async function pc(force) {
  const box = $('#pc'), a = await apiProbe(force);
  if (!a.ok) { box.innerHTML = '<div class="err">Метрики сервера (ЦП, ОЗУ, GPU) недоступны: панель S2 /api не подключена (' + esc(a.error) + '). Цифры не выдумываются; графики выше построены из реальных ответов служб.</div>'; return; }
  const r = await call('/api/pc-metrics'); if (!r.ok || !r.data || typeof r.data !== 'object') { box.innerHTML = '<div class="err">/api/pc-metrics не отвечает: ' + esc(r.error || 'пустой ответ') + '</div>'; return; }
  const flat = (o, p = '') => Object.keys(o).flatMap((k) => (o[k] && typeof o[k] === 'object' && !Array.isArray(o[k]) ? flat(o[k], p + k + '.') : [[p + k, Array.isArray(o[k]) ? o[k].length + ' знач.' : o[k]]]));
  box.innerHTML = '<dl class="kv">' + flat(r.data).slice(0, 30).map((x) => '<dt>' + esc(x[0]) + '</dt><dd>' + esc(x[1]) + '</dd>').join('') + '</dl>';
}
function dev() {
  let gl = 'н/д'; try { const c = document.createElement('canvas').getContext('webgl'), e = c && c.getExtension('WEBGL_debug_renderer_info'); gl = e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : c ? 'WebGL без сведений о GPU' : 'WebGL недоступен'; } catch (e) { /* нет WebGL */ }
  const cn = navigator.connection || {};
  $('#dev').innerHTML = '<dl class="kv"><dt>Экран</dt><dd>' + innerWidth + '×' + innerHeight + ' @' + devicePixelRatio + '</dd><dt>Ядер ЦП</dt><dd>' + (navigator.hardwareConcurrency || 'н/д') + '</dd><dt>ОЗУ (оценка)</dt><dd>' + (navigator.deviceMemory ? '≥ ' + navigator.deviceMemory + ' ГБ' : 'н/д') + '</dd><dt>GPU</dt><dd>' + esc(gl) + '</dd><dt>Сеть</dt><dd>' + esc(cn.effectiveType ? cn.effectiveType + ', rtt ' + cn.rtt + ' мс' : 'н/д') + '</dd><dt>Фон</dt><dd>' + (window.__noxSpace ? 'three.js, WebGL2' : document.body.classList.contains('bgfallback') ? 'запасной режим' : 'загружается') + '</dd></dl>';
}
$('#sPause').addEventListener('click', (e) => { paused = !paused; const b = e.currentTarget; b.setAttribute('aria-pressed', String(paused)); b.querySelector('span').textContent = paused ? 'Продолжить' : 'Пауза'; b.querySelector('sl-icon').setAttribute('name', paused ? 'player-play' : 'player-pause'); $('#sState').textContent = paused ? 'ОПРОС ОСТАНОВЛЕН' : 'ОПРОС КАЖДЫЕ 5 С'; });
$('#sClear').addEventListener('click', () => { t = []; SV.forEach((k) => (lat[k] = [])); fps = []; heap = []; draw(); toast('Графики очищены'); });
$('#sCsv').addEventListener('click', () => { if (!t.length) { toast('Нет данных для CSV', true); return; } download('nox-metrics.csv', ['time,' + SV.join(',') + ',fps,heap_mb'].concat(t.map((x, i) => [new Date(x * 1000).toISOString()].concat(SV.map((k) => (lat[k][i] == null ? '' : lat[k][i])), fps[i], heap[i] == null ? '' : heap[i]).join(','))).join('\n'), 'text/csv'); toast('CSV: строк ' + t.length); });
c1 = mk('#ch1', SV.map((k) => ({ label: NAMES[k] }))); c2 = mk('#ch2', [{ label: 'кадры/с' }, { label: 'JS, МБ', scale: 'mb' }], { mb: {} });
dev(); space.then(dev); setTimeout(sample, 1200); setInterval(sample, 5000);
