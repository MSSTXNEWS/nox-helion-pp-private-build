# M_LOG: мобильная адаптация (дизайнер M)
## 2026-11-25
- Этап 1: MOBILE_REFS.md (105 приложений, топ-20 паттернов).
- Этап 2: vendor/pulltorefresh (0.1.22), vendor/use-gesture (10.3.1) добавлены; ios-haptics, swiper, shoelace, gsap, motion уже стояли. Лёгкие, < 0.1 МБ.
- Этап 3: site/nox-m-mobile.css + nox-m-mobile.js, тег подключён в 78 страниц (бэкапы *.bak_m_1); все правила только в @media (max-width:768px) / mq.matches.
  - Таб-бар (#nox-m-tab) вместо дока, шторка «Ещё» (сетка nav.json), единая кнопка ИИ (#nox-m-ai) вместо .nmc-fab/#nxmPill/#nxnavx/.nai-btn (старые остаются в DOM, скрыты, вызываются click()).
  - --ds-dock-h / --dock-h = высота таб-бара.
  - Нижние шторки: sl-dialog и .s2-modal; свайп вниз закрывает; свайп от левого края = назад; pull-to-refresh на страницах данных.
  - Чат на мобильном: открывается сразу (index -> chat, ?home=1 для главной); только лента и поле; колонки S1 (диалоги/команды/заготовки/система) скрыты, доступны через таб-бар «Диалоги», «Команды», «Заготовки» (шторки-прокси кликают оригиналы).
  - JS-фиксы: цели >= 44 px, шрифт >= 14 px (inline !important), без горизонтального скролла.
- Согласование с S1: классы колонок чата не известны; шторки опираются на текущие селекторы (.lv-bar, .lv-dd sl-menu-item, .lv-tag, .lv-inc, #cxChips button, #btnThreads, #tgWid, #nuiVoice, #nuiFlow, #btnPalette, #btnSettings). При смене классов обновить функции commands()/tpls() в nox-m-mobile.js.
- Инфра: лимит GitHub API и 503 при общем опросе run.sh; сервер раньше давал ERR_CONNECTION_REFUSED на ходу.
