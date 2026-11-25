/* NOX · палитра команд Ctrl+K на ninja-keys (MIT). Страницы из nav.json + действия NOX + сервисы. */
import './vendor/ninja-keys/ninja-keys.js';
const nm = (t) => String(t || '').replace(/^NOX HELION\s*·\s*/i, '').toLowerCase().replace(/^./, (c) => c.toUpperCase());
const toast = (msg, bad) => { const d = document.createElement('div'); d.textContent = msg; d.style.cssText = 'position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:2147483600;padding:10px 18px;border-radius:12px;font:300 12px/1.2 inherit;letter-spacing:.14em;text-transform:uppercase;color:#f3ebe4;background:rgba(14,12,12,.82);border:1px solid ' + (bad ? 'rgba(200,70,50,.6)' : 'rgba(255,225,200,.18)') + ';backdrop-filter:blur(18px)'; document.body.appendChild(d); setTimeout(() => d.remove(), 3200); };
const jget = (u, o) => fetch(u, o).then(async (r) => { const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch (e) {} return { ok: r.ok, status: r.status, j, t }; });
(async () => {
  const nav = await jget('./nav.json', { cache: 'no-cache' }).then((r) => r.j || { groups: [] }).catch(() => ({ groups: [] }));
  const data = [];
  for (const g of nav.groups) for (const i of g.items) data.push({ id: 'p:' + i.file, title: nm(i.title), section: 'Страницы · ' + g.group, keywords: i.file + ' ' + g.group, handler: () => { location.href = i.file; } });
  data.push(
    { id: 'a:stop', title: 'Остановить ответ NOX (STOP)', section: 'Действия NOX', keywords: 'stop стоп', handler: () => { if (window.NOXDock && NOXDock.stop) { NOXDock.stop(); toast('STOP отправлен'); } else { const b = document.getElementById('dkStop'); b ? b.click() : toast('STOP недоступен на этой странице', 1); } } },
    { id: 'a:health', title: 'Состояние шлюза и ядра', section: 'Действия NOX', keywords: 'health статус', handler: async () => { const r = await jget('/api/chat/health').catch(() => null); toast(r && r.ok ? 'Шлюз: ответ получен' : 'Шлюз недоступен', !(r && r.ok)); } },
    { id: 'a:chat', title: 'Задать вопрос NOX (Резонанс)', section: 'Действия NOX', keywords: 'чат диалог вопрос', handler: () => { location.href = 'chat.html'; } },
    { id: 'a:copy', title: 'Скопировать ссылку на страницу', section: 'Действия NOX', handler: () => { navigator.clipboard && navigator.clipboard.writeText(location.href).then(() => toast('Ссылка скопирована')); } },
    { id: 'a:reload', title: 'Перезагрузить страницу', section: 'Действия NOX', handler: () => location.reload() },
    { id: 'a:ntfy', title: 'Уведомление ntfy: отправить тест', section: 'Действия NOX', keywords: 'ntfy push уведомление', handler: async () => { const r = await fetch('/svc/ntfy/nox-helion', { method: 'POST', body: 'Проверка канала уведомлений NOX HELION', headers: { Title: 'NOX HELION' } }).catch(() => null); toast(r && r.ok ? 'ntfy: отправлено' : 'ntfy недоступен', !(r && r.ok)); } },
  );
  const st = await jget('/svc/_status').then((r) => r.j || {}).catch(() => ({}));
  for (const [k, v] of Object.entries(st.services || {})) if (v.ui !== false) data.push({ id: 's:' + k, title: (v.title || k) + (v.up ? '' : ' · не запущен'), section: 'Сервисы', keywords: k, handler: () => { v.up ? window.open('/svc/' + k + '/', '_blank') : toast((v.title || k) + ': сервис не запущен', 1); } });
  const el = document.createElement('ninja-keys');
  el.setAttribute('placeholder', 'Поиск страниц и действий NOX…'); el.openHotkey = 'ctrl+alt+shift+f12'; el.noAutoLoadMdIcons = true; el.data = data; el.footerHtml = '<span style="opacity:.7;letter-spacing:.12em;font-size:10px">ENTER · ВЫБРАТЬ &nbsp; ↑↓ · ПЕРЕМЕЩЕНИЕ &nbsp; ESC · ЗАКРЫТЬ</span>';
  el.style.cssText = '--ninja-z-index:9800;--ninja-width:620px;--ninja-accent-color:#c0392b;--ninja-font-family:inherit;--ninja-text-color:#efe6df;--ninja-secondary-text-color:#a89c93;--ninja-modal-background:rgba(16,13,13,.78);--ninja-modal-shadow:0 24px 70px rgba(0,0,0,.65);--ninja-overflow-background:rgba(2,3,10,.55);--ninja-secondary-background-color:rgba(255,235,220,.06);--ninja-selected-background:rgba(176,44,32,.38);--ninja-actions-height:360px;--ninja-icon-size:1.2em;--ninja-key-border-radius:6px;--ninja-footer-background:rgba(255,235,220,.04)';
  document.body.appendChild(el);
  /* палитра открывается только по Ctrl+K или кнопке: при загрузке без действия пользователя гасим её */
  let touched = 0; ['keydown', 'pointerdown', 'touchstart'].forEach((t) => addEventListener(t, () => { touched = 1; }, true));
  const quiet = () => { if (!touched) { try { if (typeof el.close === 'function') el.close(); } catch (e) { /* нет close: оставляем как есть */ } } };
  setTimeout(quiet, 700); setTimeout(quiet, 2000);
  let tm = 0, last = '';
  el.addEventListener('change', (e) => { const q = ((e.detail && e.detail.search) || '').trim(); if (q === last) return; last = q; clearTimeout(tm);
    if (q.length < 2) { el.data = data; return; }
    tm = setTimeout(async () => { const r = await jget('/search?q=' + encodeURIComponent(q)).catch(() => null); if (q !== last) return;
      const hits = (r && r.j && r.j.hits) || [];
      el.data = data.concat(hits.map((h, i) => ({ id: 'q:' + i, title: h.title + (h.text && h.kind !== 'страница' ? ' · ' + String(h.text).slice(0, 60) : ''), section: 'Поиск · ' + h.kind, keywords: q + ' ' + h.title, handler: () => { location.href = h.url; } })));
    }, 220); });
  const open = (e) => { e.preventDefault(); e.stopImmediatePropagation(); el.open(); };
  addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'k') open(e); }, true);
  for (const id of ['dkK', 'tbSearch']) document.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('#' + id)) open(e); }, true);
  window.NOXNinja = { open: () => el.open(), el };
})();
