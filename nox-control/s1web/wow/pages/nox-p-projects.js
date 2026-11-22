/* Проекты и задачи: канбан (Sortable) Очередь / В работе / Проверка / Готово + календарь (FullCalendar: события и сроки карточек).
   Хранение: localStorage 'nox.tasks.v1' + зеркало в IndexedDB (Dexie); экспорт/импорт JSON, экспорт ICS; API задач NOX используется, если панель S2 его отдаёт;
   напоминания и уведомления через nox-notify.js (Notification API + sw.js). */
import { $, $$, esc, ls, call, apiProbe, download, toast, ymd } from './nox-api.js';
import { ready } from './nox-nav.js';
import * as NN from './nox-notify.js';
const KEY = 'nox.tasks.v1', COLS = [['queue', 'Очередь'], ['doing', 'В работе'], ['review', 'Проверка'], ['done', 'Готово']];
const norm = (t) => Object.assign({ kind: 'task', owner: '', project: '', due: '', time: '', note: '', created: Date.now() }, t, { col: t.col === 'todo' ? 'queue' : COLS.some((c) => c[0] === t.col) ? t.col : 'queue', kind: t.kind === 'event' ? 'event' : 'task' });
let tasks = (ls.json(KEY, { tasks: [] }).tasks || []).filter((t) => t && t.id && t.title).map(norm);
let proj = '', cal = null, editId = null, db = null;
/* IndexedDB (Dexie): зеркало, на случай если localStorage очищен */
try { if (window.Dexie) { db = new window.Dexie('nox-tasks'); db.version(1).stores({ tasks: 'id' }); } } catch (e) { db = null; }
const mirror = () => { if (db) db.tasks.clear().then(() => db.tasks.bulkPut(JSON.parse(JSON.stringify(tasks)))).catch(() => {}); };
const save = () => { if (!ls.setJson(KEY, { v: 2, tasks })) toast('localStorage недоступен: задачи сохранены только в IndexedDB', true); mirror(); NN.checkReminders && NN.checkReminders(); };
const uid = () => 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const today = () => ymd(new Date());
const colName = (c) => (COLS.find((x) => x[0] === c) || [0, c])[1];
const board = () => tasks.filter((t) => t.kind !== 'event');
const visible = (a) => (a || tasks).filter((t) => !proj || (t.project || 'Общий') === proj);
$$('#aCol,#dCol').forEach((s) => { s.innerHTML = COLS.map((c) => '<option value="' + c[0] + '">' + c[1] + '</option>').join(''); });

function renderChips() {
  const names = [...new Set(tasks.map((t) => t.project || 'Общий'))].sort(); if (proj && !names.includes(proj)) proj = '';
  $('#projList').innerHTML = names.map((n) => '<option value="' + esc(n) + '">').join('');
  $('#ownList').innerHTML = [...new Set(tasks.map((t) => t.owner).filter(Boolean))].sort().map((n) => '<option value="' + esc(n) + '">').join('');
  $('#chips').innerHTML = '<button type="button" class="tag' + (!proj ? ' on' : '') + '" data-p="">Все · ' + tasks.length + '</button>' + names.map((n) => '<button type="button" class="tag' + (proj === n ? ' on' : '') + '" data-p="' + esc(n) + '">' + esc(n) + ' · ' + tasks.filter((t) => (t.project || 'Общий') === n).length + '</button>').join('');
}
function taskHtml(t) {
  const late = t.due && t.due < today() && t.col !== 'done', btn = (a, ic, tt) => '<button type="button" data-a="' + a + '" aria-label="' + tt + '" title="' + tt + '"><sl-icon library="tabler" name="' + ic + '"></sl-icon></button>';
  return '<article class="task' + (late ? ' late' : '') + (t.col === 'done' ? ' done' : '') + '" data-id="' + esc(t.id) + '"><div class="tt">' + esc(t.title) + '</div><div class="tb">' + (t.col !== COLS[0][0] ? btn('prev', 'chevron-left', 'В колонку левее') : '') + (t.col !== COLS[3][0] ? btn('next', 'chevron-right', 'В колонку правее') : '') + btn('edit', 'pencil', 'Изменить') + btn('del', 'x', 'Удалить').replace('<button', '<button class="x"') + '</div>'
    + '<div class="tm"><span class="tag">' + esc(t.project || 'Общий') + '</span>' + (t.owner ? '<span class="tag on" title="Владелец">' + esc(t.owner) + '</span>' : '') + (t.due ? '<span class="tag' + (late ? ' bad' : '') + '">' + esc(t.due) + (late ? ' · просрочено' : '') + '</span>' : '') + (t.note ? '<span class="tag" title="' + esc(t.note) + '">заметка</span>' : '') + '</div></article>';
}
let sorts = [];
function renderBoard() {
  const box = $('#vBoardBox'); sorts.forEach((s) => s.destroy()); sorts = [];
  box.innerHTML = COLS.map((c) => { const l = visible(board()).filter((t) => t.col === c[0]); return '<section class="card kcol" data-col="' + c[0] + '"><h2>' + c[1] + '<span class="r">' + l.length + '</span></h2><div class="klist" data-col="' + c[0] + '">' + l.map(taskHtml).join('') + '</div></section>'; }).join('');
  $$('.klist', box).forEach((l) => sorts.push(window.Sortable.create(l, { group: 'tasks', animation: 160, delay: 140, delayOnTouchOnly: true, ghostClass: 'sortable-ghost', chosenClass: 'sortable-chosen', filter: '.tb', preventOnFilter: false, onEnd: onDrop })));
}
function onDrop() {
  const order = [], shown = new Set();
  $$('#vBoardBox .klist').forEach((l) => $$('.task', l).forEach((n) => { const t = tasks.find((x) => x.id === n.dataset.id); if (t) { t.col = l.dataset.col; order.push(t); shown.add(t.id); } }));
  tasks = order.concat(tasks.filter((t) => !shown.has(t.id))); save(); renderAll(); refetch();
}
const refetch = () => { if (cal) cal.refetchEvents(); };
function renderSum() {
  const b = board(), t0 = today(), wk = ymd(new Date(Date.now() + 7 * 864e5)), act = visible(b), open = act.filter((t) => t.col !== 'done');
  const cells = [['Всего', act.length], ['В работе', act.filter((t) => t.col === 'doing').length], ['Просрочено', open.filter((t) => t.due && t.due < t0).length], ['Срок на неделе', open.filter((t) => t.due && t.due >= t0 && t.due <= wk).length], ['Готово', act.filter((t) => t.col === 'done').length]];
  const nxt = open.filter((t) => t.due && t.due >= t0).sort((x, y) => x.due.localeCompare(y.due)).slice(0, 5);
  $('#psum').innerHTML = cells.map((c) => '<div class="clk"><span class="mono">' + c[0] + '</span><b>' + c[1] + '</b></div>').join('');
  $('#pnext').innerHTML = act.length ? (nxt.length ? nxt.map((t) => '<li><span class="mono">' + esc(t.due.slice(8) + '.' + t.due.slice(5, 7)) + '</span> ' + esc(t.title) + (t.project ? ' <span class="muted">· ' + esc(t.project) + '</span>' : '') + '</li>').join('') : '<li class="muted">Задачи без срока: назначьте дату в карточке.</li>') : '<li class="muted">Задач пока нет: добавьте первую в форме выше.</li>';
}
function renderAll() { renderChips(); renderBoard(); renderSum(); }

/* ---------- диалог ---------- */
const kindUi = () => { const ev = $('#dKind').value === 'event'; $('#dTimeW').hidden = !ev; $('#dColW').hidden = ev; };
$('#dKind').addEventListener('change', kindUi);
async function openDlg(id, due, kind) {
  await ready; const t = id ? tasks.find((x) => x.id === id) : null; editId = id || null;
  $('#dlg').label = t ? (t.kind === 'event' ? 'Изменить событие' : 'Изменить задачу') : 'Новая запись';
  $('#dKind').value = t ? t.kind : kind || 'task'; $('#dTitle').value = t ? t.title : ''; $('#dProj').value = t ? t.project || '' : proj; $('#dOwner').value = t ? t.owner || '' : ''; $('#dDue').value = t ? t.due || '' : due || ''; $('#dTime').value = t ? t.time || '' : ''; $('#dCol').value = t ? t.col : 'queue'; $('#dNote').value = t ? t.note || '' : '';
  kindUi(); $('#dDel').style.display = t ? '' : 'none'; $('#dlg').show(); setTimeout(() => $('#dTitle').focus(), 250);
}
function saveDlg() {
  const title = $('#dTitle').value.trim(); if (!title) { $('#dTitle').focus(); return; }
  const f = { title, kind: $('#dKind').value, project: $('#dProj').value.trim(), owner: $('#dOwner').value.trim(), due: $('#dDue').value, time: $('#dKind').value === 'event' ? $('#dTime').value : '', col: $('#dCol').value, note: $('#dNote').value.trim() };
  if (f.kind === 'event' && !f.due) { toast('Для события нужна дата', true); $('#dDue').focus(); return; }
  if (editId) Object.assign(tasks.find((x) => x.id === editId), f); else tasks.unshift(norm(Object.assign({ id: uid(), created: Date.now() }, f)));
  save(); $('#dlg').hide(); renderAll(); refetch(); toast(editId ? 'Сохранено' : f.kind === 'event' ? 'Событие добавлено' : 'Задача добавлена');
}
function delTask(id) { const t = tasks.find((x) => x.id === id); if (!t) return; tasks = tasks.filter((x) => x.id !== id); save(); renderAll(); refetch(); toast('Удалено: ' + t.title); }
$('#dSave').addEventListener('click', saveDlg); $('#dForm').addEventListener('submit', (e) => { e.preventDefault(); saveDlg(); });
$('#dCancel').addEventListener('click', () => $('#dlg').hide());
$('#dDel').addEventListener('click', () => { if (editId) { delTask(editId); $('#dlg').hide(); } });
$('#addForm').addEventListener('submit', (e) => {
  e.preventDefault(); const title = $('#aTitle').value.trim(); if (!title) return;
  tasks.unshift(norm({ id: uid(), created: Date.now(), title, project: $('#aProj').value.trim(), owner: $('#aOwner').value.trim(), due: $('#aDue').value, col: $('#aCol').value }));
  save(); $('#aTitle').value = ''; renderAll(); refetch(); toast('Задача добавлена');
});
$('#vBoardBox').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-a]'); if (!b) return; const id = b.closest('.task').dataset.id, t = tasks.find((x) => x.id === id);
  if (b.dataset.a === 'edit') openDlg(id); else if (b.dataset.a === 'del') delTask(id);
  else { const i = COLS.findIndex((c) => c[0] === t.col) + (b.dataset.a === 'next' ? 1 : -1); if (COLS[i]) { t.col = COLS[i][0]; save(); renderAll(); refetch(); } }
});
$('#vBoardBox').addEventListener('dblclick', (e) => { const t = e.target.closest('.task'); if (t && !e.target.closest('button')) openDlg(t.dataset.id); });
$('#chips').addEventListener('click', (e) => { const b = e.target.closest('button[data-p]'); if (!b) return; proj = b.dataset.p; renderAll(); refetch(); });

/* ---------- календарь ---------- */
function mkCal() {
  cal = new window.FullCalendar.Calendar($('#cal'), {
    initialView: 'dayGridMonth', locale: 'ru', firstDay: 1, height: 'auto', fixedWeekCount: false, editable: true, dayMaxEvents: 3, eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
    headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,listMonth' },
    buttonText: { today: 'Сегодня', month: 'Месяц', list: 'Список' }, noEventsText: 'Нет событий и сроков в этом месяце',
    events: (_i, ok) => ok(visible().filter((t) => t.due).map((t) => ({ id: t.id, title: t.title, start: t.kind === 'event' && t.time ? t.due + 'T' + t.time : t.due, allDay: !(t.kind === 'event' && t.time), classNames: [t.col === 'done' ? 'done' : '', t.kind === 'event' ? 'ev' : 'dl'] }))),
    dateClick: (i) => openDlg(null, i.dateStr, 'event'), eventClick: (i) => openDlg(i.event.id),
    eventDrop: (i) => { const t = tasks.find((x) => x.id === i.event.id); if (t) { t.due = ymd(i.event.start); save(); renderAll(); toast('Дата перенесена на ' + t.due); } }
  });
  cal.render();
}
function setView(v) {
  $('#vBoardBox').hidden = v !== 'board'; $('#vSumBox').hidden = v !== 'board'; $('#vCalBox').hidden = v !== 'cal';
  $('#vBoard').setAttribute('aria-pressed', String(v === 'board')); $('#vCal').setAttribute('aria-pressed', String(v === 'cal'));
  if (v === 'cal') { if (!cal) mkCal(); else { cal.refetchEvents(); cal.updateSize(); } }
}
$('#vBoard').addEventListener('click', () => setView('board')); $('#vCal').addEventListener('click', () => setView('cal'));

/* ---------- экспорт / импорт ---------- */
$('#exp').addEventListener('click', () => { download('nox-tasks-' + today() + '.json', JSON.stringify({ schema: 'nox-tasks-v2', exported: new Date().toISOString(), tasks }, null, 2)); toast('Экспортировано записей: ' + tasks.length); });
const icsT = (s) => String(s).replace(/\\/g, '\\\\').replace(/;/g, '\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
$('#expIcs').addEventListener('click', () => {
  const d = tasks.filter((t) => t.due); if (!d.length) { toast('Нет записей с датой: в ICS нечего писать', true); return; }
  const nx = (s) => { const x = new Date(s + 'T00:00:00'); x.setDate(x.getDate() + 1); return ymd(x).replace(/-/g, ''); }, stamp = new Date().toISOString().replace(/[-:]|\.\d+/g, '');
  const L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//NOX HELION//tasks//RU'].concat(...d.map((t) => { const timed = t.kind === 'event' && t.time, dt = t.due.replace(/-/g, '');
    return ['BEGIN:VEVENT', 'UID:' + t.id + '@nox-helion', 'DTSTAMP:' + stamp, timed ? 'DTSTART:' + dt + 'T' + t.time.replace(':', '') + '00' : 'DTSTART;VALUE=DATE:' + dt, timed ? 'DTEND:' + dt + 'T' + t.time.replace(':', '') + '00' : 'DTEND;VALUE=DATE:' + nx(t.due), 'SUMMARY:' + icsT(t.title), 'DESCRIPTION:' + icsT((t.project || 'Общий') + (t.owner ? ' · ' + t.owner : '') + ' · ' + colName(t.col) + (t.note ? '\n' + t.note : '')), 'END:VEVENT']; })).concat(['END:VCALENDAR']);
  download('nox-tasks-' + today() + '.ics', L.join('\r\n'), 'text/calendar'); toast('ICS: событий ' + d.length);
});
$('#imp').addEventListener('click', () => $('#impFile').click());
$('#impFile').addEventListener('change', async (e) => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  try {
    const j = JSON.parse(await f.text()), a = Array.isArray(j) ? j : j.tasks; if (!Array.isArray(a)) throw new Error('нет массива tasks');
    let n = 0; a.forEach((x) => { if (!x || !x.title) return; const t = norm({ id: String(x.id || uid()), title: String(x.title).slice(0, 200), project: String(x.project || ''), owner: String(x.owner || ''), due: /^\d{4}-\d\d-\d\d$/.test(x.due || '') ? x.due : '', time: /^\d\d:\d\d$/.test(x.time || '') ? x.time : '', col: x.col, kind: x.kind, note: String(x.note || ''), created: x.created || Date.now() }); const i = tasks.findIndex((y) => y.id === t.id); if (i >= 0) tasks[i] = t; else tasks.push(t); n++; });
    save(); renderAll(); refetch(); toast('Импортировано записей: ' + n);
  } catch (err) { toast('Файл не принят: ' + err.message, true); }
});

/* ---------- API задач NOX (если панель S2 подключена) ---------- */
let apiTasks = null;
async function checkApi(force) {
  const tag = $('#apiTag'); tag.className = 'tag'; tag.textContent = 'API ЗАДАЧ: ПРОВЕРКА'; $('#apiAct').hidden = true;
  const a = await apiProbe(force);
  if (!a.ok) { tag.className = 'tag warn'; tag.textContent = 'API ЗАДАЧ НЕТ · ХРАНЕНИЕ В БРАУЗЕРЕ'; tag.title = 'Панель S2 /api не подключена: ' + a.error + '. Клик: проверить снова'; return; }
  for (const p of ['/api/nox/tasks', '/api/tasks']) { const r = await call(p); const arr = r.ok && r.data && (Array.isArray(r.data) ? r.data : r.data.tasks); if (Array.isArray(arr)) { apiTasks = arr; tag.className = 'tag on'; tag.textContent = 'API ЗАДАЧ: ' + arr.length; $('#apiAct').hidden = false; return; } }
  tag.className = 'tag warn'; tag.textContent = 'ПАНЕЛЬ ЕСТЬ, API ЗАДАЧ НЕТ'; tag.title = 'Ни /api/nox/tasks, ни /api/tasks не вернули список';
}
$('#apiImp').addEventListener('click', () => {
  let n = 0; (apiTasks || []).forEach((x) => { const title = x.title || x.name || x.text; if (!title) return; const id = 'api:' + (x.id || title), st = String(x.status || x.col || '').toLowerCase(), col = /done|готов|complete/.test(st) ? 'done' : /review|провер/.test(st) ? 'review' : /doing|progress|работ/.test(st) ? 'doing' : 'queue';
    const t = norm({ id, title: String(title).slice(0, 200), project: String(x.project || 'NOX'), owner: String(x.owner || x.assignee || ''), due: /^\d{4}-\d\d-\d\d/.test(x.due || x.deadline || '') ? (x.due || x.deadline).slice(0, 10) : '', col, note: String(x.note || x.description || '') }); const i = tasks.findIndex((y) => y.id === id); if (i >= 0) tasks[i] = Object.assign(tasks[i], t); else { tasks.push(t); n++; } });
  save(); renderAll(); refetch(); toast('Из NOX добавлено: ' + n);
});
$('#apiTag').addEventListener('click', () => checkApi(true));

/* ---------- уведомления ---------- */
function ntag() { const s = NN.state(), t = $('#ntag'), on = s === 'granted' && NN.enabled(); t.className = 'tag' + (on ? ' on' : s === 'denied' || s === 'unsupported' ? ' bad' : ' warn'); t.textContent = on ? 'НАПОМИНАНИЯ: ВКЛ' : s === 'granted' ? 'НАПОМИНАНИЯ: ВЫКЛ' : s === 'denied' ? 'УВЕДОМЛЕНИЯ ЗАПРЕЩЕНЫ БРАУЗЕРОМ' : s === 'unsupported' ? 'УВЕДОМЛЕНИЙ НЕТ В БРАУЗЕРЕ' : 'ВКЛЮЧИТЬ НАПОМИНАНИЯ'; t.title = NN.STATE_RU[s] + (s === 'denied' ? '. Разрешите уведомления для этого сайта в настройках браузера.' : ''); }
$('#ntag').addEventListener('click', async () => {
  const s = NN.state();
  if (s === 'granted') { NN.setEnabled(!NN.enabled()); ntag(); toast(NN.enabled() ? 'Напоминания включены' : 'Напоминания выключены'); return; }
  const r = await NN.request(); ntag();
  if (r === 'granted') { NN.setEnabled(true); ntag(); toast('Напоминания включены'); await NN.show('NOX', 'Напоминания по срокам задач включены', 'nox-test', 'projects.html'); NN.checkReminders(); } else toast(r === 'denied' ? 'Уведомления запрещены: напоминаний не будет' : 'Уведомления не поддерживаются этим браузером', true);
});

(async () => {
  if (!tasks.length && db) { try { const a = await db.tasks.toArray(); if (a.length) { tasks = a.map(norm); ls.setJson(KEY, { v: 2, tasks }); toast('Задачи восстановлены из IndexedDB: ' + a.length); } } catch (e) { /* пусто */ } }
  renderAll(); mirror();
})();
renderAll(); checkApi(false); ntag();
