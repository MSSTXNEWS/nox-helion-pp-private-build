/* Ядро: модели, тиры, параметры llama-server, активные запросы (с остановкой), проверка генерации, серверы. Только реальные ответы API. */
import { $, esc, call, probeAll, hhmmss, ST_RU, toast, basisRu } from './nox-api.js';
import './nox-nav.js';
let busy = false;
const kv = (o) => '<dl class="kv">' + Object.keys(o).map((k) => '<dt>' + esc(k) + '</dt><dd>' + esc(o[k]) + '</dd>').join('') + '</dl>';
async function run(manual) {
  if (busy) return; busy = true; $('#cRefresh').disabled = true;
  try {
    const [P, props] = await Promise.all([probeAll(manual), call('/glm/props')]);
    const byId = Object.fromEntries(P.services.map((s) => [s.id, s]));
    $('#tiers').innerHTML = ['deep', 'fast'].map((k) => { const s = byId[k], sp = P.stats.ok && P.stats.data.speed && P.stats.data.speed[k]; return '<section class="card c6 svc ' + s.state + '"><div class="svc-h"><i class="led ' + s.state + '"></i><b>' + (k === 'deep' ? 'Глубокий тир' : 'Быстрый тир') + '</b><span class="ms mono">' + s.ms + ' МС</span></div>'
      + (sp && s.state === 'ok' ? '<div class="big" style="margin:8px 0">' + sp.tps + '<small>ТОК/С · ' + (sp.basis === 'default' ? 'ОЦЕНКА ШЛЮЗА, ЕЩЁ НЕ ИЗМЕРЕНО' : basisRu(sp.basis).toUpperCase()) + '</small></div>' : '') + (s.error ? '<div class="err">' + esc(s.error) + '</div>' : '') + '<ul class="lines">' + s.lines.map((l) => '<li>' + esc(l) + '</li>').join('') + '</ul><div class="svc-st">' + ST_RU[s.state] + '</div></section>'; }).join('');
    const m = P.models; $('#mInfo').textContent = m.ms + ' МС';
    const list = m.ok && m.data && m.data.data;
    $('#models').innerHTML = list && list.length ? '<table class="tbl"><thead><tr><th>Модель</th><th>Владелец</th><th>Создана</th></tr></thead><tbody>' + list.map((x) => '<tr><td>' + esc(x.id) + '</td><td>' + esc(x.owned_by || '—') + '</td><td>' + (x.created ? new Date(x.created * 1000).toLocaleDateString('ru-RU') : '—') + '</td></tr>').join('') + '</tbody></table>' : '<div class="err">Список моделей недоступен: ' + esc(m.error || 'шлюз не вернул моделей') + '</div>';
    if (props.ok && props.data && typeof props.data === 'object') { const d = props.data, g = d.default_generation_settings || {}, o = {}; if (d.model_alias || d.model_path) o['модель'] = d.model_alias || d.model_path; if (g.n_ctx || d.n_ctx) o['контекст, ток.'] = g.n_ctx || d.n_ctx; if (d.total_slots != null) o['слотов'] = d.total_slots; if (d.build_info) o['сборка'] = d.build_info; $('#props').innerHTML = Object.keys(o).length ? kv(o) : '<div class="muted">llama-server ответил, но стандартных полей нет:</div>' + kv(Object.fromEntries(Object.keys(d).slice(0, 10).map((k) => [k, typeof d[k] === 'object' ? '{…}' : d[k]]))); }
    else $('#props').innerHTML = '<div class="err">llama-server не отдаёт параметры: ' + esc(props.error) + '</div>';
    const act = P.stats.ok && P.stats.data ? P.stats.data.active || [] : null; $('#actN').textContent = act ? act.length : '';
    $('#active').innerHTML = act === null ? '<div class="err">Шлюз недоступен: ' + esc(P.stats.error) + '</div>' : act.length ? act.map((a) => { const id = typeof a === 'object' ? a.id || a.request_id : a; return '<div class="frow" style="justify-content:space-between;padding:4px 0"><span class="mono">' + esc(typeof a === 'object' ? JSON.stringify(a).slice(0, 120) : a) + '</span><span class="seg"><button type="button" data-stop="' + esc(id) + '">Остановить</button></span></div>'; }).join('') : '<div class="empty">Сейчас нет активных запросов.</div>';
    $('#srv').innerHTML = '<table class="tbl"><thead><tr><th>Служба</th><th>Маршрут</th><th>Статус</th><th>Отклик</th><th>Подробности</th></tr></thead><tbody>' + P.services.map((s) => '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.sub) + '</td><td class="' + (s.state === 'ok' ? 'okc' : s.state === 'warn' ? 'warn' : 'err') + '">' + ST_RU[s.state] + '</td><td>' + s.ms + ' мс</td><td>' + esc(s.error || s.lines.join(' · ')) + '</td></tr>').join('') + '</tbody></table>';
    $('#cTime').textContent = 'ОБНОВЛЕНО ' + hhmmss();
  } finally { busy = false; $('#cRefresh').disabled = false; }
}
$('#cRefresh').addEventListener('click', () => run(true));
$('#active').addEventListener('click', async (e) => { const b = e.target.closest('button[data-stop]'); if (!b) return; b.disabled = true; const r = await call('/glm/v1/stop', { method: 'POST', body: { request_id: b.dataset.stop } }); if (r.ok) { toast(r.data && r.data.stopped ? 'Запрос остановлен' : 'Запрос уже завершился'); run(); } else { toast('Остановить не удалось: ' + r.error, true); b.disabled = false; } });
$('#gen').addEventListener('click', async () => {
  const b = $('#gen'), out = $('#genOut'); b.disabled = true; out.innerHTML = '<span class="muted">Запрос отправлен…</span>';
  const r = await call('/glm/v1/chat/completions', { method: 'POST', timeout: 90000, body: { messages: [{ role: 'user', content: 'Ответь одним словом: готов.' }], max_tokens: 24, stream: false } });
  b.disabled = false; const c = r.ok && r.data && r.data.choices && r.data.choices[0], txt = c && ((c.message && c.message.content) || c.text);
  out.innerHTML = txt ? '<div class="okc mono">ОТВЕТ ЗА ' + r.ms + ' МС</div><pre class="core">' + esc(txt) + '</pre>' : '<div class="err">Генерация не удалась: ' + esc(r.error || 'модель вернула пустой ответ') + '</div>';
  run();
});
run(); setInterval(() => { if (!document.hidden) run(); }, 10000);
