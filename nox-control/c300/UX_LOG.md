# UX_LOG: страница -> найдено -> исправлено -> U до/после
U до/после пока не измерены: qa_audit.py на сервере не запускался (в этой сессии нет доступа к /workspace); запустить фоном по пакету ux_p1.
## Пакет ux_p1 (деплой ux_dep_p1, прогон 45692051479, QA_CLEAN)
- system: JS-падение «reading percent» при неполном ответе /api/pc-metrics -> защита (нет данных = строка с ошибкой); подписи h2 10.5 px -> 12; hud-lbl 10 -> 12. U: ? -> ?
- widgets: шрифты 10-11 px -> 12 (nox-pages.css). U: ? -> ?
- memory, knowledge, cinema, map, дашборд/холст/Canvas/Карта темы (K6 FAB): 404 иконок tabler (bounding-box, diagram-3, grid-1x2, file-earmark-text, player-play-filled) -> существующие имена; map/widgets: 404 marker-shadow.png -> добавлен файл.
- Обход без дефектов (hscroll 0, ошибок JS 0, безымянных кнопок 0): advisors, assistant, projects, music, news, mail, calendar, finance, training, tools, contacts, events, messenger, notifications, social, studio, tv.
- Известно, не исправлялось: header .tb-t высотой 38 px и .tb-i 32 px на 1440 (канон nox-shell/nox-unify), leaflet-маркер без alt, projects: required в скрытой форме диалога пишет в консоль «not focusable».
## Пакет ux_p2 (деплой ux_dep_p2, прогон 45700182835, QA_CLEAN)
- projects: required в скрытой форме диалога -> novalidate + aria-invalid + toast «Введите название» при пустом названии.
- pdf: 404 иконки easel -> presentation. atlas: подписи 11.5 -> 12 px.
- Обход без дефектов (1440/390: hscroll 0, JS 0): about, benchmark, browser, calls, connections, consciousness, constructor, dispatcher, downloads, editor, effects, evolution, forge, games, glance, growth, install, integrations, intents, live, marketing, models, money, nexus, operators, ops, organism, pc-control, pc-maintenance, planets, scene, selffeel, soul, spaces, voice, weights, ai-learning, mini.
- Не исправлено: board (excalidraw с unpkg не грузится без сети - вендорить), qa.html (JS: prepend of null), about/integrations (404 hdr/metal/moon/mars текстур в снимке), #k8-live 25 px на 390.
## Замер U (очередь: u_audit5 -> ux_aud_p1 -> ux_aud_p2, flock /tmp/qaa.lock)
Результаты: $O/ux_qa_prog.txt (system widgets memory map cinema knowledge) и ux_qa2_prog.txt (projects pdf atlas); забирать ux_get_p2.sh. U до -> после: заполнить по факту.
## Пакет ux_p3 (ux_dep_p3, прогон 45701689515, QA_CLEAN)
- qa.html: JS «prepend of null» (nox-shell искал #app) -> main обёрнут в div#app.
- board: EXCALIDRAW_ASSET_PATH ставился после загрузки скрипта, чанки шли с unpkg -> путь задан inline до excalidraw.production.min.js (вендор уже лежал в vendor/nox-x/excalidraw/dist); запросов на unpkg нет.
- about/integrations: на сервере отсутствовали текстуры реестра; докачаны HDRI machine_shop_01_1k (CC0 Poly Haven), Metal012_1K Color (CC0 ambientCG), 2k_moon, 2k_mars -> nox-mars.jpg (Solar System Scope, CC BY 4.0).
- qa_audit.py: режим QA_FAST=1 (1 vision-прогон, только 1440, max_tokens 600; бэкап qa_audit.py.bak_ux_fast_*, по умолчанию выключен). Очередь ux_fast1.sh (после u_audit5, flock): system widgets memory map cinema knowledge projects pdf atlas board qa about integrations -> $O/ux_f_prog.txt.
- Цвета в правках: только CSS-переменные (под тему «Графит»).
