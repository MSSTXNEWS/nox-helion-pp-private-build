/* S4 · встроенные сервисы в стеклянных рамках (/svc/<имя>/). Проверка доступности и абсолютных путей ассетов (режим strip). Конфиг: data-svc="имя:Заголовок,имя:Заголовок". */
(function () {
  const me = document.currentScript; const cfg = (me && me.dataset.svc || '').split(',').filter(Boolean).map((s) => s.split(':'));
  const wrap = document.querySelector('.wrap'); if (!wrap || !cfg.length) return;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  cfg.forEach(([n, title]) => {
    const sec = document.createElement('section'); sec.className = 'card s4sv';
    sec.innerHTML = '<h2>' + esc(title) + ' <span class="r mono" data-st>проверка…</span></h2><div class="s4fb"><button type="button" data-o>Открыть отдельно</button><button type="button" data-r>Обновить</button></div><iframe title="' + esc(title) + '" loading="lazy" hidden></iframe><p class="muted" data-e hidden></p>';
    wrap.appendChild(sec);
    const fr = sec.querySelector('iframe'), st = sec.querySelector('[data-st]'), er = sec.querySelector('[data-e]');
    const url = '/svc/' + n + '/';
    const H = { memos: async () => { const r = await fetch('/svc/memos/api/memos', { cache: 'no-store' }); if (r.status === 401) return { off: 'Memos требует входа: откройте отдельно, создайте учётную запись и заметки.' }; const j = await r.json(); return j.memos && j.memos.length ? { off: 'Заметок: ' + j.memos.length + '. Откройте отдельно.' } : { empty: 'Заметок пока нет.' }; },
      kuma: async () => { const j = await (await fetch('/svc/kuma/api/entry-page', { cache: 'no-store' })).json(); if (j.type === 'setup-database') return { off: 'Uptime Kuma установлена, но не настроена: нужна первичная настройка (создание БД и учётной записи).' }; return { off: 'Данные мониторов Kuma требуют входа: откройте отдельно.' }; },
      beszel: async () => { const j = await (await fetch('/svc/beszel/api/collections/systems/records', { cache: 'no-store' })).json(); if (!j.items) return { off: 'Beszel требует входа: откройте отдельно.' }; if (!j.items.length) return { empty: 'Агенты Beszel не добавлены: хостов для мониторинга пока нет.' }; return { rows: j.items }; } };
    if (H[n]) {
      const st = sec.querySelector('[data-st]'), fr = sec.querySelector('iframe'), er = sec.querySelector('[data-e]'); fr.remove(); er.hidden = false; sec.querySelector('[data-r]').remove();
      sec.querySelector('[data-o]').onclick = () => window.open(url, '_blank', 'noopener');
      H[n]().then((r) => { st.textContent = r.rows ? r.rows.length + ' хостов' : 'на связи';
        if (r.rows && window.echarts) { er.className = 's4kbc'; er.textContent = ''; const c = echarts.init(er, 'nox'); er.style.height = '240px'; c.setOption({ tooltip: { trigger: 'axis' }, legend: { textStyle: { color: '#cfc4bd' } }, grid: { left: 40, right: 10, top: 30, bottom: 30 }, xAxis: { type: 'category', data: r.rows.map((x) => x.name) }, yAxis: { type: 'value', max: 100 }, series: [{ name: 'CPU %', type: 'bar', data: r.rows.map((x) => (x.info && x.info.cpu) || 0) }, { name: 'Память %', type: 'bar', data: r.rows.map((x) => (x.info && x.info.mp) || 0) }] }); }
        else if (window.NOXds) { er.className = ''; r.empty ? NOXds.empty(er, { icon: 'server', title: 'Нет данных', text: r.empty }) : NOXds.unavailable(er, r.off); } else er.textContent = r.empty || r.off; })
        .catch((e) => { st.textContent = 'нет связи'; window.NOXds ? NOXds.unavailable(er, 'Служба не отвечает: ' + e.message) : (er.textContent = 'Служба не отвечает'); });
      return;
    }
    const load = async () => {
      try {
        const r = await fetch(url, { cache: 'no-store', redirect: 'manual' }); if (r.type === 'opaqueredirect') { st.textContent = 'редирект, встраивание невозможно'; fr.hidden = true; er.hidden = false; er.textContent = 'Служба «' + n + '» отвечает перенаправлением на путь вне /svc/ (начальная настройка не завершена или нет режима strip). Откройте отдельно.'; return; } if (!r.ok) throw new Error('HTTP ' + r.status);
        const h = await r.text(), abs = [...h.matchAll(/(?:src|href)="(\/[^\/"][^"]*\.(?:js|css))"/g)].map((m) => m[1]).filter((p) => !p.startsWith('/svc/')).slice(0, 3);
        if (abs.length) { st.textContent = 'на связи, встраивание невозможно'; fr.hidden = true; er.hidden = false; er.textContent = 'Приложение запрашивает ассеты по абсолютным путям (' + abs[0] + ') без префикса /svc/: в рамке оно не загрузится. Откройте отдельно или включите переписывание путей в прокси.'; return; }
        st.textContent = 'на связи'; fr.hidden = false; fr.src = url + '?t=' + Date.now();
      } catch (e) { st.textContent = 'нет связи'; fr.hidden = true; er.hidden = false; er.textContent = 'Служба «' + n + '» недоступна (' + e.message + '). Подключите её или проверьте /svc/' + n + '/.'; }
    };
    sec.querySelector('[data-o]').onclick = () => window.open(url, '_blank', 'noopener'); sec.querySelector('[data-r]').onclick = load; load();
  });
})();
