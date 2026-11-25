
/* S3 слои: высоты шапки и дока в CSS-переменные */
(() => {
  const set = () => { const r = document.documentElement.style, d = document.getElementById('nxdock'), t = document.querySelector('.bar.tb,.tb'); if (d) r.setProperty('--ds-dock-h', Math.round(d.getBoundingClientRect().height) + 'px'); if (t) r.setProperty('--ds-head-h', Math.round(t.getBoundingClientRect().height) + 'px'); };
  addEventListener('resize', set); addEventListener('load', () => { set(); setTimeout(set, 1500); }); set();
  if (window.ResizeObserver) { const ro = new ResizeObserver(set); const w = setInterval(() => { const d = document.getElementById('nxdock'); if (d) { ro.observe(d); clearInterval(w); } }, 400); setTimeout(() => clearInterval(w), 8000); }
})();
