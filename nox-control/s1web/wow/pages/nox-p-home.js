/* Главная: реальные health-запросы ко всем службам NOX + локальные задачи. */
import { $, esc, ls, call, probeAll, hhmmss, ST_RU, ymd, basisRu } from './nox-api.js';
import './nox-nav.js';
let busy = false;
const tasksCard = () => {
  const t = (ls.json('nox.tasks.v1', { tasks: [] }).tasks || []), open = t.filter((x) => x.col !== 'done'), today = ymd(new Date()), late = open.filter((x) => x.due && x.due < today);
  const next = open.filter((x) => x.due && x.due >= today).sort((a, b) => a.due.localeCompare(b.due))[0];
  return '<article class="card svc ok"><div class="svc-h"><i class="led ok"></i><b>Задачи</b></div><div class="svc-sub">локально в браузере</div>'
    + '<ul class="lines"><li>открыто: ' + open.length + ' из ' + t.length + '</li><li' + (late.length ? ' class="err"' : '') + '>просрочено: ' + late.length + '</li><li>ближайшая: ' + (next ? esc(next.due + ' · ' + next.title) : 'нет срока') + '</li></ul><div class="svc-st"><a href="projects.html" class="okc">ОТКРЫТЬ ПРОЕКТЫ</a></div></article>';
};
function renderSvc(P) {
  $('#svc').innerHTML = P.services.map((s) => '<article class="card c3 svc ' + s.state + '"><div class="svc-h"><i class="led ' + s.state + '"></i><b>' + esc(s.name) + '</b><span class="ms mono">' + (s.ms != null ? s.ms + ' МС' : '') + '</span></div><div class="svc-sub">' + esc(s.sub) + '</div>'
    + (s.error ? '<div class="err">' + esc(s.error) + '</div>' : '') + (s.lines.length ? '<ul class="lines">' + s.lines.map((l) => '<li>' + esc(l) + '</li>').join('') + '</ul>' : '') + '<div class="svc-st">' + ST_RU[s.state] + '</div></article>').join('') + tasksCard().replace('class="card ', 'class="card c3 ');
  const ok = P.services.filter((s) => s.state === 'ok').length, bad = P.services.filter((s) => s.state === 'bad').length, n = P.services.length;
  $('#sumLed').className = 'led ' + (bad ? 'bad' : ok === n ? 'ok' : 'warn');
  $('#sumText').textContent = ok + ' ИЗ ' + n + ' СЛУЖБ В СТРОЮ' + (bad ? ' · НЕДОСТУПНО: ' + bad : '');
  $('#sumTime').textContent = 'ПОСЛЕДНИЙ ОПРОС ' + hhmmss();
}
function renderSpeed(P) {
  const r = P.stats, S = r.ok && r.data; $('#spMs').textContent = r.ms + ' МС';
  if (!S) { $('#speed').innerHTML = '<div class="err">Шлюз не отвечает: ' + esc(r.error) + '</div>'; return; }
  const c = S.cache || {}, f = (k) => (S.speed && S.speed[k] ? S.speed[k].tps + ' <small>ТОК/С · ' + (S.speed[k].basis === 'default' ? 'ОЦЕНКА' : basisRu(S.speed[k].basis).toUpperCase()) + '</small>' : '—');
  $('#speed').innerHTML = '<dl class="kv"><dt>Глубокий</dt><dd class="big" style="font-size:22px">' + f('deep') + '</dd><dt>Быстрый</dt><dd class="big" style="font-size:22px">' + (S.fast_available ? f('fast') : '<small>НЕ ПОДКЛЮЧЁН</small>') + '</dd><dt>Попадание в кэш</dt><dd>' + (c.hit_ratio != null ? Math.round(c.hit_ratio * 100) + '%' : 'нет запросов') + '</dd><dt>Запросов к шлюзу</dt><dd>' + (c.requests || 0) + '</dd><dt>Активных сейчас</dt><dd>' + (S.active || []).length + '</dd></dl>';
}
function renderMem(P) {
  const r = P.mem, M = r.ok && r.data && r.data.ok && r.data.stats;
  $('#memBox').innerHTML = M ? '<dl class="kv"><dt>Фактов</dt><dd class="big" style="font-size:22px">' + M.facts + '</dd><dt>Эпизодов</dt><dd>' + M.episodes + '</dd><dt>Профиль</dt><dd>' + M.profile + '</dd><dt>Правок владельца</dt><dd>' + M.changes + '</dd><dt>Полнотекстовый поиск</dt><dd>' + (M.fts5 ? 'FTS5' : 'LIKE') + '</dd></dl>' : '<div class="err">Служба памяти недоступна: ' + esc(r.error || 'нет статистики') + '</div>';
}
async function renderResume() {
  const r = await call('/glm/v1/resume', { timeout: 12000 });
  $('#resume').innerHTML = r.ok && r.data && r.data.text ? '<pre class="core">' + esc(r.data.text) + '</pre>' : '<div class="err">' + (r.ok ? 'Шлюз вернул пустое резюме.' : 'Резюме недоступно: ' + esc(r.error)) + '</div>';
}
async function run(manual) {
  if (busy) return; busy = true; const b = $('#refresh'); b.disabled = true;
  try { const P = await probeAll(manual); renderSvc(P); renderSpeed(P); renderMem(P); await renderResume(); } finally { busy = false; b.disabled = false; }
}
$("#refresh").addEventListener("click", () => run(true));
run(); setInterval(() => { if (!document.hidden) run(); }, 15000);
