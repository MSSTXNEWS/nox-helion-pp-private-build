# THEME_LOG (TH): тема «Графит»

## Пакет gr1: тема + кнопки
- Тема по умолчанию «Графит» (html[data-nox-theme=graphite]); «Солнце (классика)» = nox.ui.theme=sun (или ?theme=sun), прежний вид без изменений.
- Токены: шкала Radix Colors slate dark (MIT) --gx-1..12; акцент серебристо-голубой #9db1d1 (--cy 157,177,209); янтарь --am 224,184,120 малыми дозами; success #6cc59a, warn #e0b878, danger #e5736b; Shoelace --sl-color-primary/neutral/success/warning/danger, --sl-focus-ring, --sl-input-*.
- Фон: noise (SVG feTurbulence), радиальные градиенты, сетка 64px с маской, аврора 90 с (reduced-motion: статично). #space/#dust скрыты, сцена three.js в Графите не запускается (guard в nox-wow-bg.js).
- Авто-карта nox-graphite-map.css: th_gen_map.py дублирует каждое правило всех CSS и <style> сайта с тёплым цветом под html[data-nox-theme=graphite] с цветом в серо-голубой гамме (красные «danger» не трогает). Пересобирается скриптом деплоя; после крупных правок CSS другими агентами повторить: python3 th_gen_map.py SITE SITE/nox-graphite-map.css.
- ECharts-тема nox: серая палитра (патч nox-ds.js). Команды палитры: «Тема: Графит», «Тема: Солнце» (nox-actions.js). Переключатель: карточка «Тема» в Настройки > Интерфейс (nox-theme.js), localStorage nox.ui.theme, тема ставится до отрисовки (document.write link в head).
- Кнопки: .nx-btn (primary/secondary/ghost/danger/icon; sm 32, md 36, lg 44), sl-button и разовые кнопки страниц сведены глобальным CSS (радиус 8, фокус-кольцо 2px, мягкие hover/active/disabled).
- Не охвачено: стили, которые JS пишет inline/в <style> во время работы; страницы без nox-theme.js (operators, live, *-s1.main).
- Изменённые файлы: nox-theme.js, nox-wow-bg.js, nox-ds.js, nox-actions.js (бэкапы *.bak_th_<ts>), новые nox-graphite.css, nox-graphite-map.css.
- Снимки: nox-control/c300/screens_th/ (before_* до, btn_* и after_* после).
- Откат: gh workflow run nox-c300.yml -f script=th_rb_gr1.sh (восстановит бэкапы, удалит css), либо у пользователя: localStorage nox.ui.theme=sun.

## Пакет gr2: логотип, иконки Lucide, карта цветов
- Логотип NOX: nox-logo.svg (кольцо серебро + тёмный диск, янтарная точка), в Графите заменяет красную кляксу-аватар `.tg-av-orb` (canvas скрыт) и класс `.nox-logo`; `.nbx-orb` нейтральные кольца.
- Иконки: основной набор Lucide v1.80 (ISC, 2431 иконка, сетка 24, линия 2px, в Графите 1.75 через `sl-icon::part(svg)`). Подмена глобально: резолвер библиотеки `tabler` в nox-nav.js и nox-wow.js (патч TH-ICONS) вызывает `NOXiconUrl` (nox-icons.js): карта имён Tabler -> Lucide (около 100 алиасов), нет в Lucide - остаётся Tabler. Страницы не переписаны. Файлы: vendor/lucide/icons (из lucide.zip), nox-icons.js. 3 имени, которые давали 404 в Tabler (layout-split, grid-1x2, player-play-filled), теперь замаплены. В теме «Солнце» остаются Tabler.
- Сравнение 30 иконок: screens_th/icons_compare.png (Tabler/Lucide/Phosphor). Из 59 иконок, реально загружаемых на 79 страницах, Lucide покрыл все (21 по алиасам), Phosphor под теми же именами не нашёл 35 (другая схема имён), у Tabler 1 нет (easel). Запасные: Phosphor (MIT, мягче линия), Tabler (прежний, fallback).
- Карта цветов: th_gen_map.py теперь разбирает и CSS внутри строк JS (инжектируемые стили); --mg в Графите стал лавандовым; nox-theme.js подключён в operators.html. live.html (отдельная страница статуса, синяя палитра, без sl-icon) не трогали.
- Web Awesome 3: лицензия MIT (Fonticons), 3.15.0, 20 МБ распакованно / 16 МБ dist-cdn / 2645 файлов. Пилот локально на settings (screens_th/wa_before_settings_1440.jpg, wa_after_settings_1440.jpg): компоненты работают, но default-тема WA светлая, а её глобальные стили перекрашивают существующие кнопки страницы; иконки WA грузятся с CDN FontAwesome (нужна офлайн-библиотека). Вывод: в прод не ставили, нужна отдельная тёмная тема на --wa-* и изоляция; пока CSS-мост поверх sl-* (gr1).
- Снимки 2560 и 390: screens_th/gr2_<page>_<2560|390>.jpg (Графит) и sun_<page>_<2560|390>.jpg (Солнце), 8 страниц: index, chat, creative, settings, system, music, news, photo.
- Откат: th_rb_gr2.sh (возврат к gr1), th_rb_gr1.sh (полный откат темы).

## Пакет gr3
- 4K: на index (body[data-page=home]) был двойной zoom (nox-4k.css html{zoom:1.55} + nox-home-v.css .page{zoom:1.5}), макет вылезал. nox-th-fix.css (грузится всегда, обе темы): page zoom 1, .wrap max-width 1560 css px по центру, отступ сверху. Снимок: screens_th/gr3_index_2560.jpg.
- photo: ошибка `(a.response||[]).forEach is not a function` приходила из Filerobot (vendor/nox-x/filerobot/filerobot-image-editor.min.js): при language ru он грузит переводы с внешнего i18n-fastly.ultrafast.io, и если ответ не массив, падает. Патч: Array.isArray(a.response). Воспроизводилась только когда ответ-объект (в моём тесте мок), на сервере QA её не показывал. Внешний запрос остаётся (стоит убрать в отдельной задаче: отдать переводы локально).
- Логотип NOX: шапка/пульт (#nxsun, она же на мобильном), аватар чата .tg-av-orb, мини-чат .nmc-fab.
- Регрессия gr2, найденная и исправленная: сканер строк JS породил правило `html[graphite] button{background:#515358}` (из nox-k6-live.js), все кнопки стали серыми. Сканер теперь отбрасывает правила по голым тегам. Порядок CSS: сначала карта, потом nox-graphite.css, чтобы ручные правила побеждали.
- Откат: th_rb_gr3.sh возвращает к gr2.

## Пакет gr4
- Двойной zoom на 2560: проверены все 79 страниц (html zoom x zoom элементов, выход за ширину). Остался только `.s2{zoom:1.6}` на board, cinema, music, news, studio: там html zoom равен 1, то есть масштаб одинарный и намеренный, переполнения нет. Больше двойных нет.
- Filerobot: переводы локально (vendor/nox-x/filerobot/fie-i18n.json, 111 строк, ru), запрос к i18n-fastly.ultrafast.io убран патчем. Проверено в браузере: интерфейс по-русски, внешних запросов 0.
- Найдено при обходе снимков: на news/calendar/cinema/studio видны парные кнопки (.s6h). Причина: `.s6h{display:none!important}` (nox-s6.css) проигрывает `.k4-btn{display:inline-flex!important}` (nox-k4-core.css) по порядку. Баг есть и в «Солнце». Фикс в nox-th-fix.css.
- Primary-кнопки разнобоем (светлые и сине-стальные): все приведены к светлому серебру, включая классовые sl-button (s6sl). Бейджи sl-badge (сплошной янтарь) стали тонированными. 
- Снимки обхода: screens_th/review_1440_a|b|c.jpg, review_2560_a|b|c.jpg, review_390_all.jpg (18 страниц: до правок gr4), после: gr4_news_calendar_music_photo_1440.jpg.
- Не правили: белый круг-узел в графе на memory (JS), синеватые иконки на tools, красные плашки YouTube на cinema (бренд).
- Откат: th_rb_gr4.sh.

## Пакет gr5
- Граф памяти (memory): белый узел-запрос стал серебристо-голубым (#c2d0e8), палитра типов узлов, рёбер и подписей серо-голубая (патч nox-s4-memory.js, зависит от `data-nox-theme`).
- Обход остальных 61 страниц на 1440 (листы screens_th/review_rest_1440_0..4.jpg): дёшево выглядели atlas (оранжевое свечение глобуса), training/growth (оранжевые линии и заливка графиков), nexus (кислотные узлы), organism (серый #666 фон Tabulator), assistant (коричневатый Monaco).
- Универсальный патч (patch.py, п.9): в JS-файлах nox-*.js литералы цвета `'#hex'`/`'rgba(...)'` с тёплым оттенком заменяются на `(window.NOXgx ? серо-голубой : прежний)`. Красные (danger) не трогаются. `window.NOXgx` ставит nox-theme.js. Идемпотентно (маркер TH-GXW в конце файла), каждый файл проверяется `node --check`. Исключены dz-creative, worlds, sun, live. ~40 файлов. В «Солнце» поведение прежнее.
- CSS: Tabulator и Monaco в серых тонах.
- Не правили: белые ячейки теплокарты на growth, красный узел NOX на nexus (hub), столбцы benchmark (данные), страницы glance/downloads (белый iframe в моём моке, не проверено на сервере).
- Откат: th_rb_gr5.sh (восстанавливает все nox-*.js из резервной папки /workspace/nox/web/th_gr5_bak_<ts>).
- Сторожа темы не ставил (запрещено).
