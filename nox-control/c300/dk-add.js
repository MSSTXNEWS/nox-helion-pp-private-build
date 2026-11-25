
/* S3 док/шрифты: STOP остаётся доступным; общий пол 12 px для текста на страницах меню */
(() => {
  const keep = () => { const d = document.getElementById('nxdTools'); if (!d) return; [...d.querySelectorAll('button')].forEach((b) => { if (/^\s*stop\s*$/i.test(b.textContent)) b.classList.add('ds-keep'); }); };
  const SKIP = 'ninja-keys,svg,canvas,.excalidraw,[data-ds-nofs],script,style';
  let busy = 0, scans = 0;
  const fix = () => { busy = 0; scans++; const els = document.body ? document.body.getElementsByTagName('*') : []; for (let i = 0; i < els.length; i++) { const e = els[i]; if (!e.firstChild || e.closest(SKIP)) continue; let has = false; for (let c = e.firstChild; c; c = c.nextSibling) if (c.nodeType === 3 && c.textContent.trim()) { has = true; break; } if (!has) continue; const fs = parseFloat(getComputedStyle(e).fontSize); if (fs > 0 && fs < 12) e.style.setProperty('font-size', '12px', 'important'); } keep(); };
  const sched = () => { if (busy) return; busy = setTimeout(fix, 600); };
  const go = () => { keep(); sched(); new MutationObserver(sched).observe(document.body, { childList: true, subtree: true }); setTimeout(fix, 2500); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
})();
