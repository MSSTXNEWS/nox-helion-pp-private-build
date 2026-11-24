import { Calendar } from '@fullcalendar/core';
import ru from '@fullcalendar/core/locales/ru';
import dayGrid from '@fullcalendar/daygrid';
import timeGrid from '@fullcalendar/timegrid';
import list from '@fullcalendar/list';
import interaction from '@fullcalendar/interaction';
const el = document.getElementById('cal'), st = document.getElementById('calSt');
const api = (m, u, b) => fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined }).then((r) => r.json());
const small = innerWidth < 700;
const cal = new Calendar(el, {
  plugins: [dayGrid, timeGrid, list, interaction], locale: ru, initialView: small ? 'listWeek' : 'dayGridMonth', height: small ? 'auto' : '68vh', nowIndicator: true, selectable: true, firstDay: 1,
  headerToolbar: small ? { left: 'prev,next', center: 'title', right: 'listWeek,dayGridMonth' } : { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,listWeek' },
  events: (info, ok, bad) => fetch('/cal/events').then((r) => r.json()).then((d) => { st.textContent = 'событий: ' + d.length; ok(d); }).catch((e) => { st.textContent = 'API календаря недоступен'; bad(e); }),
  select: async (i) => { const t = prompt('Название события'); if (!t) return; await api('POST', '/cal/events', { title: t, start: i.startStr, end: i.endStr, allDay: i.allDay }); cal.refetchEvents(); },
  eventClick: async (i) => { if (confirm('Удалить «' + i.event.title + '»?')) { await api('DELETE', '/cal/events/' + i.event.id); cal.refetchEvents(); } },
});
cal.render(); window.NOXCal = cal;
