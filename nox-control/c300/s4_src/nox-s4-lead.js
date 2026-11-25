/* S4 · страницы «остальных» разделов в раскладке лидера ниши. Без сервиса: честное «не подключено» (NOXds.unavailable) в той же раскладке; с данными: реальные источники.
   Конфиг: data-lead на теге script. Исходная заглушка страницы скрывается, а не удаляется. */
(function () {
  const me = document.currentScript, kind = me && me.dataset.lead; if (!kind) return;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const empty = (el, icon, title, text) => { if (window.NOXds) NOXds.empty(el, { icon, title, text }); else el.innerHTML = '<p class="muted">' + esc(title + '. ' + text) + '</p>'; };
  const off = (el, why) => { if (window.NOXds) NOXds.unavailable(el, why); else el.textContent = why; };
  const btn = (id, ic, t, v, dis) => '<span class="seg"><button type="button" id="' + id + '"' + (dis ? ' disabled' : '') + '><sl-icon library="tabler" name="' + ic + '"></sl-icon>' + t + '</button></span>';
  const C = {
    mail: { lead: 'Gmail', kick: 'Входящие · отправка · фильтры', title: 'Почта', cols: [['Папки', ['Входящие', 'Отправленные', 'Черновики', 'Спам', 'Корзина']], ['Письма'], ['Чтение']], act: [['Написать', 'pencil'], ['Подключить ящик (IMAP/SMTP)', 'plug']], why: 'Почтовый ящик не подключён: нет IMAP/SMTP-учётных данных. Подключите его в «Подключениях».', icon: 'mail' },
    messenger: { lead: 'Telegram', kick: 'Единые диалоги подключённых аккаунтов', title: 'Мессенджеры', cols: [['Чаты', ['Все', 'Личные', 'Группы']], ['Диалог'], ['Профиль']], act: [['Новый чат', 'message-plus'], ['Подключить аккаунт', 'plug']], why: 'Аккаунты мессенджеров не подключены. Подключите их в «Подключениях».', icon: 'message-circle' },
    social: { lead: 'X / Threads', kick: 'Лента · профили · права', title: 'Лента', cols: [['Навигация', ['Лента', 'Профиль', 'Связи', 'Права доступа']], ['Лента'], ['Кого читать']], act: [['Опубликовать', 'send']], why: 'Социальная лента NOX не запущена: нет сервиса профилей и связей.', icon: 'users' },
    calls: { lead: 'Google Meet', kick: 'Звонки · перевод RU↔ES · субтитры', title: 'Звонки', cols: [['Встречи', ['Недавние', 'Запланированные']], ['Звонок'], ['Субтитры']], act: [['Начать звонок', 'phone']], why: 'Сервис звонков и перевода (WhisperLive) не подключён к странице.', icon: 'phone' },
    contacts: { lead: 'Google Контакты', kick: 'Люди · встречи · календарь отдельно', title: 'Контакты', cols: [['Группы', ['Все', 'Избранные', 'Недавние']], ['Контакты'], ['Карточка']], act: [['Добавить контакт', 'user-plus'], ['Подключить CardDAV', 'plug']], why: 'Адресная книга не подключена (Radicale отвечает перенаправлением, учётная запись не настроена).', icon: 'address-book' },
    'book-reader': { lead: 'Apple Books', kick: 'Полка · страница · закладки', title: 'Книги', cols: [['Полка', ['Читаю', 'Хочу прочитать', 'Прочитано']], ['Библиотека'], ['Закладки']], act: [['Добавить книгу', 'book-upload']], why: 'Библиотека книг пуста: источник книг (OPDS/Calibre) не подключён.', icon: 'books' },
    games: { lead: 'Steam', kick: 'Игры с персонами', title: 'Игры', cols: [['Библиотека', ['Все', 'Настольные', 'Викторины']], ['Игры'], ['Партия']], act: [['Новая партия', 'player-play']], why: 'Игровой сервис не подключён: в библиотеке нет игр.', icon: 'device-gamepad-2' },
    finance: { lead: 'Actual Budget', kick: 'Бюджет · учёт · графики', title: 'Финансы', cols: [['Счета', ['Все счета', 'Бюджет', 'Отчёты']], ['Операции'], ['Сводка']], act: [['Открыть Actual', 'external-link']], why: 'Actual Budget установлен (:18204), но не интегрирован: счета и операции требуют входа. Откройте отдельно.', icon: 'wallet' }
  };
  document.addEventListener('DOMContentLoaded', () => {
    const wrap = document.querySelector('main .wrap') || document.querySelector('.wrap'); if (!wrap) return;
    const old = [...wrap.children]; const root = document.createElement('div'); root.className = 's4ld';
    const hide = () => old.forEach((e) => (e.style.display = 'none'));
    if (kind === 'notifications') {
      root.innerHTML = '<div class="ph"><div><span class="kick mono">Slack · Входящие · журнал команд</span><h1>Уведомления</h1></div></div><div class="s4ls"><section class="card s4lc"><h2>Лента <span class="r mono" id="s4ln">…</span></h2><div id="s4lf"></div></section></div>';
      wrap.prepend(root); hide();
      fetch('/api/nox/outbox', { cache: 'no-store' }).then((r) => r.json()).then((j) => { const m = (j.messages || []).slice(-60).reverse(), f = root.querySelector('#s4lf'); root.querySelector('#s4ln').textContent = m.length + ' шт.';
        if (!m.length) return empty(f, 'bell-off', 'Уведомлений нет', 'NOX пока ничего не присылал.');
        f.innerHTML = m.map((x) => '<div class="s4lr"><i class="s4d g"></i><div><div>' + esc(String(x.text || '').slice(0, 300)) + '</div><small class="mono">' + new Date(x.ts * 1000).toLocaleString('ru-RU') + '</small></div></div>').join(''); })
        .catch(() => off(root.querySelector('#s4lf'), 'Лента уведомлений недоступна: /api/nox/outbox не отвечает.')); return;
    }
    if (kind === 'nexus') {
      root.innerHTML = '<div class="ph"><div><span class="kick mono">Сетевой граф · органы ядра и службы</span><h1>Nexus</h1></div><div class="acts"><span class="seg"><button type="button" id="s4nf"><sl-icon library="tabler" name="focus-centered"></sl-icon>Вписать</button></span></div></div><section class="card s4lc"><h2>Граф связей <span class="r mono" id="s4nn">…</span></h2><div class="s4nw"><div id="s4ny"></div><aside id="s4ni" class="muted">Нажмите на узел.</aside></div></section>';
      wrap.prepend(root); hide();
      Promise.all([fetch('/api/nox/status', { cache: 'no-store' }).then((r) => r.json()).catch(() => null), fetch('./data/live.json?t=' + Date.now(), { cache: 'no-store' }).then((r) => r.json()).catch(() => null)]).then(([st, lv]) => {
        const el = []; const org = st && st.health && st.health.organs || {}, ports = lv && lv.ports || {};
        el.push({ data: { id: 'NOX', l: 'NOX', c: '#f2c14e', s: 30 } }); el.push({ data: { id: 'core', l: 'Ядро', c: '#e0954a', s: 20 } }); el.push({ data: { id: 'ec', source: 'NOX', target: 'core' } });
        Object.keys(org).forEach((k) => { el.push({ data: { id: 'o:' + k, l: k, c: org[k] ? '#8fc28a' : '#d64630', s: 12, d: 'Орган ядра: ' + (org[k] ? 'жив' : 'не отвечает') } }); el.push({ data: { id: 'eo' + k, source: 'core', target: 'o:' + k } }); });
        el.push({ data: { id: 'svc', l: 'Службы', c: '#6aa9d8', s: 20 } }); el.push({ data: { id: 'es', source: 'NOX', target: 'svc' } });
        Object.keys(ports).forEach((k) => { const ok = ports[k] && ports[k].ok; el.push({ data: { id: 'p:' + k, l: k, c: ok ? '#8fc28a' : '#d64630', s: 12, d: 'Служба: ' + (ok ? 'жива' : 'нет ответа') + (ports[k] && ports[k].via ? ' (' + ports[k].via + ')' : '') } }); el.push({ data: { id: 'ep' + k, source: 'svc', target: 'p:' + k } }); });
        root.querySelector('#s4nn').textContent = (Object.keys(org).length + Object.keys(ports).length) + ' узлов';
        if (el.length < 6) { off(root.querySelector('#s4ny'), 'Нет данных: ядро и службы не ответили.'); return; }
        if (!window.cytoscape) { off(root.querySelector('#s4ny'), 'Cytoscape не загружен.'); return; }
        const cy = cytoscape({ container: root.querySelector('#s4ny'), elements: el, layout: { name: 'cose', animate: false, nodeRepulsion: 12000, idealEdgeLength: 70 }, wheelSensitivity: .25,
          style: [{ selector: 'node', style: { 'background-color': 'data(c)', width: 'data(s)', height: 'data(s)', label: 'data(l)', color: '#cfc4bd', 'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 3 } }, { selector: 'edge', style: { width: 1, 'line-color': 'rgba(255,235,220,.2)', 'curve-style': 'haystack' } }, { selector: ':selected', style: { 'border-width': 2, 'border-color': '#fff' } }] });
        cy.on('tap', 'node', (e) => { const d = e.target.data(); root.querySelector('#s4ni').innerHTML = '<b>' + esc(d.l) + '</b><p>' + esc(d.d || '') + '</p>'; });
        root.querySelector('#s4nf').onclick = () => cy.fit(undefined, 30); addEventListener('resize', () => cy.resize());
      }); return;
    }
    if (kind === 'map') {
      root.innerHTML = '<div class="ph"><div><span class="kick mono">Google Maps · карта мира</span><h1>Карта</h1></div></div><section class="card s4lc"><div id="s4map"></div></section>';
      wrap.prepend(root); hide();
      if (window.L) { const m = L.map('s4map', { worldCopyJump: true, zoomControl: true }).setView([30, 20], 2); L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(m); setTimeout(() => m.invalidateSize(), 300); }
      else off(root.querySelector('#s4map'), 'Библиотека карты (Leaflet) не загружена.'); return;
    }
    const c = C[kind]; if (!c) return;
    root.innerHTML = '<div class="ph"><div><span class="kick mono">' + esc(c.kick) + '</span><h1>' + esc(c.title) + '</h1></div><div class="acts">' + c.act.map((a, i) => btn('s4a' + i, a[1], esc(a[0]), i ? 'default' : 'primary', kind !== 'finance' || i > 0 ? i === 0 : false)).join('') + '</div></div>'
      + '<div class="s4l3"><aside class="card s4lc"><h2>' + esc(c.cols[0][0]) + '</h2>' + (c.cols[0][1] || []).map((x, i) => '<button type="button" class="s4li' + (i ? '' : ' on') + '">' + esc(x) + '</button>').join('') + '</aside>'
      + '<section class="card s4lc"><h2>' + esc(c.cols[1][0]) + '</h2><div id="s4m"></div></section><section class="card s4lc"><h2>' + esc(c.cols[2][0]) + '</h2><div id="s4r"></div></section></div>';
    wrap.prepend(root); hide();
    off(root.querySelector('#s4m'), c.why); empty(root.querySelector('#s4r'), c.icon, 'Ничего не выбрано', 'Выберите элемент слева, когда сервис будет подключён.');
    root.querySelectorAll('.s4li').forEach((b) => (b.onclick = () => { root.querySelectorAll('.s4li').forEach((x) => x.classList.remove('on')); b.classList.add('on'); }));
    const a1 = root.querySelector('#s4a1'); if (a1) a1.onclick = () => { location.href = kind === 'finance' ? '/svc/actual/' : 'connections.html'; };
    if (kind === 'finance') { const a0 = root.querySelector('#s4a0'); a0.removeAttribute('disabled'); a0.onclick = () => window.open('/svc/actual/', '_blank', 'noopener'); }
    if (kind !== 'finance') { const a0 = root.querySelector('#s4a0'); a0 && (a0.title = 'Недоступно: сервис не подключён'); }
  });
})();
