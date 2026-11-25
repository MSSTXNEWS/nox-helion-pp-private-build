/* S4 · подтверждение необратимых кнопок в стекле. Система: «Очистить» графики. */
(function () {
  const ask = (txt) => new Promise((ok) => { const o = document.createElement('div'); o.className = 's4dlg'; o.innerHTML = '<div><div>' + txt + '</div><button type="button" data-y>Да, очистить</button><button type="button" data-n>Отмена</button></div>'; const done = (v) => { o.remove(); ok(v); }; o.querySelector('[data-y]').onclick = () => done(true); o.querySelector('[data-n]').onclick = () => done(false); o.addEventListener('click', (e) => { if (e.target === o) done(false); }); document.body.appendChild(o); });
  const b = document.getElementById('sClear'); if (!b) return;
  b.addEventListener('click', async (e) => {
    if (b.dataset.ok) { delete b.dataset.ok; return; }
    e.stopImmediatePropagation(); e.preventDefault();
    if (await ask('Очистить накопленные графики этой вкладки? Историю нельзя вернуть.')) { b.dataset.ok = '1'; b.click(); }
  }, true);
})();
/* growth: три карточки «служба недоступна» -> одно состояние; слайдеры ECharts в стекле */
(function () {
  if (document.body.dataset.page !== 'growth') return;
  const fix = () => {
    const secs = [...document.querySelectorAll('main section, main .card')].filter((s) => !s.querySelector('section') && /СЛУЖБА НЕДОСТУПНА/i.test(s.textContent) && !s.dataset.s4);
    if (secs.length > 1) {
      secs.slice(1).forEach((s) => { s.style.display = 'none'; s.dataset.s4 = 'h'; });
      const s = secs[0]; s.dataset.s4 = '1'; s.innerHTML = '<h2 style="margin:0 0 6px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;opacity:.7">Служба роста · :8100</h2><p style="margin:0;font-size:13px">Служба не запущена: порт 8100 не отвечает. Метрики недели и итоги появятся, когда её подключат.</p>';
    }
    if (window.echarts) document.querySelectorAll('main div').forEach((d) => { const c = d.__zr && window.echarts.getInstanceByDom(d); if (c && !d.dataset.s4z) { d.dataset.s4z = 1; try { c.setOption({ dataZoom: [{}, { backgroundColor: 'rgba(255,235,220,.04)', borderColor: 'rgba(255,225,200,.14)', fillerColor: 'rgba(224,101,74,.2)', handleStyle: { color: '#e0654a', borderColor: '#e0654a' }, dataBackground: { lineStyle: { color: 'rgba(255,130,80,.35)' }, areaStyle: { color: 'rgba(255,130,80,.1)' } }, selectedDataBackground: { lineStyle: { color: '#e0654a' }, areaStyle: { color: 'rgba(224,101,74,.25)' } }, textStyle: { color: '#9a8f88' } }] }); } catch (e) { /* */ } } });
  };
  new MutationObserver(fix).observe(document.body, { childList: true, subtree: true }); setTimeout(fix, 1500); setTimeout(fix, 4000);
})();
