
/* S3 ds2: безопасный requestIdleCallback, skeleton для настроек до появления панелей */
(() => {
  window.NOXds.idle = (fn, ms) => { if (window.requestIdleCallback) return window.requestIdleCallback(fn, { timeout: ms || 500 }); return setTimeout(fn, 1); };
  if (!/\/settings\.html$/.test(location.pathname)) return;
  const mk = () => { const w = document.querySelector('.wrap'); if (!w || document.getElementById('dsSetSkel') || document.querySelector('.nxm-side')) return; const d = document.createElement('div'); d.id = 'dsSetSkel'; d.className = 'ds-skel-set'; d.setAttribute('aria-busy', 'true'); d.setAttribute('aria-label', 'Загрузка настроек'); d.innerHTML = '<div class="ds-skel ds-skel-card" style="width:240px;height:320px"></div><div style="flex:1"><div class="ds-skel ds-skel-line" style="width:40%"></div><div class="ds-skel ds-skel-card"></div><div class="ds-skel ds-skel-card"></div></div>'; w.appendChild(d); };
  const mo = new MutationObserver(() => { if (document.querySelector('.nxm-side')) { const s = document.getElementById('dsSetSkel'); s && s.remove(); mo.disconnect(); } else mk(); });
  mo.observe(document.documentElement, { childList: true, subtree: true }); mk(); setTimeout(() => { mo.disconnect(); const s = document.getElementById('dsSetSkel'); s && s.remove(); }, 12000);
})();
