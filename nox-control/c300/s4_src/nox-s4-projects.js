/* S4 · Проекты: виды «Список» (Linear: группы по статусу и циклам) и «Гант» (Frappe Gantt) поверх задач страницы (localStorage nox.tasks.v1). Данные только реальные. */
(function () {
  const $ = (s) => document.querySelector(s), esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const seg = $('#vBoard') && $('#vBoard').parentNode; if (!seg) return;
  const COLS = [['queue', 'Очередь'], ['doing', 'В работе'], ['review', 'Проверка'], ['done', 'Готово']];
  const tasks = () => { try { return (JSON.parse(localStorage.getItem('nox.tasks.v1') || '{}').tasks || []).filter((t) => t.kind !== 'event'); } catch (e) { return []; } };
  const mk = (id, ic, tx) => { const b = document.createElement('button'); b.type = 'button'; b.id = id; b.setAttribute('aria-pressed', 'false'); b.innerHTML = '<sl-icon library="tabler" name="' + ic + '"></sl-icon>' + tx; seg.insertBefore(b, $('#vCal')); return b; };
  const bL = mk('vList', 'list', 'Список'), bG = mk('vGantt', 'timeline', 'Гант');
  const box = (id) => { const s = document.createElement('section'); s.className = 'card s4p'; s.id = id; s.hidden = true; $('#vCalBox').after(s); return s; };
  const L = box('s4List'), G = box('s4Gantt');
  const all = ['#vBoardBox', '#vCalBox', '#vSumBox'].map((q) => $(q)), btns = ['#vBoard', '#vCal'].map((q) => $(q));
  let gantt = null;
  function show(w) {
    L.hidden = w !== 'l'; G.hidden = w !== 'g';
    if (w) { $('#vBoardBox').hidden = true; $('#vCalBox').hidden = true; btns.forEach((b) => b.setAttribute('aria-pressed', 'false')); }
    bL.setAttribute('aria-pressed', w === 'l'); bG.setAttribute('aria-pressed', w === 'g');
    if (w === 'l') list(); if (w === 'g') gant();
  }
  btns.forEach((b) => b.addEventListener('click', () => { L.hidden = G.hidden = true; bL.setAttribute('aria-pressed', 'false'); bG.setAttribute('aria-pressed', 'false'); }, true));
  bL.onclick = () => show('l'); bG.onclick = () => show('g');
  const iso = (d) => d.toISOString().slice(0, 10), mon = (d) => { const x = new Date(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); x.setHours(12, 0, 0, 0); return x; };
  function cycle(t) {
    if (!t.due) return 'Без срока'; const m0 = mon(new Date()), m = mon(new Date(t.due + 'T12:00:00')), w = Math.round((m - m0) / 6048e5);
    return w < 0 ? 'Просрочено' : w <= 1 ? 'Текущий цикл (2 недели)' : w <= 3 ? 'Следующий цикл' : 'Позже';
  }
  function list() {
    const T = tasks(); if (!T.length) { L.innerHTML = '<h2>Список</h2><p class="muted">Задач пока нет: добавьте первую в форме выше.</p>'; return; }
    const by = (f, order) => order.map((k) => [k, T.filter((t) => f(t) === k)]).filter((x) => x[1].length);
    const row = (t) => '<div class="s4r"><span class="s4s s-' + t.col + '"></span><span class="s4t">' + esc(t.title) + '</span><span class="tag">' + esc(t.project || 'Общий') + '</span>' + (t.owner ? '<span class="tag on">' + esc(t.owner) + '</span>' : '') + '<span class="mono muted">' + esc(t.due || '—') + '</span></div>';
    const grp = (h, a) => '<div class="s4g"><h3>' + esc(h) + ' <small class="mono">' + a.length + '</small></h3>' + a.map(row).join('') + '</div>';
    L.innerHTML = '<h2>Список <span class="r mono">' + T.length + ' задач</span></h2><div class="s4cols"><div><h2 class="s4h">По статусу</h2>'
      + by((t) => t.col, COLS.map((c) => c[0])).map(([k, a]) => grp(COLS.find((c) => c[0] === k)[1], a)).join('') + '</div><div><h2 class="s4h">Циклы</h2>'
      + by(cycle, ['Просрочено', 'Текущий цикл (2 недели)', 'Следующий цикл', 'Позже', 'Без срока']).map(([k, a]) => grp(k, a)).join('') + '</div></div>';
  }
  function gant() {
    const T = tasks().filter((t) => t.due), no = tasks().length - T.length;
    if (!T.length) { G.innerHTML = '<h2>Гант</h2><p class="muted">Нет задач со сроком: Гант строится по сроку. Задайте срок у задачи.</p>'; return; }
    G.innerHTML = '<h2>Гант <span class="r mono">' + T.length + ' со сроком' + (no ? ' · ' + no + ' без срока скрыто' : '') + '</span></h2><div class="s4vm"><button type="button" data-m="Day">День</button><button type="button" data-m="Week">Неделя</button><button type="button" data-m="Month">Месяц</button></div><div id="s4gt" class="s4gt"><svg id="s4gs"></svg></div>';
    const rows = T.map((t) => { const e = new Date(t.due + 'T12:00:00'), s = new Date(Math.min(t.created || e - 6048e5, e - 864e5)); return { id: String(t.id), name: t.title, start: iso(s), end: iso(e), progress: t.col === 'done' ? 100 : t.col === 'review' ? 75 : t.col === 'doing' ? 40 : 0 }; });
    try {
      const Gt = window.Gantt && (window.Gantt.default || window.Gantt);
      gantt = new Gt('#s4gs', rows, { view_mode: 'Week', language: 'ru' });
      G.querySelectorAll('.s4vm button').forEach((b) => (b.onclick = () => gantt.change_view_mode(b.dataset.m)));
    } catch (e) { G.insertAdjacentHTML('beforeend', '<p class="muted">Гант не загрузился: ' + esc(e.message) + '</p>'); }
  }
  addEventListener('storage', () => { if (!L.hidden) list(); if (!G.hidden) gant(); });
})();
