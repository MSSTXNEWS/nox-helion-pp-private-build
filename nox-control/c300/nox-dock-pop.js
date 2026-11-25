/* NOX · выпадающие списки нижней панели в стиле Dock/visionOS: стекло, иконка + название + 1 строка описания.
   Данные: nav.json (groups[].items[]: file,name,icon,desc). Избранное (★) и недавние — localStorage. На телефоне: долгое нажатие на ячейку или кнопка «ещё» открывает нижнюю шторку. */
(() => {
  if (window.__noxDockPop) return; window.__noxDockPop = 1;
  const here = location.pathname.split('/').pop() || 'index.html';
  const touch = matchMedia('(hover:none)').matches;
  const LS = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) || d; } catch (e) { return d; } };
  const SV = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* хранилище недоступно */ } };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const nm = (i) => i.name || String(i.title || '').replace(/^NOX HELION\s*·\s*/i, '').toLowerCase().replace(/^./, (c) => c.toUpperCase());
  let nav = null, pop = null, sheet = null, t1 = 0, owner = null;
  const load = () => nav || (nav = fetch('./nav.json', { cache: 'no-cache' }).then((r) => r.json()).catch(() => ({ groups: [] })));
  const icon = (n) => (n && customElements.get('sl-icon') ? '<sl-icon library="tabler" name="' + esc(n) + '"></sl-icon>' : '<span class="ndp-dot"></span>');
  const flat = (d) => (d.groups || []).flatMap((g) => g.items.map((i) => Object.assign({ group: g.group }, i)));
  const favs = () => LS('nox.nav.fav', []);
  const toggleFav = (f) => { const a = favs(), k = a.indexOf(f); if (k >= 0) a.splice(k, 1); else a.push(f); SV('nox.nav.fav', a.slice(0, 12)); };
  const row = (i) => '<div class="ndp-r' + (i.file === here ? ' act' : '') + '"><a role="menuitem" href="' + esc(i.file) + '"' + (i.file === here ? ' aria-current="page"' : '') + '>'
    + '<span class="ndp-i">' + icon(i.icon) + '</span><span class="ndp-t"><b>' + esc(nm(i)) + '</b><small>' + esc(i.desc || '') + '</small></span></a>'
    + '<button type="button" class="ndp-s' + (favs().includes(i.file) ? ' on' : '') + '" data-fav="' + esc(i.file) + '" aria-label="В избранное" title="В избранное">★</button></div>';
  const extra = (d, g) => {
    const all = flat(d), by = (f) => all.find((x) => x.file === f);
    const fv = favs().map(by).filter(Boolean), rc = LS('nox.nav.recent', []).filter((f) => f !== here).map(by).filter(Boolean).slice(0, 3);
    let h = '';
    if (fv.length) h += '<div class="ndp-h2">Избранное</div><div class="ndp-chips">' + fv.map((i) => '<a href="' + esc(i.file) + '">' + esc(nm(i)) + '</a>').join('') + '</div>';
    if (rc.length) h += '<div class="ndp-h2">Недавние</div><div class="ndp-chips">' + rc.map((i) => '<a href="' + esc(i.file) + '">' + esc(nm(i)) + '</a>').join('') + '</div>';
    return h;
  };
  const body = (d, g) => '<div class="ndp-h">' + esc(g.group) + '</div>' + g.items.map(row).join('') + extra(d, g);
  const hide = () => { clearTimeout(t1); if (pop) pop.classList.remove('on'); owner = null; };
  const later = () => { clearTimeout(t1); t1 = setTimeout(hide, 260); };
  const bindFav = (root, d, g, rerender) => root.querySelectorAll('[data-fav]').forEach((b) => b.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); toggleFav(b.dataset.fav); rerender(); }));
  const ensure = () => {
    if (pop) return pop;
    pop = document.createElement('div'); pop.className = 'ndp'; pop.setAttribute('role', 'menu');
    pop.addEventListener('mouseenter', () => clearTimeout(t1)); pop.addEventListener('mouseleave', later);
    document.body.appendChild(pop); return pop;
  };
  const place = (a, p) => { const r = a.getBoundingClientRect(), w = p.offsetWidth, hg = p.offsetHeight; p.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px'; p.style.top = Math.max(8, r.top - hg - 12) + 'px'; };
  const groupOf = (d, file) => (d.groups || []).find((x) => x.items.some((i) => i.file === file));
  async function show(a) {
    const file = (a.getAttribute('href') || '').split('/').pop(); if (!file) return;
    const d = await load(), g = groupOf(d, file); if (!g) return;
    const p = ensure(); owner = a; clearTimeout(t1);
    const render = () => { p.innerHTML = body(d, g); bindFav(p, d, g, render); place(a, p); };
    render(); p.classList.add('on'); place(a, p);
  }
  async function openSheet(file) {
    const d = await load(), g = groupOf(d, file) || (d.groups || [])[0]; if (!g) return;
    if (!sheet) { sheet = document.createElement('div'); sheet.className = 'ndp-sheet'; sheet.innerHTML = '<div class="ndp-bg"></div><div class="ndp-pn" role="dialog" aria-label="Раздел"></div>'; document.body.appendChild(sheet); sheet.querySelector('.ndp-bg').addEventListener('click', () => sheet.classList.remove('on')); }
    const pn = sheet.querySelector('.ndp-pn');
    const render = () => { pn.innerHTML = '<div class="ndp-grab"></div>' + body(d, g); bindFav(pn, d, g, render); };
    render(); requestAnimationFrame(() => sheet.classList.add('on'));
  }
  if (!touch) {
    document.addEventListener('mouseover', (e) => { const a = e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]'); if (a && a !== owner) show(a); else if (a) clearTimeout(t1); });
    document.addEventListener('mouseout', (e) => { if (e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]')) later(); });
    document.addEventListener('focusin', (e) => { const a = e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]'); if (a) show(a); });
  } else {
    let tm = 0, fired = 0;
    document.addEventListener('touchstart', (e) => { const a = e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]'); if (!a) return; fired = 0; tm = setTimeout(() => { fired = 1; openSheet((a.getAttribute('href') || '').split('/').pop()); }, 450); }, { passive: true });
    ['touchend', 'touchmove', 'touchcancel'].forEach((t) => document.addEventListener(t, () => clearTimeout(tm), { passive: true }));
    document.addEventListener('click', (e) => { if (fired && e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]')) { e.preventDefault(); fired = 0; } }, true);
  }
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { hide(); if (sheet) sheet.classList.remove('on'); } });
  window.NOXNav = { openSheet: (f) => openSheet(f || here), favs, toggleFav };
  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = './nox-dock-pop.css'; document.head.appendChild(l);
})();
