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
