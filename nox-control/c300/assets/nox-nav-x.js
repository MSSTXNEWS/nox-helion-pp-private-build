/* NOX · навигация+ (расширение поверх канона, канон не меняет):
   палитра Ctrl+K по всем разделам nav.json (группы, поиск, недавние), последние разделы,
   индикаторы датчиков ядра и чата (раскрываются по наведению), кнопка поиска на телефоне. */
(() => {
  if (window.__noxNavX) return; window.__noxNavX = 1;
  const here = location.pathname.split('/').pop() || 'index.html';
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = './nox-nav-x.css'; document.head.appendChild(css);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const nm = (t) => String(t || '').replace(/^NOX HELION\s*·\s*/i, '').trim();
  const RK = 'nox.nav.recent';
  const recent = () => { try { return JSON.parse(localStorage.getItem(RK) || '[]'); } catch (e) { return []; } };
  const remember = () => {
    if (!here) return;
    const r = recent().filter((x) => x !== here); r.unshift(here);
    try { localStorage.setItem(RK, JSON.stringify(r.slice(0, 8))); } catch (e) { /* хранилище недоступно: ничего страшного */ }
  };
  remember();

  /* ---------- данные разделов из nav.json ---------- */
  let items = [];
  const byFile = {};
  fetch('./nav.json', { cache: 'no-cache' }).then((r) => r.json()).then((d) => {
    items = (d.groups || []).flatMap((g) => (g.items || []).map((i) => ({ file: i.file, title: nm(i.title), group: nm(g.group) })));
    items.forEach((i) => { byFile[i.file] = i; });
    crumb();
  }).catch(() => {});

  /* ---------- нижний правый блок: хлебная крошка, датчики, поиск ---------- */
  const dock = document.createElement('div');
  dock.id = 'nxnavx'; dock.setAttribute('aria-label', 'Навигация и датчики');
  dock.innerHTML = '<span class="nxx-crumb" id="nxx-crumb"></span>'
    + '<span class="nxx-sens" id="nxx-sens" tabindex="0" aria-label="Датчики">'
    + '<i class="nxx-dot" data-k="core" title="ядро"></i><span class="nxx-lab" data-k="core">ядро</span>'
    + '<i class="nxx-dot" data-k="chat" title="чат"></i><span class="nxx-lab" data-k="chat">чат</span></span>'
    + '<button type="button" class="nxx-key" id="nxx-open" aria-label="Поиск по разделам (Ctrl+K)">⌘K</button>';
  const mount = () => document.body && document.body.appendChild(dock);
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);

  const crumb = () => {
    const el = document.getElementById('nxx-crumb'); if (!el) return;
    const i = byFile[here];
    el.innerHTML = i ? '<b>' + esc(i.group) + '</b> / ' + esc(i.title) : '';
  };

  /* ---------- датчики: ядро и чат, раз в 15 с ---------- */
  const setDot = (k, state, text) => {
    const d = dock.querySelector('.nxx-dot[data-k="' + k + '"]'), l = dock.querySelector('.nxx-lab[data-k="' + k + '"]');
    if (d) d.dataset.state = state;
    if (l) l.textContent = text;
  };
  const probe = async (k, url, label) => {
    const t0 = performance.now();
    try {
      const r = await fetch(url, { cache: 'no-store' });
      const ms = Math.round(performance.now() - t0);
      setDot(k, r.ok ? (ms > 1500 ? 'warn' : 'ok') : 'warn', label + ' ' + ms + ' мс');
    } catch (e) { setDot(k, 'bad', label + ' нет связи'); }
  };
  const sense = () => { probe('core', './glm/v1/nox/stats', 'ядро'); probe('chat', './api/chat/health', 'чат'); };
  sense(); setInterval(sense, 15000);

  /* ---------- палитра Ctrl+K ---------- */
  const pal = document.createElement('div');
  pal.id = 'nxpal'; pal.setAttribute('role', 'dialog'); pal.setAttribute('aria-modal', 'true'); pal.setAttribute('aria-label', 'Поиск по разделам');
  pal.innerHTML = '<div class="nxp-box"><input id="nxp-q" type="search" autocomplete="off" placeholder="Раздел, функция или команда…" aria-label="Поиск"><ul id="nxp-list" role="listbox"></ul><div class="nxp-foot">↑ ↓ выбор · Enter открыть · Esc закрыть</div></div>';
  const open = () => {
    if (!pal.isConnected) document.body.appendChild(pal);
    pal.classList.add('on'); const q = pal.querySelector('#nxp-q'); q.value = ''; render(''); q.focus();
  };
  const close = () => pal.classList.remove('on');
  const list = () => pal.querySelector('#nxp-list');
  let sel = 0, shown = [];
  const render = (term) => {
    const t = term.trim().toLowerCase();
    let arr;
    if (!t) {
      const rec = recent().map((f) => byFile[f]).filter(Boolean);
      const grp = byFile[here] ? items.filter((i) => i.group === byFile[here].group && i.file !== here) : [];
      arr = [].concat(rec.map((i) => ({ ...i, tag: 'недавние' })), grp.slice(0, 6).map((i) => ({ ...i, tag: 'из раздела «' + byFile[here].group + '»' })));
    } else {
      arr = items.filter((i) => (i.title + ' ' + i.group).toLowerCase().includes(t)).slice(0, 30).map((i) => ({ ...i, tag: i.group }));
    }
    if (!items.length && !t) arr = [{ file: 'index.html', title: 'Главная', tag: 'начало' }];
    shown = arr; sel = 0;
    list().innerHTML = arr.map((i, n) => '<li role="option" data-n="' + n + '" class="' + (n === 0 ? 'on' : '') + '"><a href="' + esc(i.file) + '"><span>' + esc(i.title) + '</span><small>' + esc(i.tag) + '</small></a></li>').join('')
      || '<li class="nxp-none">ничего не найдено</li>';
  };
  const paint = () => list().querySelectorAll('li[data-n]').forEach((li) => li.classList.toggle('on', +li.dataset.n === sel));
  pal.addEventListener('click', (e) => { if (e.target === pal) close(); });
  pal.querySelector('#nxp-q').addEventListener('input', (e) => render(e.target.value));
  pal.querySelector('#nxp-q').addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, shown.length - 1); paint(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); paint(); e.preventDefault(); }
    else if (e.key === 'Enter' && shown[sel]) { location.href = shown[sel].file; }
  });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); pal.classList.contains('on') ? close() : open(); }
    else if (e.key === 'Escape') close();
  });
  dock.querySelector('#nxx-open').addEventListener('click', open);
})();
