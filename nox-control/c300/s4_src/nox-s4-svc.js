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
