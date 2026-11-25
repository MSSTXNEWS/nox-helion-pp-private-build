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
