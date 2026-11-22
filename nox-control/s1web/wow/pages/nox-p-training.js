/* Обучение: прогресс из API панели S2 (если подключена) + реальные данные памяти (состав, действия владельца, правки как пары для дообучения). */
import { $, esc, memory, call, apiProbe, download, toast } from './nox-api.js';
import './nox-nav.js';
let pairs = [], charts = [];
const when = (ts) => new Date(ts * 1000).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
const kv = (o, d = 0) => '<dl class="kv">' + Object.keys(o).slice(0, 40).map((k) => { const v = o[k]; return '<dt>' + esc(k) + '</dt><dd>' + (v && typeof v === 'object' ? (d < 1 ? kv(v, d + 1) : esc(JSON.stringify(v).slice(0, 160))) : esc(v)) + '</dd>'; }).join('') + '</dl>';
async function progress(force) {
  const box = $('#prog'), st = $('#pState'); box.textContent = 'Проверка…'; st.textContent = '';
  const a = await apiProbe(force);
  if (!a.ok) {
    /* S2 не подключена: показываем реальные данные S1 - что накоплено для обучения (память s03, правки владельца, скорость шлюза) */
    const [h, j, g] = await Promise.all([call('/memory/health'), memory({ op: 'journal', limit: 500 }), call('/glm/v1/nox/stats')]);
    const S = h.ok && h.data && h.data.stats, C = j.ok && j.data && j.data.ok ? j.data.changes : null, pr = C ? C.filter((x) => x.action === 'correct' && x.old && x.new) : null, sp = g.ok && g.data && g.data.speed;
    const row = (k, v) => '<dt>' + k + '</dt><dd>' + esc(v) + '</dd>', last = pr && pr.length ? when(Math.max(...pr.map((x) => x.ts || 0))) : '—';
    st.textContent = 'ДАННЫЕ S1';
    box.innerHTML = '<div class="big">' + (pr ? pr.length : '—') + '<small>ПАР «БЫЛО → СТАЛО» ГОТОВО К ДООБУЧЕНИЮ</small></div><dl class="kv" style="margin-top:8px">'
      + row('Фактов в памяти', S ? S.facts : 'недоступно') + row('Эпизодов', S ? S.episodes : 'недоступно') + row('Правок владельца в журнале', C ? C.length : 'недоступно') + row('Последняя правка', last)
      + row('Скорость глубокого (GLM)', sp && sp.deep ? sp.deep.tps + ' ток/с' : 'нет данных') + row('Скорость быстрого', sp && sp.fast ? sp.fast.tps + ' ток/с' : 'нет данных') + '</dl>'
      + '<p class="muted" style="font-size:12.5px;margin:8px 0 0">Процент выполнения самого обучения появится, когда подключится панель S2 (RunPod): цифра не выдумывается. Пары можно выгрузить кнопкой «Правки как JSONL».</p>'; return; }
  for (const p of ['/api/nox/progress', '/api/nox/training/status', '/api/training/status']) {
    const r = await call(p); if (!r.ok || !r.data || typeof r.data !== 'object') continue; const d = r.data;
    const done = d.completedSteps != null ? d.completedSteps : d.step, tot = d.targetSteps != null ? d.targetSteps : d.total_steps;
    st.textContent = String(d.status || 'ДАННЫЕ ПОЛУЧЕНЫ').toUpperCase();
    box.innerHTML = (Number.isFinite(done) && Number.isFinite(tot) && tot > 0 ? '<div class="big">' + done + ' / ' + tot + '<small>ШАГОВ ЧЕКПОИНТА</small></div><div class="prog" style="margin:8px 0"><i style="width:' + Math.min(100, done / tot * 100).toFixed(1) + '%"></i></div>' : '') + '<div class="muted mono" style="margin-bottom:6px">' + esc(p) + '</div>' + kv(d); return;
  }
  st.textContent = 'ПУСТО'; box.innerHTML = '<div class="err">Панель S2 отвечает, но ни /api/nox/progress, ни /api/nox/training/status не вернули данных.</div>';
}
function chart(id, opt) { const n = $(id); n.textContent = ''; if (!window.echarts) { n.innerHTML = '<div class="err">ECharts не загрузился (vendor/nox-extra/echarts.min.js)</div>'; return; } const c = window.echarts.init(n, null, { renderer: 'canvas' }); c.setOption(Object.assign({ backgroundColor: 'transparent', textStyle: { color: '#b6c3cd', fontFamily: 'JetBrains Mono, monospace' }, animation: true }, opt)); charts.push(c); }
async function data() {
  charts.forEach((c) => c.dispose()); charts = [];
  const [h, j] = await Promise.all([call('/memory/health'), memory({ op: 'journal', limit: 200 })]);
  const S = h.ok && h.data && h.data.stats;
  if (!S) { $('#chMem').innerHTML = '<div class="err">Память недоступна: ' + esc(h.error) + '</div>'; $('#chMem').style.minHeight = '0'; } else chart('#chMem', { color: ['#7ff5ef', '#ffb454', '#ff5f8a'], tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: ['48%', '72%'], label: { color: '#e9eff3', formatter: '{b}: {c}' }, itemStyle: { borderColor: '#02030a', borderWidth: 2 }, data: [{ name: 'Факты', value: S.facts }, { name: 'Эпизоды', value: S.episodes }, { name: 'Профиль', value: S.profile }] }] });
  if (!j.ok || !j.data || !j.data.ok) { const m = esc((j.data && j.data.error) || j.error); $('#chAct').innerHTML = '<div class="err">Журнал недоступен: ' + m + '</div>'; $('#chAct').style.minHeight = '0'; $('#pairs').innerHTML = '<div class="err">Журнал недоступен: ' + m + '</div>'; $('#actInfo').textContent = ''; return; }
  const c = j.data.changes, cnt = {}; c.forEach((x) => { cnt[x.action] = (cnt[x.action] || 0) + 1; });
  $('#actInfo').textContent = 'ПОСЛЕДНИЕ ' + c.length;
  const names = Object.keys(cnt);
  if (!names.length) { $('#chAct').innerHTML = '<div class="empty">Владелец пока ничего не правил.</div>'; $('#chAct').style.minHeight = '0'; } else chart('#chAct', { grid: { left: 40, right: 12, top: 12, bottom: 28 }, tooltip: {}, xAxis: { type: 'category', data: names, axisLine: { lineStyle: { color: '#335' } } }, yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(150,225,235,.1)' } } }, series: [{ type: 'bar', data: names.map((n) => cnt[n]), itemStyle: { color: '#7ff5ef' }, barMaxWidth: 36 }] });
  pairs = c.filter((x) => x.action === 'correct' && x.old && x.new);
  $('#pairInfo').textContent = pairs.length + ' ПАР';
  $('#pairs').innerHTML = pairs.length ? '<table class="tbl"><thead><tr><th>Время</th><th>Запись</th><th>Было</th><th>Стало</th></tr></thead><tbody>' + pairs.map((x) => '<tr><td>' + esc(when(x.ts)) + '</td><td>' + esc(x.ref) + '</td><td>' + esc(x.old) + '</td><td>' + esc(x.new) + '</td></tr>').join('') + '</tbody></table>' : '<div class="empty">Исправлений пока нет: пары появятся, когда вы поправите записи на странице «Память».</div>';
}
$('#tRefresh').addEventListener('click', async () => { await Promise.all([progress(true), data()]); toast('Данные обновлены'); });
$('#tJsonl').addEventListener('click', () => { if (!pairs.length) { toast('Нет исправлений для экспорта', true); return; } download('nox-corrections.jsonl', pairs.map((x) => JSON.stringify({ ref: x.ref, ts: x.ts, before: x.old, after: x.new, reason: x.reason || null })).join('\n') + '\n', 'application/x-ndjson'); toast('Экспортировано пар: ' + pairs.length); });
addEventListener('resize', () => charts.forEach((c) => c.resize()));
progress(false); data();
