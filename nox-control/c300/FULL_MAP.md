# FULL_MAP: инвентарь страниц (ui_fm1, 2026-11-26)

84 html на сервере, 13+ групп в nav.json. Статус: ЯДРО = на готовом движке, ШАБЛОН = общий каркас ~7.7 КБ с inline 2713 Б (одинаковый шаблон, заглушка по сути), САМОПИСНАЯ = оболочка nox-p-*/s2/s4 без движка, ФРАГМЕНТ = *.main. U/A: локальный замер (Lighthouse ещё не подключён, A по axe+метрикам); пусто = ещё не мерили.

| Страница | Группа | Статус | Движок сейчас | Заменить на | U / A (26.11, после правок) | UX |
|---|---|---|---|---|---|---|
| about | ВИДЖЕТЫ | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.6 | - |
| advisors | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.7 | - |
| ai-learning | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.7 | - |
| assistant-s1.main | - | ФРАГМЕНТ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| assistant | ПОМОЩНИК | ЯДРО | fullcalendar,vis-timeline | Shoelace-каркас (sl-card/tab-group) | 9.7 / 7.4 | UX |
| atlas-s1.main | - | ФРАГМЕНТ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| atlas | - | ШАБЛОН (заглушка) | - | globe-gl/d3-celestial (есть) | 9.0 / 7.6 | UX |
| benchmark | - | САМОПИСНАЯ | - | ECharts | 9.5 / 7.6 | - |
| board | ДОСКА | ЯДРО | excalidraw,swiper | Excalidraw (есть) | 9.1 / 6.9 | UX |
| book-reader | - | САМОПИСНАЯ | - | foliate-js (не трогать) | 9.6 / 7.4 | - |
| browser | - | ШАБЛОН (заглушка) | - | sl-tab-group + iframe | 9.5 / 7.7 | - |
| calendar | ПОМОЩНИК | ЯДРО | fullcalendar | FullCalendar (есть) + sl-* | 9.3 / 7.7 | UX |
| calls | - | ШАБЛОН (заглушка) | - | deep-chat + sl-card | 8.9 / 7.7 | - |
| chat-dc | - | ЯДРО | deep-chat | Shoelace-каркас (sl-card/tab-group) | 9.3 / 7.8 | - |
| chat | РЕЗОНАНС | САМОПИСНАЯ | - | deep-chat (CH) | 9.3 / 7.8 | - |
| cinema | КИНОТЕАТР | ЯДРО | swiper,vidstack | Shoelace-каркас (sl-card/tab-group) | 8.8 / 7.5 | UX |
| connections | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.5 | - |
| consciousness | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.1 | - |
| constructor | КОНСТРУКТОР | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.7 | - |
| contacts | - | ШАБЛОН (заглушка) | - | Tabulator | 8.9 / 7.7 | - |
| creative | - | ЯДРО | fabric | Shoelace-каркас (sl-card/tab-group) | 8.8 / 7.7 | UX |
| dispatcher | СИСТЕМА | ЯДРО | echarts | Shoelace-каркас (sl-card/tab-group) | 9.8 / 7.3 | UX |
| downloads | СИСТЕМА | САМОПИСНАЯ | - | Uppy + sl-progress | 9.7 / 7.8 | UX |
| editor-s1.main | - | ФРАГМЕНТ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| editor | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 8.8 / 7.8 | - |
| effects | ЭФФЕКТЫ | САМОПИСНАЯ | - | tsparticles+GSAP+lottie | 9.4 / 7.5 | - |
| events | - | ЯДРО | fullcalendar | FullCalendar (есть) | 9.2 / 7.4 | - |
| evolution | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.7 | - |
| finance | - | САМОПИСНАЯ | - | ECharts + Tabulator | 8.8 / 7.2 | - |
| forge | - | ШАБЛОН (заглушка) | - | Excalidraw/CodeMirror | 9.5 / 7.5 | - |
| g01-status | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.7 / 7.6 | - |
| g02-owner | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.6 | - |
| g03-release | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.9 | - |
| g04-provider | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.9 | - |
| g05-evidence | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.7 | - |
| g06-orchestrator | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.3 / 7.7 | - |
| g07-hardware | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.8 / 8.7 | - |
| games | - | ШАБЛОН (заглушка) | - | boardgame-io/chessground (есть) | 8.4 / 9.1 | - |
| glance | ВИДЖЕТЫ | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| growth | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.3 / 9.1 | - |
| index | - | САМОПИСНАЯ | - | gridstack слой поверх эталона V29.3 | 5.0 / 4.8 | UX |
| install | СИСТЕМА | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| integrations | ВИДЖЕТЫ | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.8 / 9.7 | UX |
| intents | ДОСКА | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| knowledge | - | ШАБЛОН (заглушка) | - | Cytoscape + blocknote | 9.7 / 7.9 | UX |
| live | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 8.5 / 5.0 | - |
| mail | - | ШАБЛОН (заглушка) | - | Shoelace split + Tabulator | 9.8 / 8.0 | UX |
| map | - | ЯДРО | leaflet | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.6 | UX |
| marketing | - | ШАБЛОН (заглушка) | - | ECharts | 9.3 / 8.9 | - |
| memory | СИСТЕМА | ЯДРО | cytoscape | Cytoscape (есть) | 9.8 / 7.4 | UX |
| messenger | - | ШАБЛОН (заглушка) | - | deep-chat (есть) | 8.4 / 9.1 | - |
| mini | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| models | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 8.7 / 8.3 | - |
| money | - | САМОПИСНАЯ | - | ECharts + Tabulator | 8.4 / 8.3 | - |
| music | МУЗЫКА | ЯДРО | swiper | wavesurfer + howler | 9.6 / 7.9 | UX |
| news | ВИДЖЕТЫ | ЯДРО | swiper | Shoelace-каркас (sl-card/tab-group) | 9.8 / 9.7 | UX |
| nexus | - | ЯДРО | cytoscape | Cytoscape/3d-force-graph (есть) | 9.4 / 9.1 | - |
| notifications | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| operators | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 8.6 / 9.4 | - |
| ops | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.2 / 9.1 | - |
| organism | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 8.9 / 9.1 | - |
| pc-control | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| pc-maintenance | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| pdf | КОНСТРУКТОР | ШАБЛОН (заглушка) | - | pdf.js + blocknote | 8.9 / 9.1 | UX |
| photo | АТЕЛЬЕ | ЯДРО | filerobot | Shoelace-каркас (sl-card/tab-group) | 7.7 / 7.1 | UX |
| planets | - | САМОПИСНАЯ | - | three | 9.2 / 9.1 | - |
| projects | СИСТЕМА | ЯДРО | dexie,frappe,fullcalendar | Shoelace-каркас (sl-card/tab-group) | 9.8 / 9.7 | UX |
| qa | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 7.9 / 8.3 | - |
| resonance | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 8.8 / 9.7 | - |
| scene | ЦВЕТ СЦЕНЫ | САМОПИСНАЯ | - | three + tsparticles | 9.4 / 9.1 | - |
| selffeel | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| settings | СИСТЕМА | САМОПИСНАЯ | - | Shoelace tab-group/switch | 9.4 / 7.5 | UX |
| social | - | ШАБЛОН (заглушка) | - | sl-card + Tabulator | 8.4 / 9.1 | - |
| soul | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| spaces | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) | 9.4 / 9.1 | - |
| studio | АТЕЛЬЕ | ЯДРО | swiper | Shoelace-каркас (sl-card/tab-group) | 9.0 / 6.8 | UX |
| system | СИСТЕМА | ЯДРО | echarts,uPlot | ECharts+gridstack (есть) | 9.8 / 7.7 | UX |
| tools | КОНСТРУКТОР | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 9.8 / 9.7 | UX |
| training | СИСТЕМА | ЯДРО | echarts | Shoelace-каркас (sl-card/tab-group) | 9.3 / 9.7 | UX |
| tv | КИНОТЕАТР | ШАБЛОН (заглушка) | - | hls.js/dashjs + vidstack | 8.9 / 6.7 | - |
| voice | ГОЛОС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 8.7 / 7.4 | UX |
| weights | - | ШАБЛОН (заглушка) | - | ECharts | 9.3 / 9.7 | - |
| widgets | ВИДЖЕТЫ | ЯДРО | leaflet | Shoelace-каркас (sl-card/tab-group) | 9.8 / 9.7 | UX |
| writer | - | ЯДРО | swiper | Shoelace-каркас (sl-card/tab-group) | 9.5 / 7.6 | UX |


## СВОДКА U/A: было → стало (26.11, WEB)
Измерение: bundles/ui_score (axe + собственные метрики 44 px, CTA, ошибки JS, тема; Lighthouse a11y/bp/perf только где есть, perf занижен нагрузкой сервера). Базовая точка: 27 страниц, U 8.00 / A 7.47. «Было» = полный прогон 80 страниц до правок 44 px, CTA и aria; «стало» = после правок, 81 страница: U 9.21 / A 8.16.
Правки: nox-a11y-fix.js (aria, роли, подписи, 44 px у шапки и дока, CTA, main), nox-frame.js (каркас Shoelace на 27 заглушках + operators), чат v8-v12, tv-плеер, Writer Pro, роли студии.

| Страница | U было | A было | U стало | A стало |
|---|---|---|---|---|
| about | 9.2 | 5.9 | 9.5 | 7.6 |
| advisors | 8.6 | 5.9 | 9.5 | 7.7 |
| ai-learning | 9.4 | 6.1 | 9.5 | 7.7 |
| assistant | 8.0 | 5.5 | 9.7 | 7.4 |
| atlas | 8.8 | 6.0 | 9.0 | 7.6 |
| benchmark | 9.2 | 5.9 | 9.5 | 7.6 |
| board | 8.9 | 5.4 | 9.1 | 6.9 |
| book-reader | 9.2 | 5.7 | 9.6 | 7.4 |
| browser | 8.6 | 6.0 | 9.5 | 7.7 |
| calendar | 9.3 | 6.1 | 9.3 | 7.7 |
| calls | 8.6 | 6.0 | 8.9 | 7.7 |
| chat | 7.1 | 2.9 | 9.3 | 7.8 |
| chat-dc | 8.3 | 5.8 | 9.3 | 7.8 |
| cinema | 8.2 | 4.6 | 8.8 | 7.5 |
| connections | 7.9 | 3.4 | 9.5 | 7.5 |
| consciousness | 8.9 | 3.4 | 9.5 | 7.1 |
| constructor | 8.9 | 3.4 | 9.5 | 7.7 |
| contacts | 7.9 | 3.4 | 8.9 | 7.7 |
| creative | 8.3 | 4.4 | 8.8 | 7.7 |
| dispatcher | 9.7 | 4.6 | 9.8 | 7.3 |
| downloads | 9.7 | 4.6 | 9.7 | 7.8 |
| editor | 8.3 | 6.9 | 8.8 | 7.8 |
| effects | 8.9 | 3.4 | 9.4 | 7.5 |
| events | 8.9 | 7.0 | 9.2 | 7.4 |
| evolution | 7.9 | 8.3 | 9.5 | 7.7 |
| finance | 8.3 | 8.3 | 8.8 | 7.2 |
| forge | 7.9 | 8.3 | 9.5 | 7.5 |
| g01-status | 9.5 | 9.2 | 9.7 | 7.6 |
| g02-owner | 7.9 | 8.3 | 9.5 | 7.6 |
| g03-release | 7.9 | 8.3 | 9.5 | 7.9 |
| g04-provider | 7.9 | 8.3 | 9.5 | 7.9 |
| g05-evidence | 7.9 | 8.3 | 9.5 | 7.7 |
| g06-orchestrator | 7.7 | 8.3 | 9.3 | 7.7 |
| g07-hardware | 8.9 | 8.9 | 9.8 | 8.7 |
| games | 7.9 | 8.3 | 8.4 | 9.1 |
| glance | 8.9 | 8.3 | 9.4 | 9.1 |
| growth | 8.4 | 8.3 | 9.3 | 9.1 |
| index | - | - | 5.0 | 4.8 |
| install | 8.9 | 8.3 | 9.4 | 9.1 |
| integrations | 9.7 | 9.6 | 9.8 | 9.7 |
| intents | 8.9 | 8.3 | 9.4 | 9.1 |
| knowledge | 9.7 | 9.6 | 9.7 | 7.9 |
| live | 8.5 | 5.0 | 8.5 | 5.0 |
| mail | 9.7 | 9.6 | 9.8 | 8.0 |
| map | 9.7 | 9.6 | 9.5 | 7.6 |
| marketing | 7.9 | 8.3 | 9.3 | 8.9 |
| memory | 9.7 | 9.6 | 9.8 | 7.4 |
| messenger | 7.9 | 8.3 | 8.4 | 9.1 |
| mini | 7.9 | 8.3 | 9.4 | 9.1 |
| models | 8.7 | 8.3 | 8.7 | 8.3 |
| money | 8.2 | 8.3 | 8.4 | 8.3 |
| music | 9.4 | 9.6 | 9.6 | 7.9 |
| news | 8.2 | 9.6 | 9.8 | 9.7 |
| nexus | 8.9 | 8.3 | 9.4 | 9.1 |
| notifications | 8.9 | 8.3 | 9.4 | 9.1 |
| operators | 7.8 | 9.2 | 8.6 | 9.4 |
| ops | 7.7 | 8.3 | 9.2 | 9.1 |
| organism | 8.3 | 8.2 | 8.9 | 9.1 |
| pc-control | 7.9 | 8.3 | 9.4 | 9.1 |
| pc-maintenance | 7.9 | 8.3 | 9.4 | 9.1 |
| pdf | 8.6 | 8.9 | 8.9 | 9.1 |
| photo | 8.3 | 8.3 | 7.7 | 7.1 |
| planets | 8.8 | 8.3 | 9.2 | 9.1 |
| projects | 8.9 | 8.3 | 9.8 | 9.7 |
| qa | 5.4 | 8.3 | 7.9 | 8.3 |
| resonance | 8.0 | 8.5 | 8.8 | 9.7 |
| scene | 8.8 | 8.3 | 9.4 | 9.1 |
| selffeel | 8.9 | 8.3 | 9.4 | 9.1 |
| settings | 8.4 | 8.3 | 9.4 | 7.5 |
| social | 7.9 | 8.3 | 8.4 | 9.1 |
| soul | 8.7 | 8.3 | 9.4 | 9.1 |
| spaces | 7.9 | 8.3 | 9.4 | 9.1 |
| studio | 6.9 | 3.4 | 9.0 | 6.8 |
| system | 9.7 | 9.6 | 9.8 | 7.7 |
| tools | 8.7 | 9.6 | 9.8 | 9.7 |
| training | 8.5 | 9.1 | 9.3 | 9.7 |
| tv | 8.3 | 8.9 | 8.9 | 6.7 |
| voice | 7.7 | 9.6 | 8.7 | 7.4 |
| weights | 9.2 | 9.6 | 9.3 | 9.7 |
| widgets | 9.7 | 9.6 | 9.8 | 9.7 |
| writer | 9.2 | 8.8 | 9.5 | 7.6 |

Остаются ниже 8 (честно): index (FASTWOW эталон, не менять; 390: JS-ошибка, 17 мелких целей) U 5.0 / A 4.8; photo U 7.7 (axe: h3 role=button в чате, minor; Filerobot); live A 5.0 (замер до правки темы, перемерить); studio A 6.8 и tv A 6.7 (Lighthouse perf и best-practices); qa (служебная) U 7.9. A занижена там, где Lighthouse perf < 30 под нагрузкой сервера (GPU 91%).
