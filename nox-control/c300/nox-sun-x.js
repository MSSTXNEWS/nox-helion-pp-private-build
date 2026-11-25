/* NOX · малое чёрное солнце в центре шапки (расширение, канон не меняет).
   Лёгкий элемент поверх канонного малого солнца: чёрный диск, тонкий красный ободок, мягкая корона.
   Клик открывает пульт (#nxpult). */
(() => {
  if (window.__noxSunX) return; window.__noxSunX = 1;
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = './nox-sun-x.css'; document.head.appendChild(css);
  const sun = document.createElement('button');
  sun.type = 'button'; sun.id = 'nxsun'; sun.className = 'nxsun-x';
  sun.setAttribute('aria-label', 'Пульт NOX'); sun.title = 'Пульт NOX';
  sun.innerHTML = '<span class="nxsun-core"></span>';
  const place = () => {
    /* размер и место берём у малого солнца шапки (.tb-sun), иначе по центру сверху */
    const el = document.querySelector('.tb-sun'); let r = el && el.getBoundingClientRect();
    if (!r || r.width < 8) r = { left: innerWidth / 2 - 26, top: 8, width: 52, height: 52 };
    const d = Math.round(Math.max(34, Math.min(r.width, r.height, 72)));
    sun.style.width = d + 'px'; sun.style.height = d + 'px';
    sun.style.top = Math.round(r.top + r.height / 2 - d / 2) + 'px'; sun.style.left = Math.round(r.left + r.width / 2 - d / 2) + 'px';
  };
  const mount = () => { if (document.body) { document.body.appendChild(sun); place(); } };
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
  addEventListener('resize', place);
  setTimeout(place, 800);
  sun.addEventListener('click', () => {
    const tog = document.querySelector('#nxpult .nxpu-tog');
    if (tog) tog.click();
  });
})();
