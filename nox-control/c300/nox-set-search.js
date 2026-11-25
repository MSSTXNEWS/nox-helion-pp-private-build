/* NOX · поиск по настройкам (как в macOS): поле сверху боковой панели, фильтр по всем разделам, клавиша «/» */
(() => {
  if (window.__nxSetSearch) return; window.__nxSetSearch = 1;
  const go = () => {
    const side = document.querySelector('.nxm-side'); if (!side || side.querySelector('.nxm-search')) return !!side;
    const inp = document.createElement('sl-input'); inp.className = 'nxm-search'; inp.placeholder = 'Поиск'; inp.clearable = true; inp.size = 'large'; inp.setAttribute('aria-label', 'Поиск по настройкам');
    inp.innerHTML = '<sl-icon slot="prefix" library="tabler" name="search"></sl-icon>';
    side.insertBefore(inp, side.firstChild);
    const secs = () => [...document.querySelectorAll('section.setg')];
    let note = document.createElement('p'); note.className = 'note nxm-empty'; note.hidden = true; note.textContent = 'Ничего не найдено.';
    const pl = secs()[0] && secs()[0].parentElement; if (pl) pl.appendChild(note);
    const apply = () => {
      const q = String(inp.value || '').trim().toLowerCase();
      if (!q) { note.hidden = true; const sel = side.querySelector('[role=tab][aria-selected=true]') || side.querySelector('[role=tab]'); sel && sel.click(); return; }
      let n = 0; secs().forEach((s) => { const hit = (s.textContent || '').toLowerCase().includes(q); s.classList.toggle('nxt-off', !hit); if (hit) n++; });
      note.hidden = n > 0;
    };
    inp.addEventListener('sl-input', apply);
    document.addEventListener('keydown', (e) => { if (e.key === '/' && !/INPUT|TEXTAREA|SL-/.test((e.target && e.target.tagName) || '') ) { e.preventDefault(); inp.focus(); } });
    return true;
  };
  const t = setInterval(() => { if (go()) clearInterval(t); }, 300); setTimeout(() => clearInterval(t), 20000);
})();
