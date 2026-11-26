# READY_MAP: самописное -> готовое (аудит ui_rm1, 2026-11-26)

Источник: ui_rm1 (список site/vendor, pkg/vendor, внешние скрипты каждой страницы). Лицензии: все кандидаты MIT/Apache-2.0 (проверить файл в vendor/licenses перед заменой).

Уже лежит в site/vendor (не нужно скачивать): fullcalendar, echarts, cytoscape, excalidraw, codemirror, d3, gridstack, kbar, cmdk, hls.js, howler, dashjs, dexie, fuse.js, konva, fabric, grapesjs, graphology, 3d-force-graph, frappe-gantt, jsonforms, driver.js, embla-carousel, gsap, katex, highlight.js, lightweight-charts, deep-chat, blocknote, drawio, foliate-js, ffmpeg. В pkg/vendor: shoelace, wavesurfer.js, swiper, split.js, lucide, tabler, lottie-web, three.
Ещё не вижу в vendor (список обрезан на "loquix", хвост проверю): tldraw, Schedule-X, Uppy, pdf.js, Tabulator, SortableJS, Notyf, ninja-keys, Plyr, Milkdown.

Общий вывод: ядро большинства страниц уже готовое (FullCalendar, ECharts, Cytoscape, Excalidraw, vidstack, filerobot, Leaflet). Самописное: ~28 общих скриптов nox-* на каждой странице (nox-ds, nox-cmd, nox-k*, nox-s4-*) и оболочки страниц (nox-p-*, nox-s2-*, nox-s4-*). Заменять нужно оболочки и виджеты, не ядра.

| Страница | Сейчас | Готовое (топ-3) | Решение |
|---|---|---|---|
| index | nox-home-*, nox-k7-cards, nox-k8-embla, 47 скриптов | Shoelace card/grid + embla (есть) + Tabler dashboard | P1: сетка карточек на sl-card, оставить embla; убрать дубли k5/k6/k7 |
| settings | nox-set-x, nox-settings-tabs, nox-k8-persona, nox-set-search | Shoelace (tab-group, switch, select, details) + jsonforms (есть) + Fuse (есть) | P1: sl-tab-group + sl-switch/sl-select, адаптер к /api/settings, ?legacy=1 |
| system | echarts + uPlot (готовое), nox-s4-grafana/glass/svc, k6-dash | ECharts (есть) + uPlot (есть) + gridstack (есть) | P1: gridstack для плиток, sl-card/sl-badge, графики оставить |
| board | Excalidraw+React (готовое), nox-s2-board | Excalidraw (есть) / tldraw / drawio (есть) | оставить Excalidraw, только адаптер сохранения; tldraw не нужен |
| calendar | FullCalendar (готовое), nox-s4-cal, k4-nl | FullCalendar (есть) / Schedule-X / assistant: vis-timeline | оставить FullCalendar, шапку и фильтры на sl-button-group; Schedule-X не нужен |
| music | nox-s2-music, k5-dj, k6-karaoke, swiper | wavesurfer (есть) + Plyr/howler (есть) + sl-range | P1: wavesurfer в плеер, howler уже есть; обложки swiper |
| memory | cytoscape (готовое) + fuse + split, nox-s4-memory | Cytoscape (есть) / graphology (есть) / 3d-force-graph (есть) | оставить; обвязку списка на sl-tree/sl-card |
| atlas | nox-atlas-s1, k4-fly, d3-celestial/globe-gl в vendor | globe-gl (есть) / d3-celestial (есть) / Cytoscape | заменить рендер на globe-gl; адаптер данных |
| downloads | nox-p-down + s4-downloads (самописное) | Uppy (нужно скачать) / sl-progress-bar+sl-card | P2: список на sl-card + sl-progress-bar; Uppy только для загрузки |
| pdf | nox-editor-s1, k6-slides (самописное) | pdf.js (нужно скачать) / foliate-js (есть) / blocknote (есть) | P2: pdf.js viewer + blocknote для заметок |
| knowledge | k6-mindmap (самописное), inline 2.7 КБ | Cytoscape (есть) / markmap / blocknote (есть) | P2: mindmap на Cytoscape, текст в blocknote |
| projects | fullcalendar+frappe-gantt+dexie (готовое), s4-projects | frappe-gantt (есть) + SortableJS (скачать) + sl-card | оставить; канбан на SortableJS |
| tasks/канбан | k6-board | SortableJS / jKanban | P2 |
| widgets | nox-p-widgets + leaflet | gridstack (есть) + sl-card | gridstack-сетка |
| map | Leaflet (готовое) | Leaflet / MapLibre GL | оставить |
| mail | nox-s4-lead, inline 2.7 КБ | Shoelace (split, tree, card) + Tabulator | P2 |
| cinema | vidstack (готовое), swiper | vidstack / Plyr / hls.js (есть) | оставить |
| news | nox-s2-news, k4-curate, swiper | sl-card + sl-tag + embla | P3 |
| photo | filerobot (готовое) | filerobot | оставить |
| voice | nox-voice-s1, k3-orb | wavesurfer (есть) + sl-button | P3 |
| training | echarts (есть), k8-anki | ECharts + sl-progress-ring | P3 |
| dispatcher | echarts, s4-grafana | ECharts + gridstack | P3 |
| tools / integrations | nox-tools, nox-p-integrations | Shoelace (card, switch, dialog) + jsonforms | P2 |
| studio / creative / writer | nox-studio, nox-k8-draw, studio-roles | CodeMirror (есть) / Milkdown / Excalidraw (есть) | writer: CodeMirror есть; blocknote как альтернатива |
| assistant | fullcalendar + vis-timeline + nox-assistant-s1 | Shoelace + deep-chat (есть) | P2, после чата |
| глобально | nox-cmd, nox-ninja (самописное ⌘K) | ninja-keys / cmdk / kbar (есть в vendor) | P1: заменить nox-cmd на kbar/cmdk, адаптер к командам |
| глобально | тосты/уведомления | Notyf / sl-alert toast (есть) | sl-alert toast, ничего не качать |

Очередь по Парето: index, settings, system, глобальный ⌘K, music, downloads, atlas/memory, calendar (шапка), board (адаптер). Схема каждой замены: новая основа на готовом, наше только адаптер к API, откат ?legacy=1, снимки 390/1920/2560, Lighthouse и axe, деплой -> ensure -> webroot_sync.

## Чек-лист «обещано -> есть/нет -> готовый движок» (v1, по сообщению владельца; ТЗ с Диска ещё не сверено построчно)

Статус: ЕСТЬ = подтверждено файлами vendor/сайта; ПРОВЕРИТЬ = не мерил; НЕТ = не найдено в аудите.

| Обещано | Статус | Готовый движок |
|---|---|---|
| Эталон главной V29.3 (красная туманность, лавовая планета, верхнее и нижнее меню) | ЕСТЬ, не менять | свой фон; виджеты gridstack слоем поверх |
| «Графит» как нейтральная база | ЕСТЬ (тема откатывается, см. ensure.sh) | --gx-* токены |
| 5 тем-миров HELION, CHRONOS, SOMNIUM, FORGE, SYNAPSE (свои фоны, кнопки, эффекты) | ПРОВЕРИТЬ (есть nox-worlds.js, nox-planets3d.js; ТЗ с Диска не читал) | three + tsparticles + GSAP + CSS-токены на мир |
| 6 цветов сцены | ПРОВЕРИТЬ | CSS-переменные + colorjs.io (есть) |
| 100 анимаций (MOTION100) | ЕСТЬ (animate.css, hover.css, magic.css, auto-animate, GSAP в vendor; nox-k5-motion100, nox-k6-motionlib) | подключено только на части страниц (в index и voice есть, в остальных нет) |
| Живые фоны и кнопки везде, без заглушек и выпадающих списков | НЕТ для 32 шаблонных страниц | tsparticles, lottie-web, Shoelace sl-button-group/sl-radio-group вместо select |
| HUD «Железный человек», Дюна, Харконнены | ПРОВЕРИТЬ (arwes-frames, arwes-animated, nox-hud-s1 есть) | arwes (есть), GSAP |
| 4K и мобильная версия | ЕСТЬ частично (nox-4k.css zoom; creative и ещё часть без него) | zoom-формулы, проверка 390/1920/2560 |
| Мини-чат NOX на каждой странице | ЕСТЬ (nox-minichat, nox-mini-s1); перевод на Deep Chat делает CH | deep-chat (есть) |
| Обучение: лента событий зелёный/жёлтый/красный, красные пушем со ссылкой | НЕТ/ПРОВЕРИТЬ | sl-alert toast + sl-badge; push через /api/nox/outbox |
| Предложения NOX: стеклянные карточки «применить/скачать/дистиллировать» | НЕТ | sl-card + sl-button |
| Графика: позитивный/негативный промпт с переключателем, ползунок режима, теги-команды | НЕТ/ПРОВЕРИТЬ (photo имеет 2 sl-textarea cIn/gP) | sl-switch, sl-range, sl-tag |
| Студии ролей: холст слева, инструменты снизу, узкий чат справа | ЕСТЬ для Writer; coder и designer soon | CodeMirror, Excalidraw |
| 10 полезных готовых функций | НЕТ списка | предложить: kbar ⌘K, Notyf/sl-alert, Fuse-поиск, driver.js-тур, sl-tree, dnd-kit, hotkeys, auto-animate, sl-dialog подтверждения, экспорт html-to-image |
| Быстрые команды маленькими аккуратными тегами | ПРОВЕРИТЬ (nox-k7-chips есть) | sl-tag |
| ⌘K | ЕСТЬ самописный (nox-cmd, nox-ninja) | kbar/cmdk (есть в vendor) |

Блокер: ТЗ веба на Диске (5 миров, 6 цветов, «МАКСИМАЛЬНАЯ ЗАГРУЗКА ГОТОВОГО», 125 репозиториев NOX WOW) подключить Google Drive коннектором в основной сессии и прочитать; без него строки про миры и цвета остаются «ПРОВЕРИТЬ».

## Интернет-кандидаты для заглушек (WebSearch 26.11; звёзды GitHub и демо НЕ проверены, поиск их не вернул)

| Страница | Интернет-кандидат 1 | 2 | 3 | Источник |
|---|---|---|---|---|
| calls | Jitsi Meet (Apache-2.0) | LiveKit (Apache-2.0, SFU + JS SDK) | MiroTalk SFU (AGPL, проверить лицензию) | https://webrtc.ventures/2026/06/open-source-webrtc-media-servers/ , https://selfhosting-sh.pages.dev/best/video-conferencing/ |
| messenger / social | Deep Chat (MIT, уже в vendor) | chatscope chat-ui-kit-react (MIT) | Element Web / matrix-react-sdk (Apache-2.0, тяжёлый) | https://github.com/Tantuss/chat-ui-kit-react , https://medevel.com/react-chat-ui/ |
| finance / money | Firefly III (AGPL, бэкенд PHP, не встроить) | Actual Budget (MIT) | ECharts + Tabulator как UI поверх своих данных | https://firefly-iii.org/ , https://openalternative.co/alternatives/actual |
| pc-control / pc-maintenance | Apache Guacamole (Apache-2.0, HTML5 клиент) | MeshCentral (Apache-2.0) | noVNC (MPL-2.0) | https://guacamole.apache.org/ , https://www.linuxlinks.com/meshcentral-web-based-remote-computer-management-platform/ |
| browser, games, social | не искал | | | следующий проход |

Оговорка: решение «брать интернет-движок вместо оригинала» требует проверки лицензии (AGPL/MPL), размера и демо; пока это только список кандидатов.
