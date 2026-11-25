
/* S3 pf: лупа сообщает состояние через aria-expanded (видно в DOM), палитра: html.nox-palette-open */
(() => {
  const btn = () => document.getElementById('tbSearch'), nk = () => document.querySelector('ninja-keys');
  const sync = () => { const b = btn(), n = nk(); if (!b) return false; const o = !!(n && n.visible); b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', String(o)); document.documentElement.classList.toggle('nox-palette-open', o); return o; };
  let tm = 0; const watch = () => { clearInterval(tm); let k = 0; tm = setInterval(() => { const o = sync(); if (!o && ++k > 2) clearInterval(tm); }, 250); };
  document.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('#tbSearch')) { setTimeout(sync, 120); watch(); } }, true);
  document.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { setTimeout(sync, 150); watch(); } }, true);
  setTimeout(sync, 1500);
})();
