/* NOX · малое чёрное солнце в центре шапки и в доке: единый лёгкий BlackSun (nox-blacksun.js, canvas 2D).
   Клик по солнцу шапки открывает пульт (#nxpult). */
(() => {
  if (window.__noxSunX) return; window.__noxSunX = 1;
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = './nox-sun-x.css'; document.head.appendChild(css);
  const lib = (cb) => { if (window.NoxBS) return cb(); const s = document.createElement('script'); s.src = './nox-blacksun.js'; s.onload = cb; document.head.appendChild(s); };
  const sun = document.createElement('button');
  sun.type = 'button'; sun.id = 'nxsun'; sun.className = 'nxsun-x';
  sun.setAttribute('aria-label', 'Пульт NOX'); sun.title = 'Пульт NOX';
  sun.innerHTML = '<span class="nxsun-core"></span>';
  const place = () => {
    const el = document.querySelector('.tb-sun'); let r = el && el.getBoundingClientRect();
    if (!r || r.width < 8) r = { left: innerWidth / 2 - 26, top: 8, width: 52, height: 52 };
    const d = Math.round(Math.max(34, Math.min(r.width, r.height, 72)));
    sun.style.width = d + 'px'; sun.style.height = d + 'px';
    sun.style.top = Math.round(r.top + r.height / 2 - d / 2) + 'px'; sun.style.left = Math.round(r.left + r.width / 2 - d / 2) + 'px';
  };
  const mount = () => { if (!document.body) return; document.body.appendChild(sun); place(); lib(() => { window.NoxBS.mount(sun.firstChild, { size: 42 }); dock(); }); };
  const dock = () => { let n = 0; const t = setInterval(() => { const d = document.getElementById('dkSun'); if (d || ++n > 40) { clearInterval(t); if (d && !d.dataset.bs) { d.dataset.bs = 1; const disc = d.querySelector('.sun-disc'); if (disc) disc.style.display = 'none'; d.style.position = 'relative'; window.NoxBS.mount(d, { size: 34 }); } } }, 400); };
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
  addEventListener('resize', place);
  setTimeout(place, 800);
  sun.addEventListener('click', () => { const tog = document.querySelector('#nxpult .nxpu-tog'); if (tog) tog.click(); });
})();
