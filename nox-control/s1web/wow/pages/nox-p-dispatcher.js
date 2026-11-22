/* Диспетчер: живые данные шлюза (/glm/v1/nox/stats), журнал ответов чата (с подписью уровня из ответа шлюза), задачи и очередь панели S2 (/api, если подключена). Нет данных - свёрнутое честное состояние. */
import { $, esc, ls, call, apiProbe, hhmmss } from './nox-api.js';
import './nox-nav.js';
const none = (title, why) => '<details class="card fold nodata"><summary><i class="led warn"></i>' + esc(title) + '<span class="mono">нет данных · подробнее</span></summary><p class="muted" style="font-size:12.5px">' + esc(why) + '</p></details>';
async function gw() {
  const r = await call('/glm/v1/nox/stats'); $('#gwT').textContent = r.ok ? 'ОПРОС ' + hhmmss() : 'НЕДОСТУПЕН';
  if (!r.ok || !r.data) { $('#gw').innerHTML = none('Шлюз не отвечает', 'Запрос /glm/v1/nox/stats: ' + (r.error || 'пустой ответ')); $('#speed').innerHTML = none('Скорость недоступна', 'Без ответа шлюза скорость и кэш неизвестны.'); return; }
  const S = r.data, act = S.active; const n = Array.isArray(act) ? act.length : act;
  $('#gw').innerHTML = '<dl class="kv"><dt>Активных запросов</dt><dd>' + esc(n == null ? '—' : n) + '</dd><dt>Быстрый уровень</dt><dd>' + (S.fast_available ? 'отвечает' : 'недоступен') + '</dd><dt>Префикс кэша</dt><dd class="mono">' + esc(S.prefix || '—') + '</dd></dl>';
  const sp = S.speed || {}, f = (k) => (sp[k] && sp[k].tps != null ? sp[k].tps + ' ток/с' + (sp[k].basis && /^measured/.test(sp[k].basis) ? ' (измерено)' : ' (оценка)') : '—'); const c = S.cache || {};
  $('#speed').innerHTML = '<dl class="kv"><dt>Глубокий (GLM)</dt><dd>' + esc(f('deep')) + '</dd><dt>Быстрый</dt><dd>' + esc(f('fast')) + '</dd><dt>Кэш: запросов</dt><dd>' + esc(c.requests != null ? c.requests : c.n != null ? c.n : '—') + '</dd><dt>Кэш: доля попаданий</dt><dd>' + esc(c.hit_ratio != null ? Math.round(c.hit_ratio * 100) + '%' : '—') + '</dd></dl>';
}
function log() {
  let th = []; try { th = JSON.parse(ls.get('nox.wow.threads', '[]')); } catch (e) { th = []; }
  const rows = []; th.forEach((t) => (t.msgs || []).forEach((m) => { if (m.role === 'assistant' && m.via) rows.push([m.ts || t.ts, t.title, m.via, m.err ? 'ошибка' : 'ок']); }));
  rows.sort((a, b) => b[0] - a[0]); $('#logN').textContent = rows.length ? 'ПОСЛЕДНИЕ ' + Math.min(rows.length, 30) : 'ПУСТО';
  $('#logT').innerHTML = rows.length ? '<thead><tr><th>Время</th><th>Диалог</th><th>Кто ответил</th><th>Итог</th></tr></thead><tbody>' + rows.slice(0, 30).map((r) => '<tr><td class="mono nw">' + esc(new Date(r[0]).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })) + '</td><td>' + esc(r[1]) + '</td><td class="mono">' + esc(r[2]) + '</td><td>' + esc(r[3]) + '</td></tr>').join('') + '</tbody>' : '<tbody><tr><td class="muted">Ответов с подписью уровня пока нет: задайте вопрос в «Резонансе». Подпись записывается только для новых ответов.</td></tr></tbody>';
}
async function s2() {
  const a = await apiProbe(true), box = $('#s2');
  if (!a.ok) { box.innerHTML = none('Задачи и очередь обучения (панель S2)', 'Панель S2 (/api) не подключена: ' + a.error + '. Задачи, очередь обучения и загрузки появятся здесь, когда панель будет подключена; старые страницы «Диспетчер задач» и «Загрузки» показывали то же самое состояние «нет данных» и убраны из меню.'); return; }
  let html = '';
  for (const [title, path] of [['Задачи', '/api/nox/tasks'], ['Прогресс обучения', '/api/nox/progress']]) { const r = await call(path); html += (r.ok && r.data) ? '<section class="card"><h2>' + esc(title) + '</h2><pre class="mono" style="white-space:pre-wrap;margin:0;font-size:12px;max-height:240px;overflow:auto">' + esc(JSON.stringify(r.data, null, 2).slice(0, 4000)) + '</pre></section>' : none(title, path + ': ' + (r.error || 'пустой ответ')); }
  box.innerHTML = html;
}
const all = () => { gw(); log(); s2(); }; $('#dRef').addEventListener('click', all); all(); setInterval(gw, 10000);
