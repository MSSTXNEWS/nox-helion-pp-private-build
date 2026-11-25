/* S4 · Органы и процессы: таблица Tabulator (готовый модуль) вместо сырой HTML-таблицы; данные берутся из реальной таблицы панели. Только на organism. */
(function () {
  const run = () => {
    const B = document.querySelector('#nbxLiveB'); if (!B || !window.Tabulator) return;
    const tb = B.querySelector('table'); if (!tb || tb.dataset.s4) return; tb.dataset.s4 = 1;
    const rows = [...tb.querySelectorAll('tbody tr')].map((tr) => { const c = [...tr.children].map((x) => x.textContent.trim()); return { organ: c[0], port: c[1], st: c[2], via: c[3] }; });
    if (!rows.length) return; tb.style.display = 'none';
    const host = document.createElement('div'); host.className = 's4tab'; tb.before(host);
    new Tabulator(host, { data: rows, layout: 'fitColumns', height: Math.min(420, 44 + rows.length * 42), movableColumns: false, placeholder: 'Нет данных',
      columns: [{ title: 'Орган', field: 'organ', headerFilter: 'input', minWidth: 140 }, { title: 'Порт', field: 'port', width: 100, hozAlign: 'right' },
        { title: 'Статус', field: 'st', width: 150, formatter: (c) => { const v = c.getValue(), ok = /жив/i.test(v); return '<span class="s4st ' + (ok ? 'ok' : 'off') + '">' + v.replace(/[&<>]/g, '') + '</span>'; } }, { title: 'Ответ', field: 'via', minWidth: 120 }] });
  };
  document.addEventListener('DOMContentLoaded', () => { run(); new MutationObserver(run).observe(document.body, { childList: true, subtree: true }); });
})();
