
/* S3 ds-v2: aria-label из title/иконки, авто-tooltip для иконок-кнопок, контраст >= 4.5:1 для приглушённого текста */
(() => {
  const ICON = { star: 'Избранное', bell: 'Уведомления', search: 'Поиск', notes: 'Заметки', x: 'Закрыть', close: 'Закрыть', plus: 'Добавить', minus: 'Убавить', settings: 'Настройки', 'message-circle': 'Чат', microphone: 'Голос', history: 'Недавние', command: 'Команды', trash: 'Удалить', download: 'Скачать', upload: 'Загрузить', refresh: 'Обновить', menu: 'Меню', 'chevron-down': 'Развернуть', 'chevron-up': 'Свернуть', play: 'Запустить', 'player-play': 'Запустить', 'player-pause': 'Пауза', copy: 'Копировать', edit: 'Править', pencil: 'Править', 'arrow-left': 'Назад' };
  const tip = document.createElement('div'); tip.id = 'ds-tip'; tip.setAttribute('role', 'tooltip');
  const label = (e) => e.getAttribute('aria-label') || e.getAttribute('data-ds-title') || e.getAttribute('title') || '';
  const nameFix = () => {
    document.querySelectorAll('button,a[href],[role=button],[role=tab]').forEach((e) => {
      if (e.closest('ninja-keys')) return; const txt = (e.textContent || '').trim();
      if (e.hasAttribute('title') && !e.hasAttribute('aria-label') && !txt) e.setAttribute('aria-label', e.getAttribute('title'));
      if (!txt && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby')) { const ic = e.querySelector('sl-icon[name]'); const n = ic && ic.getAttribute('name'); if (n) e.setAttribute('aria-label', ICON[n] || n.replace(/-/g, ' ')); }
      if (e.hasAttribute('title') && !txt) { e.setAttribute('data-ds-title', e.getAttribute('title')); e.removeAttribute('title'); }
    });
  };
  const lum = (r, g, b) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const contrast = () => {
    const bg = { r: 12, g: 9, b: 9 }, L0 = lum(12, 9, 9);
    document.querySelectorAll('#page *, .card *, .nxd *, #nxpult *').forEach((e) => {
      if (e.closest('ninja-keys,svg,canvas,.excalidraw,[data-ds-nofs]')) return; let own = false; for (let c = e.firstChild; c; c = c.nextSibling) if (c.nodeType === 3 && c.textContent.trim()) { own = true; break; } if (!own) return;
      const cs = getComputedStyle(e), c = parse(cs.color); if (!c) return; const bgc = parse(cs.backgroundColor); if (bgc && bgc.a > .3) return; /* свой светлый/цветной фон: не трогаем */
      const a = c.a, r = c.r * a + bg.r * (1 - a), g = c.g * a + bg.g * (1 - a), b = c.b * a + bg.b * (1 - a), L = lum(r, g, b);
      if (L < .12) return; /* тёмный текст на светлом: не трогаем */
      if ((L + .05) / (L0 + .05) < 4.5) e.style.setProperty('color', 'rgb(' + Math.min(255, Math.round(c.r * 1.0 + (255 - c.r) * .25)) + ',' + Math.min(255, Math.round(c.g + (255 - c.g) * .25)) + ',' + Math.min(255, Math.round(c.b + (255 - c.b) * .25)) + ')', 'important');
    });
  };
  let t1 = 0; const run = () => { t1 = 0; nameFix(); }; const sched = () => { if (!t1) t1 = setTimeout(run, 500); };
  const show = (e) => { const t = label(e.closest('[data-ds-title],[aria-label],[title]') || e); if (!t) return; const el = e.closest('button,a,[role=button],[role=tab]'); if (!el || (el.textContent || '').trim()) return; tip.textContent = t; document.body.appendChild(tip); const r = el.getBoundingClientRect(); tip.style.left = '0px'; tip.style.top = '0px'; const w = tip.offsetWidth, h = tip.offsetHeight; let x = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)), y = r.top - h - 8; if (y < 8) y = r.bottom + 8; tip.style.left = x + 'px'; tip.style.top = y + 'px'; tip.setAttribute('data-on', ''); };
  const hide = () => tip.removeAttribute('data-on');
  document.addEventListener('mouseover', (e) => show(e.target)); document.addEventListener('mouseout', hide); document.addEventListener('focusin', (e) => show(e.target)); document.addEventListener('focusout', hide); document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
  const go = () => { nameFix(); new MutationObserver(sched).observe(document.body, { childList: true, subtree: true }); setTimeout(() => { nameFix(); contrast(); }, 2800); setTimeout(contrast, 7000); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
  window.NOXds && (window.NOXds.contrast = contrast);
})();
