/* NOX · живые обои: единое состояние ИИ (нагрузка GPU из live.json, «думает» из NOXstate) питает CSS-переменные --nox-load и --nox-think; фон миров дышит от них.
   Событие window 'nox:ai-state' получают сцены (three.js) для своих uniform. */
(() => {
  if (window.NOXlive) return;
  const store = { load: 0, vram: 0, think: 0, round: 0 }, root = document.documentElement;
  const push = () => { root.style.setProperty('--nox-load', store.load.toFixed(2)); root.style.setProperty('--nox-think', store.think); window.dispatchEvent(new CustomEvent('nox:ai-state', { detail: Object.assign({}, store) })); };
  const pull = () => fetch('./data/live.json', { cache: 'no-store' }).then((r) => r.json()).then((j) => { const g = j.gpu || {}; store.load = Math.min(1, (g.gpu_util_pct || 0) / 100); store.vram = (g.vram_pct || 0) / 100; push(); }).catch(() => {});
  new MutationObserver(() => { store.think = window.NOXstate && window.NOXstate.get() === 'thinking' ? 1 : 0; push(); }).observe(root, { attributes: true, attributeFilter: ['data-nox-state'] });
  pull(); setInterval(pull, 8000);
  const st = document.createElement('style');
  st.textContent = 'html[data-nox-world]::after{opacity:calc(.12 + var(--nox-load,0) * .26 + var(--nox-think,0) * .12);transition:opacity 1.2s ease}@media(prefers-reduced-motion:no-preference){html[data-nox-world]::after{animation:nxlive calc(9s - var(--nox-load,0) * 5s) ease-in-out infinite}}@keyframes nxlive{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}';
  document.head.appendChild(st);
  window.NOXlive = { store };
})();
