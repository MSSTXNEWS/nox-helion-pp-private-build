/* NOX · вкладки настроек (Личность, Голос, Модели, Автономия, Интерфейс, Безопасность, Данные).
   Существующие карточки settings.html раскладываются по вкладкам; живые панели читают реальные эндпоинты (/glm/v1/nox/stats, /api/chat/health, /api/nox/agents, /api/identity, qa/registry.json).
   Чего на сервере нет — написано прямо, без заглушек-полей. */
(() => {
  if (window.__noxSetTabs || !/settings\.html$/.test(location.pathname)) return; window.__noxSetTabs = 1;
  const TABS = [['personality', 'Личность'], ['voice', 'Голос'], ['models', 'Модели'], ['autonomy', 'Автономия'], ['ui', 'Интерфейс'], ['safety', 'Безопасность'], ['data', 'Данные']];
  const MAP = [[/Голос/, 'voice'], [/Уведомления/, 'autonomy'], [/Резонанс/, 'models'], [/О сборке/, 'data'], [/Планета|Цвет неона|Космос|Плотность/, 'ui']];
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const J = (u) => fetch(u, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status)))).catch(() => null);
  const LS = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
  const dot = (ok) => '<i class="nxs-d" data-s="' + (ok === true ? 'ok' : ok === false ? 'bad' : 'warn') + '"></i>';
  const kv = (rows) => '<div class="nxs-kv">' + rows.map(([k, v, ok]) => '<div>' + (ok === undefined ? '' : dot(ok)) + '<span>' + esc(k) + '</span><b>' + esc(v) + '</b></div>').join('') + '</div>';
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = './nox-pult.css'; document.head.appendChild(css); const css2 = document.createElement('link'); css2.rel = 'stylesheet'; css2.href = './nox-settings-tabs.css'; document.head.appendChild(css2);
  const mk = (tab, title, html) => { const s = document.createElement('section'); s.className = 'card c12 setg nxs-live'; s.dataset.tab = tab; s.innerHTML = '<h3 class="mono">' + title + '</h3>' + html; return s; };

  async function panels() {
    const [st, hl, ag, idn, reg] = await Promise.all([J('/glm/v1/nox/stats'), J('/api/chat/health'), J('/api/nox/agents'), J('/api/identity'), J('qa/registry.json')]);
    const h = st && st.health, out = [];
    const organs = h && h.organs ? Object.entries(h.organs) : [];
    out.push(mk('personality', 'Личность NOX: живые органы',
      (organs.length ? '<div class="nxs-chips">' + organs.map(([k, v]) => '<span data-s="' + (v ? 'ok' : 'bad') + '">' + esc(k) + '</span>').join('') + '</div>' + kv([['Режим совести', h.conscience || '—', h.conscience === 'enforce'], ['Ходов в памяти ядра', String(h.turns != null ? h.turns : '—')]]) : '<p class="note">Данные ядра недоступны: /glm/v1/nox/stats не ответил.</p>')
      + '<p class="note">Ползунки характера (эмоциональность, инициативность) зависят от сервиса TRAITS на :8101; сейчас он не запущен, поэтому полей для них нет. Характер и ценности — на странице <a href="soul.html">Душа</a>.</p>'));
    const ports = hl ? [['Шлюз чата (RTE)', hl.rte && hl.rte.up ? hl.rte.addr : (hl.rte && hl.rte.reason) || 'нет', !!(hl.rte && hl.rte.up)], ['Ядро (:8090)', hl.core && hl.core.up ? 'работает' : (hl.core && hl.core.reason) || 'нет', !!(hl.core && hl.core.up)]] : [['Шлюз чата', 'нет ответа', false]];
    const vr = ag && ag.vram ? [['VRAM', Math.round(ag.vram.used_mib / 1024) + ' из ' + Math.round(ag.vram.total_mib / 1024) + ' ГБ (' + Math.round(ag.vram.frac * 100) + '%)', !ag.vram.over_cap]] : [];
    const gl = h && h.glm ? [['GLM', h.glm.state + ', в работе: ' + h.glm.inflight, h.glm.state === 'up']] : [];
    const depth = LS('nox.depth', 'auto');
    out.push(mk('models', 'Модели и состояние', kv(ports.concat(gl, vr))
      + '<div class="nxs-row"><span>Глубина ответа по умолчанию</span><span class="seg" role="radiogroup" id="nxsDepth">' + [['fast', 'Быстро'], ['auto', 'Авто'], ['deep', 'Глубоко']].map(([v, t]) => '<button type="button" role="radio" data-d="' + v + '" aria-checked="' + (v === depth) + '">' + t + '</button>').join('') + '</span></div>'));
    const agents = ag && ag.agents ? Object.entries(ag.agents) : [];
    out.push(mk('autonomy', 'Что NOX делает сам' + (ag && ag.phase ? ' · фаза: ' + esc(ag.phase) : ''),
      agents.length ? '<div class="nxs-tbl">' + agents.map(([k, a]) => '<div>' + dot(a.status === 'RUNNING') + '<b>' + esc(k) + '</b><span>' + esc(a.role || a.kind || '') + '</span><em>' + esc(a.status) + (a.interval_s ? ' · раз в ' + a.interval_s + ' с' : '') + '</em></div>').join('') + '</div>'
        + '<p class="note">Занят чатом: ' + (ag.chat_busy ? 'да' : 'нет') + '. Включение и остановка агентов — через диспетчер (<a href="dispatcher.html">Диспетчер</a>).</p>' : '<p class="note">Список агентов недоступен: /api/nox/agents не ответил.</p>'));
    const fl = idn && idn.flags ? Object.entries(idn.flags) : [];
    const danger = reg && reg.commands ? Object.entries(reg.commands).filter(([, c]) => c.confirm) : [];
    out.push(mk('safety', 'Безопасность',
      kv(fl.map(([k, v]) => ['Идентичность: ' + k, v ? 'включено' : 'выключено', v ? true : undefined]).concat([['Режим совести ядра', h && h.conscience ? h.conscience : 'нет данных', h && h.conscience === 'enforce']]))
      + (danger.length ? '<p class="note">Команды с подтверждением: ' + danger.map(([k, c]) => esc(c.desc || k)).join('; ') + '. Подтверждение выдаёт одноразовый токен на 60 секунд.</p>' : '<p class="note">В реестре команд сейчас нет опасных; любая будущая команда с подтверждением потребует диалога и токена на 60 секунд. Произвольного shell нет.</p>')
      + '<p class="note">Журнал команд: файл /workspace/nox/state/cmd_log.jsonl на сервере; просмотр в браузере не подключён.</p>'));
    const bk = reg && reg.commands && reg.commands['backup.create'];
    out.push(mk('data', 'Данные и бэкап',
      kv([['Настройки в этом браузере', Object.keys(localStorage).filter((k) => /^nox/.test(k)).length + ' ключей'], ['Бэкап состояния NOX', bk && bk.endpoint ? 'команда backup.create доступна' : 'не подключён (нет эндпоинта)', bk && bk.endpoint ? true : undefined]])
      + '<p class="note">Экспорт, импорт и сброс настроек — кнопки в шапке страницы. Библиотеки и лицензии: <a href="about.html">О сборке</a>.</p>'));
    return out;
  }

  const build = async () => {
    const cards = [...document.querySelectorAll('section.setg')];
    if (!cards.length) return setTimeout(build, 300);
    const parent = cards[0].parentNode;
    cards.forEach((c) => { const t = (c.querySelector('h3') || {}).textContent || ''; const hit = MAP.find(([re]) => re.test(t)); c.dataset.tab = hit ? hit[1] : 'ui'; });
    const bar = document.createElement('div'); bar.className = 'nxt-tabs'; bar.setAttribute('role', 'tablist'); bar.setAttribute('aria-label', 'Разделы настроек');
    bar.innerHTML = TABS.map(([k, t], i) => '<button type="button" role="tab" data-tab="' + k + '" aria-selected="' + (i === 0) + '">' + t + '</button>').join('');
    const host = parent.closest('.grid') || parent; host.parentNode.insertBefore(bar, host);
    const show = (k) => { bar.querySelectorAll('[role="tab"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === k))); parent.querySelectorAll('section.setg').forEach((s) => s.classList.toggle('nxt-off', s.dataset.tab !== k)); try { localStorage.setItem('nox.settings.tab', k); } catch (e) { /* не критично */ } };
    bar.addEventListener('click', (e) => { const b = e.target.closest('[role="tab"]'); if (b) show(b.dataset.tab); });
    const live = await panels(); live.forEach((s) => parent.appendChild(s));
    if (window.NOXworlds) { const s = document.createElement('section'); s.className = 'card c12 setg'; s.dataset.tab = 'ui'; s.appendChild(window.NOXworlds.widget()); parent.insertBefore(s, parent.firstChild); }
    parent.addEventListener('click', (e) => { const b = e.target.closest('#nxsDepth [data-d]'); if (!b) return; try { localStorage.setItem('nox.depth', b.dataset.d); } catch (x) { /* нет хранилища */ } b.parentNode.querySelectorAll('[data-d]').forEach((x) => x.setAttribute('aria-checked', String(x === b))); });
    const q = new URLSearchParams(location.search).get('tab'); let start = q || LS('nox.settings.tab', 'ui');
    show(TABS.some(([k]) => k === start) ? start : 'ui');
  };
  build();
})();
