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
    /* размер и место берём у канонного малого солнца в центре шапки; если его не нашли, ставим по умолчанию */
    const cx = innerWidth / 2;
    let box = null;
    try {
      for (const el of document.elementsFromPoint(cx, 40)) {
        const r = el.getBoundingClientRect();
        if (r.width >= 28 && r.width <= 140 && Math.abs(r.left + r.width / 2 - cx) < 40 && r.top < 90) { box = r; break; }
      }
    } catch (e) { /* elementsFromPoint недоступен */ }
    const d = box ? Math.round(Math.max(40, Math.min(box.width, 96))) : 52;
    const top = box ? Math.round(box.top + box.height / 2 - d / 2) : 10;
    sun.style.width = d + 'px'; sun.style.height = d + 'px';
    sun.style.top = Math.max(4, top) + 'px'; sun.style.left = Math.round(cx - d / 2) + 'px';
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
