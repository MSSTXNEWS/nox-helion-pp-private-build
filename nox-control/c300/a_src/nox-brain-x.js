/* NOX · датчики ума: сознание, организм, душа, рост, самочувствие, обучение. Только реальные данные; нет данных - честная плашка. */
import { $, esc, call } from './nox-api.js';
const P = document.body.dataset.page, U = (p) => new URL(p, import.meta.url).href;
const C = { amber: '#ff8a4c', gold: '#ffb070', red: '#e8431f', dim: '#6b4d40', txt: '#d9c7bb' };
const ECH = () => window.echarts ? Promise.resolve(window.echarts) : new Promise((ok, no) => { const s = document.createElement('script'); s.src = U('./vendor/nox-extra/echarts.min.js'); s.onload = () => ok(window.echarts); s.onerror = no; document.head.appendChild(s); });
const base = () => ({ backgroundColor: 'transparent', textStyle: { color: C.txt, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }, animationDuration: 600 });
function section(id, title, right, h, before) { const s = document.createElement('section'); s.className = 'card nbx'; s.id = id; s.innerHTML = '<h2>' + title + ' <span class="r mono" id="' + id + 'R">' + (right || '') + '</span></h2><div class="nbx-b" id="' + id + 'B" style="min-height:' + h + 'px"></div><div class="muted nbx-n" id="' + id + 'N"></div>'; (before || $('#brain')).before(s); return s; }
const empty = (el, t) => { el.innerHTML = '<div class="empty">' + esc(t) + '</div>'; };
const stats = async () => { const r = await call('/glm/v1/nox/stats', { timeout: 6000 }); return r.ok && r.data && r.data.health ? r.data.health : null; };
const charts = []; addEventListener('resize', () => charts.forEach((c) => c.resize()));
const initChart = async (el, opt) => { const e = await ECH(); const c = e.init(el, null, { renderer: 'canvas' }); c.setOption(Object.assign(base(), opt)); charts.push(c); return c; };

/* ---------- сознание: 3D-разрез трансформера + органы ---------- */
async function consc() {
  const s = section('nbxViz', '3D-разрез трансформера', 'llm-viz · MIT', 520);
  $('#nbxVizB').innerHTML = '<iframe title="Разрез трансформера (llm-viz)" src="' + U('./vendor/llm-viz/llm.html') + '" loading="lazy" style="width:100%;height:100%;min-height:520px;border:0;border-radius:12px;background:#05060a"></iframe>';
  $('#nbxVizN').textContent = 'Эталонная визуализация архитектуры GPT (nano-GPT, проект llm-viz, Brendan Bycroft). Это наглядный разрез трансформера, а не веса NOX; живые данные ядра ниже.';
  organsPanel(); setInterval(() => { if (!document.hidden) organsPanel(); }, 10000);
}
let orgChart = null;
async function organsPanel() {
  let s = $('#nbxOrg'); if (!s) { s = section('nbxOrg', 'Органы ядра · живые', '', 300); $('#nbxOrgB').innerHTML = '<div class="nbx-org"><div id="nbxChips" class="nbx-chips"></div><div id="nbxGauge" style="height:220px"></div></div>'; }
  const h = await stats(); const chips = $('#nbxChips'); if (!h || !h.organs) { chips.innerHTML = '<div class="empty">Ядро не ответило (/glm/v1/nox/stats)</div>'; return; }
  const o = Object.entries(h.organs); const on = o.filter((x) => x[1]).length;
  chips.innerHTML = o.map((x) => '<span class="nbx-chip ' + (x[1] ? 'on' : 'off') + '"><i></i>' + esc(x[0]) + '</span>').join('') + '<div class="nbx-kv"><span>Совесть <b>' + esc(h.conscience || '—') + '</b></span><span>GLM <b>' + esc((h.glm && h.glm.state) || '—') + '</b></span><span>Ходов <b>' + esc(h.turns ?? '—') + '</b></span><span>Быстрый ок/пусто/сбой <b>' + (h.fast ? h.fast.ok + '/' + h.fast.empty + '/' + h.fast.fail : '—') + '</b></span></div>';
  $('#nbxOrgR').textContent = on + ' / ' + o.length + ' ЖИВЫ';
  const opt = { series: [{ type: 'gauge', min: 0, max: o.length, progress: { show: true, width: 12, itemStyle: { color: C.amber } }, axisLine: { lineStyle: { width: 12, color: [[1, 'rgba(255,255,255,.08)']] } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false }, detail: { valueAnimation: true, formatter: '{value}/' + o.length, color: C.gold, fontSize: 26, offsetCenter: [0, '10%'] }, title: { color: C.txt, offsetCenter: [0, '60%'], fontSize: 11 }, data: [{ value: on, name: 'органов живо' }] }] };
  if (!orgChart) orgChart = await initChart($('#nbxGauge'), opt); else orgChart.setOption(opt);
}

/* ---------- организм: лента органов (перемотка) + граф ядер ---------- */
const hist = [];
async function loadHist() {
  try { const r = await fetch(U('./data/organs_hist.jsonl?t=' + Date.now()), { cache: 'no-store' }); if (r.ok) (await r.text()).trim().split('\n').slice(-1500).forEach((l) => { try { hist.push(JSON.parse(l)); } catch (e) { /* */ } }); } catch (e) { /* нет записи */ }
}
async function ribbon(host) {
  const s = section('nbxRib', 'Лента органов · перемотка', '', 300, host); const B = $('#nbxRibB'); B.style.height = '320px';
  await loadHist(); if (!hist.length) { empty(B, 'Запись состояния органов ещё не накопила точек. Лента наполнится, пока открыт сервер (запись каждые 15 с).'); return; }
  const c = await initChart(B, {}); let live = true;
  const draw = () => {
    const names = [...new Set(hist.flatMap((p) => Object.keys(p.organs || {})))]; const xs = hist.map((p) => new Date(p.ts * 1000).toLocaleTimeString('ru-RU'));
    const data = []; hist.forEach((p, i) => names.forEach((n, j) => { if (n in (p.organs || {})) data.push([i, j, p.organs[n] ? 1 : 0]); }));
    c.setOption({ tooltip: { position: 'top', formatter: (a) => esc(names[a.value[1]]) + ' · ' + xs[a.value[0]] + ': ' + (a.value[2] ? 'жив' : 'не отвечает') }, grid: { left: 84, right: 14, top: 8, bottom: 70 },
      xAxis: { type: 'category', data: xs, axisLabel: { color: C.txt, interval: 'auto' }, splitArea: { show: false } }, yAxis: { type: 'category', data: names, axisLabel: { color: C.txt } },
      visualMap: { show: false, min: 0, max: 1, inRange: { color: ['#7a1f10', C.amber] } },
      dataZoom: [{ type: 'inside', start: live ? Math.max(0, 100 - 6000 / hist.length) : undefined }, { type: 'slider', height: 22, bottom: 8, borderColor: 'rgba(255,130,80,.2)', fillerColor: 'rgba(255,130,80,.18)', textStyle: { color: C.txt } }],
      series: [{ type: 'heatmap', data, itemStyle: { borderColor: '#0a0707', borderWidth: 1 }, emphasis: { itemStyle: { borderColor: C.gold } } }] });
  };
  draw(); $('#nbxRibR').innerHTML = '<button type="button" class="tag" id="nbxLive">LIVE</button>';
  $('#nbxLive').addEventListener('click', () => { live = true; draw(); }); c.on('datazoom', () => { live = false; });
  $('#nbxRibN').textContent = 'Точек: ' + hist.length + ' (запись каждые 15 с с сервера). Ползунок и колесо — перемотка во времени.';
  setInterval(async () => { if (document.hidden) return; const h = await stats(); if (!h || !h.organs) return; hist.push({ ts: Date.now() / 1000, organs: h.organs }); if (hist.length > 1500) hist.shift(); if (live) draw(); $('#nbxRibN').textContent = 'Точек: ' + hist.length + ' (запись каждые 15 с с сервера). Ползунок и колесо — перемотка во времени.'; }, 15000);
}
async function coreGraph(host, withReg) {
  const s = section('nbxGr', 'Граф ядер', '3d-force-graph · MIT', 420, host); const B = $('#nbxGrB'); B.style.height = '440px';
  const [h, r] = await Promise.all([stats(), call('/brain/organism', { timeout: 9000 })]);
  const nodes = [{ id: 'NOX', label: 'NOX', val: 14, color: C.gold }], links = [];
  if (h && h.organs) { nodes.push({ id: 'core', label: 'Ядро (живые органы)', val: 8, color: C.amber }); links.push({ source: 'NOX', target: 'core' }); Object.entries(h.organs).forEach(([k, v]) => { nodes.push({ id: 'c:' + k, label: k + (v ? ' · жив' : ' · не отвечает'), val: 3, color: v ? '#ffd9a0' : C.red }); links.push({ source: 'core', target: 'c:' + k }); }); }
  const sys = r.ok && r.data && r.data.systems; if (withReg && sys) sys.forEach((sy) => { nodes.push({ id: sy.id, label: 'Система ' + sy.id + ' · ' + sy.organs.length + ' орг.', val: 5, color: C.amber }); links.push({ source: 'NOX', target: sy.id }); sy.organs.forEach((o) => { nodes.push({ id: o.id, label: (o.name_ru || o.slug) + ' · ' + o.status, val: 1.4, color: o.status === 'exists' ? C.gold : C.dim }); links.push({ source: sy.id, target: o.id }); }); });
  if (nodes.length < 3) { empty(B, 'Нет данных для графа: ядро и реестр органов не ответили.'); return; }
  try { const m = await import(U('./vendor/nox-brain/nox-brain.js')); B.textContent = ''; m.graph3d(B, { nodes, links }, { z: withReg ? 520 : 230 }); } catch (e) { empty(B, 'Граф не загрузился: ' + e.message); }
  $('#nbxGrN').textContent = 'Узлы: живые органы ядра (янтарь — отвечает, красный — нет)' + (withReg && sys ? '; реестр: ' + sys.length + ' систем, ' + nodes.filter((n) => /^K\d/.test(n.id)).length + ' органов (светлее — «exists», тусклее — «partial» и прочее)' : '') + '. Вращайте мышью/пальцем.';
}

/* ---------- самочувствие: радар + шкалы + состояние ---------- */
const EM = { hunger: 'Голод', weight: 'Тяжесть', weakness: 'Слабость', sickness: 'Болезнь', pain: 'Боль', fear: 'Страх', shame: 'Стыд', pride: 'Гордость', boredom: 'Скука', curiosity: 'Любопытство', fatigue: 'Усталость' };
async function feel() {
  const r = await call('/brain/selffeel', { timeout: 9000 }); const sf = r.ok && r.data && r.data.sources && r.data.sources.selfstate;
  const s = section('nbxFeel', 'Настроение NOX · радар', '', 360);
  if (!sf || !sf.ok) { empty($('#nbxFeelB'), 'selfstate недоступен: ' + ((sf && sf.reason) || (r && r.error) || 'нет ответа')); return; }
  const d = sf.data, keys = Object.keys(EM), vals = keys.map((k) => (typeof d[k] === 'number' ? d[k] : null)), known = keys.filter((k, i) => vals[i] !== null);
  const top = known.sort((a, b) => d[b] - d[a])[0]; const lvl = top ? d[top] : 0;
  $('#nbxFeelR').textContent = 'обновлено ' + esc(d.updated || '—');
  $('#nbxFeelB').innerHTML = '<div class="nbx-feel"><div class="nbx-orb" style="--lv:' + lvl + '" aria-hidden="true"><i></i><i></i><i></i></div><div class="nbx-dom"><small>Доминирует</small><b>' + esc(top ? EM[top] : '—') + '</b><span>' + (top ? Math.round(lvl * 100) + '%' : 'нет данных') + '</span></div><div id="nbxRadar" style="height:300px;min-width:260px;flex:1"></div></div><div class="nbx-bars">' + keys.map((k, i) => '<div class="nbx-bar" title="' + esc((d.reasons && d.reasons[k]) || '') + '"><span>' + EM[k] + '</span><div class="b"><i style="width:' + (vals[i] === null ? 0 : Math.round(vals[i] * 100)) + '%"></i></div><b>' + (vals[i] === null ? 'нет данных' : Math.round(vals[i] * 100) + '%') + '</b></div>').join('') + '</div>';
  await initChart($('#nbxRadar'), { radar: { indicator: keys.map((k) => ({ name: EM[k], max: 1 })), axisName: { color: C.txt }, splitLine: { lineStyle: { color: 'rgba(255,130,80,.16)' } }, splitArea: { show: false }, axisLine: { lineStyle: { color: 'rgba(255,130,80,.2)' } } }, series: [{ type: 'radar', data: [{ value: vals.map((v) => v === null ? 0 : v), name: 'NOX' }], areaStyle: { color: 'rgba(255,110,60,.28)' }, lineStyle: { color: C.amber }, itemStyle: { color: C.gold } }], tooltip: {} });
  $('#nbxFeelN').textContent = 'Источник: /brain/selffeel → selfstate. Поля без данных (null) показаны как «нет данных» и на радаре равны 0; наведите на шкалу — причина из журнала.';
}

/* ---------- рост: ходы во времени из записи ---------- */
async function growth() {
  const s = section('nbxGrow', 'Рост · ходы NOX во времени', 'по записи сервера', 300); const B = $('#nbxGrowB'); B.style.height = '300px'; await loadHist(); const pts = hist.filter((p) => typeof p.turns === 'number');
  if (pts.length < 2) { empty(B, 'История ходов ещё копится (запись каждые 15 с). Служба роста (8100) не отвечает: расширенные метрики появятся с ней.'); return; }
  await initChart(B, { tooltip: { trigger: 'axis' }, grid: { left: 44, right: 14, top: 16, bottom: 50 }, xAxis: { type: 'category', data: pts.map((p) => new Date(p.ts * 1000).toLocaleTimeString('ru-RU')) }, yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(255,255,255,.07)' } } }, dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 6 }], series: [{ type: 'line', data: pts.map((p) => p.turns), smooth: true, showSymbol: false, areaStyle: { color: 'rgba(255,110,60,.2)' }, lineStyle: { color: C.amber } }] });
}

/* ---------- обучение: реальные логи ---------- */
async function train() {
  const s = section('nbxTr', 'Кривые обучения · реальные логи', '', 320, $('main .card')); const B = $('#nbxTrB'); B.style.height = '340px';
  let d = null; try { const r = await fetch(U('./data/train_logs.json?t=' + Date.now()), { cache: 'no-store' }); if (r.ok) d = await r.json(); } catch (e) { /* */ }
  const runs = d && d.runs ? Object.entries(d.runs).filter((x) => x[1].points.length > 1) : [];
  if (!runs.length) { empty(B, 'Обучение не запущено: в логах сервера нет точек loss.'); return; }
  $('#nbxTrR').textContent = d.running ? 'ИДЁТ ОБУЧЕНИЕ' : 'ОБУЧЕНИЕ НЕ ЗАПУЩЕНО';
  const col = ['#ff8a4c', '#ffd9a0', '#e8431f', '#b08968', '#ff6a3d', '#c9a27e'];
  await initChart(B, { tooltip: { trigger: 'axis' }, legend: { textStyle: { color: C.txt }, type: 'scroll', bottom: 28 }, grid: { left: 48, right: 14, top: 16, bottom: 80 }, xAxis: { type: 'value', name: 'шаг', nameTextStyle: { color: C.txt }, splitLine: { show: false } }, yAxis: { type: 'value', name: 'loss', scale: true, splitLine: { lineStyle: { color: 'rgba(255,255,255,.07)' } } }, dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 4 }],
    series: runs.flatMap(([n, r], i) => [{ name: n, type: 'line', showSymbol: false, data: r.points.map((p) => [p.step, p.loss]), lineStyle: { color: col[i % col.length] } }].concat(r.points.some((p) => p.ce != null) ? [{ name: n + ' · holdout CE', type: 'line', showSymbol: true, symbolSize: 5, data: r.points.filter((p) => p.ce != null).map((p) => [p.step, p.ce]), lineStyle: { color: col[i % col.length], type: 'dashed' }, itemStyle: { color: col[i % col.length] } }] : [])) });
  $('#nbxTrN').textContent = (d.running ? 'Процесс обучения активен. ' : 'Сейчас обучение не запущено; показаны последние завершённые прогоны. ') + 'Файлы: ' + runs.map(([n, r]) => n + ' (' + r.points.length + ' т., ' + new Date(r.mtime * 1000).toLocaleString('ru-RU') + ')').join('; ');
}
/* ---------- живые процессы: порты органов, GPU, раунд, чекпоинты, журнал правок (из data/live.json) ---------- */
async function livePanel() {
  const B0 = section('nbxLive', 'Органы и процессы · живые данные', '', 260, $('main .card')); const B = $('#nbxLiveB');
  let d = null; try { const r = await fetch(U('./data/live.json?t=' + Date.now()), { cache: 'no-store' }); if (r.ok) d = await r.json(); } catch (e) { /* */ }
  if (!d) { empty(B, 'Нет данных live.json: датчик не пишет файл.'); return; }
  const age = Math.round(Date.now() / 1000 - d.ts);
  const ports = Object.entries(d.ports || {});
  const up = ports.filter((x) => x[1].ok).length;
  $('#nbxLiveR').textContent = up + ' / ' + ports.length + ' ОТВЕЧАЮТ · ' + age + ' с назад';
  const g = d.gpu ? 'VRAM ' + d.gpu.vram_used_mib + ' / ' + d.gpu.vram_total_mib + ' МиБ (' + d.gpu.vram_pct + '%), загрузка GPU ' + d.gpu.gpu_util_pct + '%' : 'GPU: nvidia-smi недоступен';
  B.innerHTML = '<table class="nbx-tbl"><thead><tr><th>Орган</th><th>Порт</th><th>Статус</th><th>Ответ</th></tr></thead><tbody>' +
    ports.map((x) => '<tr><td>' + esc(x[0]) + '</td><td class="mono">' + esc(PORT_OF[x[0]] || '') + '</td><td>' + (x[1].ok ? 'жив' : 'нет ответа') + '</td><td class="mono">' + esc(x[1].via || '—') + '</td></tr>').join('') +
    '</tbody></table><div class="nbx-kv"><span>' + esc(g) + '</span></div>' +
    '<div class="nbx-kv"><span>Раунд <b>' + esc(d.round || '—') + '</b></span></div>' +
    '<div class="nbx-kv"><span>Чекпоинты <b>' + esc((d.ckpt_keep || []).join(', ') || '—') + '</b></span></div>' +
    '<details><summary>Лог автообучения (хвост)</summary><pre class="mono">' + esc((d.autotrain_tail || []).join('\n')) + '</pre></details>' +
    '<details><summary>Журнал изменений (хвост)</summary><pre class="mono">' + esc((d.ops_tail || []).join('\n')) + '</pre></details>';
  $('#nbxLiveN').textContent = 'Источник: /workspace/nox/state и логи на сервере, обновляется датчиком раз в 30 с. Ничего не подставлено вручную.';
  setTimeout(() => livePanel_refresh(), 30000);
}
const PORT_OF = { 'тело': 8104, 'подъядро': 8105, 'судья_учитель': 8106, 'второй_судья': 8141, 'судьи': 8300, 'каскад': 8400, 'операторы': 8130, 'API-шлюз': 8120, 'рисунок': 8097 };
function livePanel_refresh() { const el = $('#nbxLive'); if (el) el.remove(); if (!document.hidden) livePanel(); else setTimeout(livePanel_refresh, 30000); }

const go = { consc: () => consc(), organ: async () => { const first = $('#brain'); await ribbon(first); await coreGraph(first, true); }, soul: () => coreGraph($('#brain'), false), feel: () => feel(), growth: () => growth(), train: () => train() }[P];
if (go) go();
if (['consc', 'organ', 'train'].includes(P)) livePanel();
