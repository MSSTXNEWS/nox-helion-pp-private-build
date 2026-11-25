/* NOX · вкладки настроек (расширение): группирует существующие карточки settings.html по вкладкам.
   Разделы без функций честно помечаются «появится»; настройки, которых нет на сервере, не выдаются за рабочие. */
(() => {
  if (window.__noxSetTabs || !/settings\.html$/.test(location.pathname)) return; window.__noxSetTabs = 1;
  const TABS = [
    ['personality', 'Личность'], ['voice', 'Голос'], ['models', 'Модели'], ['autonomy', 'Автономия'],
    ['ui', 'Интерфейс'], ['safety', 'Безопасность'], ['data', 'Данные']
  ];
  /* соответствие заголовков карточек вкладкам; неизвестное — в «Интерфейс» */
  const MAP = [
    [/Голос/, 'voice'], [/Уведомления/, 'autonomy'], [/Резонанс/, 'models'], [/О сборке/, 'data'],
    [/Планета|Цвет неона|Космос|Плотность/, 'ui']
  ];
  const PH = {
    personality: ['Характер, эмоциональность, инициативность и смайлики', 'Ползунки личности появятся в следующей версии.'],
    models: ['Тело, судьи, советники, глубина по умолчанию, лимиты VRAM и диска', 'Выбор моделей и лимиты появятся в следующей версии. Глубину ответа пока можно выбрать в пульте (ПУЛЬТ в левом нижнем углу).'],
    autonomy: ['Что NOX делает сам, что с подтверждением, тихие часы', 'Правила автономии и тихие часы появятся в следующей версии.'],
    safety: ['Подтверждение опасных команд, вход снаружи, журнал команд', 'Подтверждение опасных команд уже работает в пульте и в шине команд; настройки входа и журнал появятся в следующей версии.'],
    voice: ['Голос, скорость, ударения, паузы и числа', 'Выбор голоса и скорости появится в следующей версии. Переключатель озвучки выше сохраняет выбор.'],
    ui: ['Пять миров, качество, 4K', 'Выбор миров HELION, CHRONOS, SOMNIUM, FORGE и SYNAPSE, качество MAX/BALANCED/ECO и 4K появятся в следующей версии. Цвет, планета и плотность уже настраиваются ниже.'],
    data: ['Бэкапы и экспорт', 'Бэкап и снимок состояния появятся в следующей версии. Экспорт, импорт и сброс настроек — кнопки в шапке страницы.']
  };
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = './nox-pult.css'; document.head.appendChild(css);

  const build = () => {
    const cards = [...document.querySelectorAll('section.setg')];
    if (!cards.length) return setTimeout(build, 300);
    const parent = cards[0].parentNode;
    cards.forEach((c) => {
      const h = (c.querySelector('h3') || {}).textContent || '';
      const hit = MAP.find(([re]) => re.test(h));
      c.dataset.tab = hit ? hit[1] : 'ui';
    });
    /* пустые вкладки получают честную заглушку */
    TABS.forEach(([k]) => {
      if (k === 'ui' || cards.some((c) => c.dataset.tab === k)) return;
      const [t, txt] = PH[k];
      const s = document.createElement('section'); s.className = 'card c12 setg nxt-ph'; s.dataset.tab = k;
      s.innerHTML = '<h3 class="mono">' + t + '</h3><p>' + txt + '</p>';
      parent.appendChild(s);
    });
    const bar = document.createElement('div'); bar.className = 'nxt-tabs'; bar.setAttribute('role', 'tablist'); bar.setAttribute('aria-label', 'Разделы настроек');
    bar.innerHTML = TABS.map(([k, t], i) => '<button type="button" role="tab" data-tab="' + k + '" aria-selected="' + (i === 0) + '">' + t + '</button>').join('');
    const host = parent.closest(".grid") || parent; host.parentNode.insertBefore(bar, host);
    const show = (k) => {
      bar.querySelectorAll('[role="tab"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === k)));
      parent.querySelectorAll('section.setg').forEach((s) => s.classList.toggle('nxt-off', s.dataset.tab !== k));
      try { localStorage.setItem('nox.settings.tab', k); } catch (e) { /* не критично */ }
    };
    bar.addEventListener('click', (e) => { const b = e.target.closest('[role="tab"]'); if (b) show(b.dataset.tab); });
    let start = 'ui'; try { start = localStorage.getItem('nox.settings.tab') || 'ui'; } catch (e) { /* по умолчанию */ }
    show(TABS.some(([k]) => k === start) ? start : 'ui');
  };
  build();
})();
