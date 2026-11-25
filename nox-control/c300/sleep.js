
/* S3: у пульта нет эндпоинтов сна и приоритета чата: вместо мёртвых disabled-кнопок честная пометка */
(() => {
  const fix = () => { const p = document.getElementById('nxpult'); if (!p) return false; p.querySelectorAll('button').forEach((b) => { const t = (b.textContent || '').trim().toLowerCase(); if (b.disabled && (/^сон$|приоритет/.test(t))) { const s = document.createElement('span'); s.className = 'ds-badge-off'; s.title = 'Нет серверного эндпоинта: функция будет доступна после подключения ядра'; s.textContent = t + ': недоступно'; b.replaceWith(s); } }); return true; };
  let n = 0; const t = setInterval(() => { fix(); if (++n > 20) clearInterval(t); }, 700);
})();
