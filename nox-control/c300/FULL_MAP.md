# FULL_MAP: инвентарь страниц (ui_fm1, 2026-11-26)

84 html на сервере, 13+ групп в nav.json. Статус: ЯДРО = на готовом движке, ШАБЛОН = общий каркас ~7.7 КБ с inline 2713 Б (одинаковый шаблон, заглушка по сути), САМОПИСНАЯ = оболочка nox-p-*/s2/s4 без движка, ФРАГМЕНТ = *.main. U/A: локальный замер (Lighthouse ещё не подключён, A по axe+метрикам); пусто = ещё не мерили.

| Страница | Группа | Статус | Движок сейчас | Заменить на | U | UX |
|---|---|---|---|---|---|---|
| about | ВИДЖЕТЫ | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| advisors | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| ai-learning | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| assistant-s1.main | - | ФРАГМЕНТ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| assistant | ПОМОЩНИК | ЯДРО | fullcalendar,vis-timeline | Shoelace-каркас (sl-card/tab-group) | 6.8 | UX |
| atlas-s1.main | - | ФРАГМЕНТ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| atlas | - | ШАБЛОН (заглушка) | - | globe-gl/d3-celestial (есть) | 7.4 | UX |
| benchmark | - | САМОПИСНАЯ | - | ECharts |  | - |
| board | ДОСКА | ЯДРО | excalidraw,swiper | Excalidraw (есть) | 6.5 | UX |
| book-reader | - | САМОПИСНАЯ | - | foliate-js (не трогать) |  | - |
| browser | - | ШАБЛОН (заглушка) | - | sl-tab-group + iframe |  | - |
| calendar | ПОМОЩНИК | ЯДРО | fullcalendar | FullCalendar (есть) + sl-* | 5.4 | UX |
| calls | - | ШАБЛОН (заглушка) | - | deep-chat + sl-card |  | - |
| chat-dc | - | ЯДРО | deep-chat | Shoelace-каркас (sl-card/tab-group) |  | - |
| chat | РЕЗОНАНС | САМОПИСНАЯ | - | deep-chat (CH) |  | - |
| cinema | КИНОТЕАТР | ЯДРО | swiper,vidstack | Shoelace-каркас (sl-card/tab-group) | 7.0 | UX |
| connections | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| consciousness | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| constructor | КОНСТРУКТОР | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| contacts | - | ШАБЛОН (заглушка) | - | Tabulator |  | - |
| creative | - | ЯДРО | fabric | Shoelace-каркас (sl-card/tab-group) | 6.0 | UX |
| dispatcher | СИСТЕМА | ЯДРО | echarts | Shoelace-каркас (sl-card/tab-group) | 8.1 | UX |
| downloads | СИСТЕМА | САМОПИСНАЯ | - | Uppy + sl-progress | 8.3 | UX |
| editor-s1.main | - | ФРАГМЕНТ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| editor | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| effects | ЭФФЕКТЫ | САМОПИСНАЯ | - | tsparticles+GSAP+lottie |  | - |
| events | - | ЯДРО | fullcalendar | FullCalendar (есть) |  | - |
| evolution | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| finance | - | САМОПИСНАЯ | - | ECharts + Tabulator |  | - |
| forge | - | ШАБЛОН (заглушка) | - | Excalidraw/CodeMirror |  | - |
| g01-status | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| g02-owner | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| g03-release | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| g04-provider | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| g05-evidence | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| g06-orchestrator | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| g07-hardware | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| games | - | ШАБЛОН (заглушка) | - | boardgame-io/chessground (есть) |  | - |
| glance | ВИДЖЕТЫ | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| growth | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| index | - | САМОПИСНАЯ | - | gridstack слой поверх эталона V29.3 | 7.4 | UX |
| install | СИСТЕМА | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| integrations | ВИДЖЕТЫ | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 7.8 | UX |
| intents | ДОСКА | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| knowledge | - | ШАБЛОН (заглушка) | - | Cytoscape + blocknote | 8.3 | UX |
| live | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| mail | - | ШАБЛОН (заглушка) | - | Shoelace split + Tabulator | 7.0 | UX |
| map | - | ЯДРО | leaflet | Shoelace-каркас (sl-card/tab-group) | 7.0 | UX |
| marketing | - | ШАБЛОН (заглушка) | - | ECharts |  | - |
| memory | СИСТЕМА | ЯДРО | cytoscape | Cytoscape (есть) | 7.8 | UX |
| messenger | - | ШАБЛОН (заглушка) | - | deep-chat (есть) |  | - |
| mini | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| models | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| money | - | САМОПИСНАЯ | - | ECharts + Tabulator |  | - |
| music | МУЗЫКА | ЯДРО | swiper | wavesurfer + howler | 6.1 | UX |
| news | ВИДЖЕТЫ | ЯДРО | swiper | Shoelace-каркас (sl-card/tab-group) | 7.0 | UX |
| nexus | - | ЯДРО | cytoscape | Cytoscape/3d-force-graph (есть) |  | - |
| notifications | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| operators | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| ops | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| organism | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| pc-control | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| pc-maintenance | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| pdf | КОНСТРУКТОР | ШАБЛОН (заглушка) | - | pdf.js + blocknote | 6.7 | UX |
| photo | АТЕЛЬЕ | ЯДРО | filerobot | Shoelace-каркас (sl-card/tab-group) | 4.9 | UX |
| planets | - | САМОПИСНАЯ | - | three |  | - |
| projects | СИСТЕМА | ЯДРО | dexie,frappe,fullcalendar | Shoelace-каркас (sl-card/tab-group) | 8.3 | UX |
| qa | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| resonance | - | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| scene | ЦВЕТ СЦЕНЫ | САМОПИСНАЯ | - | three + tsparticles |  | - |
| selffeel | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| settings | СИСТЕМА | САМОПИСНАЯ | - | Shoelace tab-group/switch | 5.8 | UX |
| social | - | ШАБЛОН (заглушка) | - | sl-card + Tabulator |  | - |
| soul | РЕЗОНАНС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| spaces | - | ШАБЛОН (заглушка) | - | Shoelace-каркас (sl-card/tab-group) |  | - |
| studio | АТЕЛЬЕ | ЯДРО | swiper | Shoelace-каркас (sl-card/tab-group) | 7.3 | UX |
| system | СИСТЕМА | ЯДРО | echarts,uPlot | ECharts+gridstack (есть) | 8.3 | UX |
| tools | КОНСТРУКТОР | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 7.3 | UX |
| training | СИСТЕМА | ЯДРО | echarts | Shoelace-каркас (sl-card/tab-group) | 6.8 | UX |
| tv | КИНОТЕАТР | ШАБЛОН (заглушка) | - | hls.js/dashjs + vidstack |  | - |
| voice | ГОЛОС | САМОПИСНАЯ | - | Shoelace-каркас (sl-card/tab-group) | 5.8 | UX |
| weights | - | ШАБЛОН (заглушка) | - | ECharts |  | - |
| widgets | ВИДЖЕТЫ | ЯДРО | leaflet | Shoelace-каркас (sl-card/tab-group) | 7.8 | UX |
| writer | - | ЯДРО | swiper | Shoelace-каркас (sl-card/tab-group) | 7.9 | UX |
