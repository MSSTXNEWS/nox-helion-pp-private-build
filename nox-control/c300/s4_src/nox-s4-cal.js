/* S4 · Календарь: раскладка Google Calendar на FullCalendar. Виды месяц/неделя/день/повестка, индикатор «сейчас», боковой мини-календарь и «Создать». Грузится сразу после fullcalendar.global и оборачивает Calendar. */
(function () {
  if (!window.FullCalendar || !FullCalendar.Calendar) return;
  const Base = FullCalendar.Calendar, reg = (window.__fc = window.__fc || {});
  FullCalendar.Calendar = class extends Base {
    constructor(el, o) {
      o = Object.assign({}, o);
      o.headerToolbar = Object.assign({ left: 'prev,next today', center: 'title' }, o.headerToolbar, { right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek' });
      if (o.nowIndicator == null) o.nowIndicator = true; if (o.firstDay == null) o.firstDay = 1; if (o.navLinks == null) o.navLinks = true; if (o.slotMinTime == null) o.slotMinTime = '06:00:00'; if (o.scrollTime == null) o.scrollTime = '08:00:00';
      o.buttonText = Object.assign({ today: 'Сегодня', month: 'Месяц', week: 'Неделя', day: 'День', list: 'Повестка' }, o.buttonText);
      super(el, o); if (el && el.id === 'cal') reg.cal = this;
    }
  };
  document.addEventListener('DOMContentLoaded', () => {
    const grid = document.querySelector('.grid'); if (!grid || !document.getElementById('cNew')) return;
    const side = document.createElement('aside'); side.className = 'card s4cs';
    side.innerHTML = '<button type="button" class="s4mk" id="s4new"><sl-icon library="tabler" name="plus"></sl-icon>Создать</button><div id="s4mini"></div><h3 class="mono s4sh">Календари</h3><label class="s4cl"><input type="checkbox" checked disabled><i></i>События и сроки задач</label><p class="muted" style="font-size:11.5px;margin:6px 0 0">Источник: задачи «Проектов» и /cal/events. Внешние календари не подключены.</p>';
    grid.classList.add('s4cg'); grid.prepend(side);
    side.querySelector('#s4new').onclick = () => document.getElementById('cNew').click();
    let t = 0; const iv = setInterval(() => {
      const main = reg.cal; if (!main || !main.el || !main.el.querySelector('.fc-view-harness') || ++t > 80) { if (t > 80) clearInterval(iv); return; } clearInterval(iv);
      const days = new Set(), mark = () => { days.clear(); main.getEvents().forEach((e) => e.start && days.add(e.start.toISOString().slice(0, 10))); mini.render(); };
      const mini = new Base(side.querySelector('#s4mini'), { initialView: 'dayGridMonth', locale: 'ru', firstDay: 1, height: 'auto', fixedWeekCount: false, headerToolbar: { left: 'title', right: 'prev,next' },
        dateClick: (i) => main.gotoDate(i.date), dayCellDidMount: (a) => { const d = a.date.getFullYear() + '-' + String(a.date.getMonth() + 1).padStart(2, '0') + '-' + String(a.date.getDate()).padStart(2, '0'); if (days.has(d)) a.el.classList.add('s4has'); } });
      mini.render(); setTimeout(() => main.updateSize(), 150); addEventListener('resize', () => main.updateSize()); main.on('eventsSet', mark); main.on('datesSet', (i) => { try { mini.gotoDate(main.getDate()); } catch (e) { /* */ } }); mark();
    }, 250);
  });
})();
