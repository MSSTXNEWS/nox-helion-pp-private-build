/* Виджеты: часы мира (Intl), карта (Leaflet), службы, задачи, заметка. Порядок карточек - Sortable, сохраняется в браузере. Данных не выдумываем. */
import { $, esc, ls, probeAll, pad } from './nox-api.js';
import './nox-nav.js';
const CITIES = [['Москва', 55.7558, 37.6173, 'Europe/Moscow'], ['Мадрид', 40.4168, -3.7038, 'Europe/Madrid'], ['Лондон', 51.5074, -0.1278, 'Europe/London'], ['Берлин', 52.52, 13.405, 'Europe/Berlin'], ['Стамбул', 41.0082, 28.9784, 'Europe/Istanbul'], ['Дубай', 25.2048, 55.2708, 'Asia/Dubai'], ['Нью-Йорк', 40.7128, -74.006, 'America/New_York'], ['Токио', 35.6762, 139.6503, 'Asia/Tokyo']];
/* порядок карточек */
const wg = $('#wg'), ORD = 'nox.widgets.order';
try { const o = JSON.parse(ls.get(ORD, '[]')); o.forEach((k) => { const n = wg.querySelector('[data-w="' + k + '"]'); if (n) wg.appendChild(n); }); } catch (e) { /* порядок по умолчанию */ }
if (window.Sortable) window.Sortable.create(wg, { animation: 160, handle: '.wh', ghostClass: 'drag', onEnd: () => ls.set(ORD, JSON.stringify([...wg.children].map((c) => c.dataset.w))) });
$('#wReset').addEventListener('click', () => { ls.set(ORD, '[]'); location.reload(); });
/* часы */
const zones = [['Здесь', Intl.DateTimeFormat().resolvedOptions().timeZone]].concat(CITIES.slice(0, 3).map((c) => [c[0], c[3]]), [['UTC', 'UTC']]);
function clocks() { $('#clocks').innerHTML = zones.map((z) => { const d = new Date(), f = (o) => new Intl.DateTimeFormat('ru-RU', Object.assign({ timeZone: z[1] }, o)).format(d); return '<div class="clk"><span class="mono">' + esc(z[0]) + '</span><b>' + f({ hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + '</b><small>' + esc(f({ weekday: 'short', day: 'numeric', month: 'short' })) + '</small></div>'; }).join(''); }
clocks(); setInterval(clocks, 1000);
/* карта */
const sel = $('#city'); sel.innerHTML = CITIES.map((c, i) => '<option value="' + i + '">' + esc(c[0]) + '</option>').join('');
let map = null, mk = null;
if (!window.L) { $('#map').innerHTML = '<div class="empty">Leaflet не загрузился (vendor/nox-extra/leaflet.js).</div>'; $('#mapSt').textContent = 'НЕТ БИБЛИОТЕКИ'; }
else {
  map = window.L.map('map', { zoomControl: true, attributionControl: true }).setView([CITIES[0][1], CITIES[0][2]], 5);
  let loaded = 0, failed = 0; const tl = window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; участники <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' }).addTo(map);
  tl.on('tileload', () => { loaded++; $('#mapSt').textContent = 'ПЛИТКИ OSM: ЗАГРУЖЕНЫ'; $('#mapNote').textContent = ''; }); tl.on('tileerror', () => { failed++; if (!loaded) { $('#mapSt').textContent = 'ПЛИТКИ НЕДОСТУПНЫ'; $('#mapNote').textContent = 'Плитки карты берутся с tile.openstreetmap.org напрямую браузером; без интернета видна только метка и сетка.'; } });
  mk = window.L.marker([CITIES[0][1], CITIES[0][2]], { icon: window.L.icon({ iconUrl: './vendor/nox-extra/images/marker-icon.png', iconSize: [25, 41], iconAnchor: [12, 41] }) }).addTo(map);
  sel.addEventListener('change', () => { const c = CITIES[+sel.value]; map.setView([c[1], c[2]], 6); mk.setLatLng([c[1], c[2]]); });
  new ResizeObserver(() => map.invalidateSize()).observe($('#map'));
}
/* службы и задачи */
async function svc() { const P = await probeAll(false); $('#svcT').textContent = P.services.filter((s) => s.state === 'ok').length + ' / ' + P.services.length + ' В СТРОЮ'; $('#svc').innerHTML = P.services.map((s) => '<li><i class="led ' + s.state + '"></i> ' + esc(s.name) + ' <span class="muted mono">' + (s.state === 'ok' ? (s.ms != null ? s.ms + ' мс' : 'в строю') : 'недоступно') + '</span></li>').join(''); }
svc(); setInterval(svc, 15000);
const tasks = ((ls.json('nox.tasks.v1', { tasks: [] }).tasks) || []).filter((t) => t && t.title), COL = { queue: 'Очередь', doing: 'В работе', review: 'Проверка', done: 'Готово' };
const board = tasks.filter((t) => t.kind !== 'event'), today = new Date().toISOString().slice(0, 10), next = tasks.filter((t) => t.due && t.due >= today && t.col !== 'done').sort((a, b) => a.due.localeCompare(b.due))[0];
$('#tkT').textContent = board.length ? board.length + ' ЗАДАЧ' : 'ПУСТО';
$('#tk').innerHTML = board.length ? '<dl class="kv">' + Object.keys(COL).map((k) => '<dt>' + COL[k] + '</dt><dd>' + board.filter((t) => (t.col || 'queue') === k).length + '</dd>').join('') + '<dt>Ближайший срок</dt><dd>' + (next ? esc(next.title.slice(0, 40)) + ' · ' + esc(next.due.slice(8) + '.' + next.due.slice(5, 7)) : 'нет') + '</dd></dl>' : '<div class="empty">Задач пока нет. Добавьте их в разделе «Проекты».</div>';
/* заметка */
const nt = $('#note'); nt.value = ls.get('nox.widgets.note', ''); let tm = 0; nt.addEventListener('input', () => { clearTimeout(tm); tm = setTimeout(() => { ls.set('nox.widgets.note', nt.value); $('#noteT').textContent = 'сохранено ' + pad(new Date().getHours()) + ':' + pad(new Date().getMinutes()); }, 400); });
