/* NOX · выпадающие списки подразделов нижней панели (данные: nav.json groups). Отдельный модуль, канон не затрагивает. */
(() => {
  if (window.__noxDockPop) return; window.__noxDockPop = 1;
  if (matchMedia('(hover:none)').matches && innerWidth < 900) return;
  const here = location.pathname.split('/').pop() || 'index.html';
  const nm = (t) => String(t || '').replace(/^NOX HELION\s*·\s*/i, '').toLowerCase().replace(/^./, (c) => c.toUpperCase());
  let nav = null, pop = null, t1 = 0, owner = null;
  const load = () => nav || (nav = fetch('./nav.json', { cache: 'no-cache' }).then((r) => r.json()).catch(() => ({ groups: [] })));
  const hide = () => { clearTimeout(t1); if (pop) pop.classList.remove('on'); owner = null; };
  const later = () => { clearTimeout(t1); t1 = setTimeout(hide, 260); };
  const ensure = () => {
    if (pop) return pop;
    pop = document.createElement('div'); pop.className = 'ndp'; pop.setAttribute('role', 'menu');
    pop.addEventListener('mouseenter', () => clearTimeout(t1)); pop.addEventListener('mouseleave', later);
    document.body.appendChild(pop); return pop;
  };
  async function show(a) {
    const file = (a.getAttribute('href') || '').split('/').pop(); if (!file) return;
    const d = await load(); const g = (d.groups || []).find((x) => x.items.some((i) => i.file === file)); if (!g) return;
    const p = ensure(); owner = a; clearTimeout(t1);
    p.innerHTML = '<div class="ndp-h">' + g.group + '</div>' + g.items.map((i) => '<a role="menuitem" href="' + i.file + '"' + (i.file === here ? ' class="act" aria-current="page"' : '') + '><span>' + nm(i.title) + '</span></a>').join('');
    p.classList.add('on');
    const r = a.getBoundingClientRect(), w = p.offsetWidth, hgt = p.offsetHeight;
    p.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px';
    p.style.top = Math.max(8, r.top - hgt - 10) + 'px';
  }
  document.addEventListener('mouseover', (e) => { const a = e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]'); if (a && a !== owner) show(a); else if (a) clearTimeout(t1); });
  document.addEventListener('mouseout', (e) => { if (e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]')) later(); });
  document.addEventListener('focusin', (e) => { const a = e.target.closest && e.target.closest('#nxdock .nxd-cells a[href]'); if (a) show(a); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = './nox-dock-pop.css'; document.head.appendChild(l);
})();
