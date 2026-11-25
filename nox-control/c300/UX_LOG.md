# UX_LOG: страница -> найдено -> исправлено -> U до/после
U до/после пока не измерены: qa_audit.py на сервере не запускался (в этой сессии нет доступа к /workspace); запустить фоном по пакету ux_p1.
## Пакет ux_p1 (деплой ux_dep_p1, прогон 45692051479, QA_CLEAN)
- system: JS-падение «reading percent» при неполном ответе /api/pc-metrics -> защита (нет данных = строка с ошибкой); подписи h2 10.5 px -> 12; hud-lbl 10 -> 12. U: ? -> ?
- widgets: шрифты 10-11 px -> 12 (nox-pages.css). U: ? -> ?
- memory, knowledge, cinema, map, дашборд/холст/Canvas/Карта темы (K6 FAB): 404 иконок tabler (bounding-box, diagram-3, grid-1x2, file-earmark-text, player-play-filled) -> существующие имена; map/widgets: 404 marker-shadow.png -> добавлен файл.
- Обход без дефектов (hscroll 0, ошибок JS 0, безымянных кнопок 0): advisors, assistant, projects, music, news, mail, calendar, finance, training, tools, contacts, events, messenger, notifications, social, studio, tv.
- Известно, не исправлялось: header .tb-t высотой 38 px и .tb-i 32 px на 1440 (канон nox-shell/nox-unify), leaflet-маркер без alt, projects: required в скрытой форме диалога пишет в консоль «not focusable».
