/* Календарь: FullCalendar поверх общего хранилища задач 'nox.tasks.v1' (то же, что в «Проектах»): сроки задач и события, создание кликом, перенос перетаскиванием, ICS. */
import { $, esc, ls, download, toast, ymd } from './nox-api.js';
import './nox-nav.js';
const KEY = 'nox.tasks.v1';
const read = () => ((ls.json(KEY, { tasks: [] }).tasks) || []).filter((t) => t && t.id && t.title);
let tasks = read(), cal = null, editId = null;
const save = () => { if (!ls.setJson(KEY, { v: 2, tasks })) toast('localStorage недоступен: изменения не сохранены', true); };
const uid = () => 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const dlg = $('#dlg');
function fetchEv(_i, ok) { tasks = read(); ok(tasks.filter((t) => t.due).map((t) => ({ id: t.id, title: t.title, start: t.kind === 'event' && t.time ? t.due + 'T' + t.time : t.due, allDay: !(t.kind === 'event' && t.time), classNames: [t.col === 'done' ? 'done' : '', t.kind === 'event' ? 'ev' : 'dl'] }))); }
function soon() {
  const now = new Date(), a = ymd(now), b = new Date(now.getTime() + 14 * 864e5), z = ymd(b);
  const L = tasks.filter((t) => t.due && t.due >= a && t.due <= z && t.col !== 'done').sort((x, y) => (x.due + (x.time || '')).localeCompare(y.due + (y.time || '')));
  $('#soonN').textContent = L.length ? L.length + ' ЗАПИС.' : '';
  $('#soon').innerHTML = L.length ? L.slice(0, 20).map((t) => '<li><span class="mono">' + esc(t.due.slice(8) + '.' + t.due.slice(5, 7)) + (t.time ? ' ' + esc(t.time) : '') + '</span> ' + esc(t.title) + (t.kind === 'event' ? '' : ' <span class="muted">(срок задачи)</span>') + '</li>').join('') : '<li class="muted">В ближайшие две недели записей нет.</li>';
}
function openDlg(id, due) {
  editId = id; const t = id ? tasks.find((x) => x.id === id) : null; $('#dTitle').value = t ? t.title : ''; $('#dDue').value = t ? t.due : due || ymd(new Date()); $('#dTime').value = t ? t.time || '' : ''; $('#dNote').value = t ? t.note || '' : '';
  $('#dDel').hidden = !t; dlg.label = t ? (t.kind === 'event' ? 'Событие' : 'Срок задачи') : 'Новое событие'; dlg.show();
}
function commit() {
  const title = $('#dTitle').value.trim(), due = $('#dDue').value; if (!title || !due) { toast('Нужны название и дата', true); return; }
  const t = editId ? tasks.find((x) => x.id === editId) : null;
  if (t) { t.title = title; t.due = due; t.time = $('#dTime').value; t.note = $('#dNote').value; } else tasks.push({ id: uid(), kind: 'event', col: 'queue', title, due, time: $('#dTime').value, note: $('#dNote').value, project: '', owner: '', created: Date.now() });
  save(); dlg.hide(); cal.refetchEvents(); soon(); toast(t ? 'Сохранено' : 'Событие добавлено');
}
$('#dSave').addEventListener('click', commit); $('#dForm').addEventListener('submit', (e) => { e.preventDefault(); commit(); });
$('#dCancel').addEventListener('click', () => dlg.hide());
$('#dDel').addEventListener('click', () => { if (!editId || !confirm('Удалить запись?')) return; tasks = tasks.filter((x) => x.id !== editId); save(); dlg.hide(); cal.refetchEvents(); soon(); });
$('#cNew').addEventListener('click', () => openDlg(null));
$('#cIcs').addEventListener('click', () => {
  const d = read().filter((t) => t.due); if (!d.length) { toast('Нет записей с датой: в ICS нечего писать', true); return; }
  const tx = (s) => String(s).replace(/\\/g, '\\\\').replace(/;/g, '\;').replace(/,/g, '\\,').replace(/\n/g, '\\n'), stamp = new Date().toISOString().replace(/[-:]|\.\d+/g, '');
  const nx = (s) => { const x = new Date(s + 'T00:00:00'); x.setDate(x.getDate() + 1); return ymd(x).replace(/-/g, ''); };
  const L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//NOX HELION//calendar//RU'];
  d.forEach((t) => { const timed = t.kind === 'event' && t.time, dt = t.due.replace(/-/g, ''); L.push('BEGIN:VEVENT', 'UID:' + t.id + '@nox-helion', 'DTSTAMP:' + stamp, timed ? 'DTSTART:' + dt + 'T' + t.time.replace(':', '') + '00' : 'DTSTART;VALUE=DATE:' + dt, timed ? 'DTEND:' + dt + 'T' + t.time.replace(':', '') + '00' : 'DTEND;VALUE=DATE:' + nx(t.due), 'SUMMARY:' + tx(t.title), 'END:VEVENT'); });
  L.push('END:VCALENDAR'); download('nox-calendar-' + ymd(new Date()) + '.ics', L.join('\r\n'), 'text/calendar'); toast('ICS: записей ' + d.length);
});
if (!window.FullCalendar) { $('#cal').innerHTML = '<div class="empty">FullCalendar не загрузился (vendor/nox-extra/fullcalendar.global.min.js).</div>'; } else {
  cal = new window.FullCalendar.Calendar($('#cal'), { initialView: 'dayGridMonth', locale: 'ru', firstDay: 1, height: 'auto', fixedWeekCount: false, editable: true, dayMaxEvents: 3, eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
    headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,listMonth' }, buttonText: { today: 'Сегодня', month: 'Месяц', week: 'Неделя', list: 'Список' }, noEventsText: 'Нет событий и сроков в этом периоде',
    events: fetchEv, dateClick: (i) => openDlg(null, i.dateStr.slice(0, 10)), eventClick: (i) => openDlg(i.event.id),
    eventDrop: (i) => { const t = tasks.find((x) => x.id === i.event.id); if (t) { t.due = ymd(i.event.start); save(); soon(); toast('Дата перенесена на ' + t.due); } } });
  cal.render();
}
soon();
