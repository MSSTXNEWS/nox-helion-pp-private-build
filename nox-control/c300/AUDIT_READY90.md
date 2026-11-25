# AUDIT_READY90: свой код против готовых движков (G, 25.11)

Источник: сервер /workspace/nox/web/site, чтение. Скрипты g_audit_1.sh, g_audit_2.sh. "Свой" = подключённые nox-*.js/css и inline, кроме общих канон-файлов (есть на >=50% страниц).
Объём vendor включает общий базис three+postprocessing+shoelace+swiper (~12,5 МБ на каждой странице), поэтому доля по байтам занижена: свой код везде <3% от vendor, и только это число обманчиво. Решающий критерий "по смыслу": своя вёрстка ключевого виджета.

| Страница | свой JS КБ | свой CSS КБ | vendor МБ | свои контролы / sl-* | готовые движки (без базиса) | Свыше 10% по смыслу | Чем заменить |
|---|---|---|---|---|---|---|---|
| about | 27 | 0 | 13 | 0 / 70 | echarts | ДА | шаблон «lead» (nox-s6-lead 27 КБ) -> Tremor-карточки + ECharts + Swiper |
| advisors | 3 | 2 | 12 | 1 / 0 | нет (только базис) | ЗАГЛУШКА | LibreChat/Open WebUI embed |
| ai-learning | 3 | 2 | 12 | 1 / 0 | нет (только базис) | ЗАГЛУШКА | ECharts + Grafana |
| assistant | 24 | 14 | 29 | 3 / 16 | нет (только базис) | ДА | assistant-ui + pdfjs + BlockNote |
| atlas | 36 | 16 | 93 | 7 / 27 | нет (только базис) | ДА | nullschool earth (vendor/earth) + d3-celestial + cobe + MapLibre; глобус с инерцией готовый |
| benchmark | 3 | 2 | 12 | 1 / 0 | нет (только базис) | ЗАГЛУШКА 2,7 КБ | ECharts + Open LLM Leaderboard-вид |
| board | 16 | 33 | 159 | 19 / 32 | drawio | ДА | draw.io/Excalidraw (стоят) вместо s2-board |
| book-reader | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | foliate-js (стоит) |
| browser | 3 | 2 | 12 | 1 / 0 | нет (только базис) | ЗАГЛУШКА 2,7 КБ | browser-use + noVNC/Chromium iframe |
| calendar | 20 | 6 | 20 | 13 / 8 | chrono-node | ДА | FullCalendar (стоит, используется на events) вместо s4-cal |
| calls | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | Jitsi/LiveKit components |
| chat | 157 | 43 | 103 | 75 / 46 | driver.js, html-to-image, nox-chat-ui, nox-liquid-glass, talkinghead | ДА | assistant-ui ThreadList/Thread + Vercel AI Elements (Suggestion=теги, Reasoning, Sources, Artifact) + Deep Chat; Telegram-tt как образец дерева слева; свой chat-x/tg/living/av свернуть до клея |
| cinema | 33 | 33 | 13 | 11 / 36 | vidstack | ДА | Vidstack (плеер) + Embla/Swiper (карусели) + шаблон Jellyfin-web/Plex-hero для карточек |
| consciousness | 34 | 9 | 24 | 2 / 2 | llm-viz, nox-brain, paper-design-shaders, tone | ЧАСТИЧНО | 5 страниц мозга (consciousness, soul, selffeel, growth, organism) делят один JS 34 КБ; 3d-force-graph/ECharts/llm-viz уже есть, разнести по данным, не по коду |
| constructor | 35 | 0 | 20 | 6 / 70 | echarts | ДА | GrapesJS/Gridstack вместо p-work (36 КБ) |
| contacts | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | Radicale/Baikal web + Tremor list |
| creative | 77 | 5 | 2 | 1 / 85 | fabric, sortablejs | ДА (78 КБ JS) | Fabric.js+Filerobot+Penpot-подход, Excalidraw; Sortable для слоёв |
| dispatcher | 21 | 4 | 20 | 1 / 6 | нет (только базис) | НЕТ | встроены сервисы (svc-embed), норм |
| downloads | 12 | 4 | 12 | 0 / 5 | нет (только базис) | НЕТ | встроенный сервис, норм |
| editor | 14 | 7 | 12 | 17 / 0 | нет (только базис) | ДА | BlockNote / CodeMirror 6 / Monaco |
| effects | 8 | 0 | 12 | 3 / 0 | нет (только базис) | ЧАСТИЧНО | Lil-gui/Tweakpane |
| events | 0 | 1 | 12 | 0 / 0 | fullcalendar | НЕТ | FullCalendar, своего кода почти нет (эталон) |
| finance | 26 | 13 | 14 | 0 / 26 | lightweight-charts | ДА | Lightweight-charts (стоит) + Tremor KPI + Ghostfolio/Firefly III UI как образец |
| games | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | Phaser/chessground/boardgame.io (стоят) |
| glance | 25 | 1 | 13 | 0 / 70 | echarts | ДА | Glance/Homepage-дашборд (шаблон) |
| growth | 37 | 8 | 24 | 2 / 5 | echarts, llm-viz, nox-brain | ЧАСТИЧНО | см. consciousness |
| index | 47 | 21 | 15 | 6 / 14 | gridstack, lightweight-charts, nox-liquid-glass, sortablejs | ДА (виджеты), оригинал не трогать | Gridstack+Sortable для сетки виджетов, Tremor/ECharts-карточки метрик; фон/шапка/низ главной V29.3 и эталона 22.11 не менять |
| install | 28 | 0 | 13 | 2 / 70 | echarts | ДА | Shoelace progress-bar + ECharts |
| integrations | 27 | 0 | 13 | 1 / 71 | echarts | ДА | Shoelace cards + Nango/Activepieces-вид |
| intents | 31 | 0 | 13 | 1 / 70 | echarts | ДА | React Flow/cytoscape |
| mail | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | SnappyMail/Roundcube embed |
| map | 15 | 3 | 20 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | MapLibre GL / earth |
| memory | 28 | 6 | 20 | 19 / 17 | cytoscape, split.js | ДА | 3d-force-graph/cosmos-gl + BlockNote + Split.js; свой список заменить |
| messenger | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | Telegram-tt / Element Web |
| models | 31 | 0 | 13 | 3 / 72 | echarts | ДА | Tremor-таблица + ECharts, шаблон Open WebUI Models |
| money | 23 | 12 | 14 | 0 / 25 | lightweight-charts | ДА | то же, что finance (дубль страницы: объединить) |
| music | 28 | 33 | 82 | 29 / 4 | lrc-kit, wavesurfer.js | ДА | Feishin (Navidrome-веб) как шаблон + wavesurfer.js + Butterchurn-визуализатор; убрать 34 КБ своего CSS |
| news | 27 | 35 | 81 | 3 / 11 | нет (только базис) | ДА | FreshRSS-тема/Miniflux + Masonry + Tremor-карточки; Readability для чтения |
| nexus | 15 | 3 | 12 | 3 / 3 | cytoscape | ШАБЛОН-ЗАГЛУШКА | cytoscape (стоит) / 3d-force-graph |
| notifications | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | ntfy-web / Novu inbox |
| organism | 35 | 9 | 103 | 2 / 2 | llm-viz, nox-brain, paper-design-shaders, tone | ЧАСТИЧНО | см. consciousness |
| pdf | 30 | 15 | 14 | 4 / 23 | нет (только базис) | ДА | PDF.js viewer (стоит) + BlockNote/CodeMirror |
| photo | 17 | 8 | 91 | 21 / 6 | нет (только базис) | ДА | Filerobot Image Editor (стоит) целиком + Fabric.js; свои панели убрать |
| projects | 27 | 4 | 100 | 31 / 14 | dexie | ДА | Frappe Gantt + SortableJS kanban + Dexie; 3 select убрать |
| scene | 15 | 5 | 12 | 7 / 0 | нет (только базис) | ЧАСТИЧНО | three.js + Tweakpane |
| selffeel | 34 | 9 | 24 | 2 / 2 | llm-viz, nox-brain, paper-design-shaders, tone | ЧАСТИЧНО | см. consciousness |
| settings | 60 | 10 | 13 | 28 / 83 | echarts | ДА | Shoelace sl-tab-group/sl-details/sl-switch целиком (settings-tabs/set-x заменить), планеты3d оставить как эталон |
| social | 15 | 3 | 12 | 3 / 3 | нет (только базис) | ШАБЛОН-ЗАГЛУШКА | Elk/Mastodon-web |
| soul | 34 | 9 | 24 | 2 / 2 | llm-viz, nox-brain, paper-design-shaders, tone | ЧАСТИЧНО | см. consciousness |
| studio | 15 | 33 | 17 | 16 / 0 | transformers-js | ДА | ComfyUI-frontend/litegraph или InvokeAI-UI как шаблон, Omniclip для видео, Excalidraw для доски |
| system | 25 | 5 | 21 | 3 / 11 | нет (только базис) | ДА | Grafana embed + uPlot/ECharts (стоят), Netdata/Glances-панель как шаблон |
| tools | 42 | 3 | 91 | 3 / 3 | нет (только базис) | ДА (43 КБ) | ninja-keys/cmdk + Gridstack-плитки |
| training | 50 | 10 | 23 | 5 / 8 | llm-viz, nox-brain | ДА (51 КБ) | ECharts + llm-viz + Grafana; логи — xterm.js |
| tv | 11 | 4 | 90 | 8 / 0 | нет (только базис) | ДА | Vidstack + dash.js/Shaka (стоят) + шаблон Jellyfin TV-layout |
| voice | 37 | 15 | 15 | 20 / 21 | wavesurfer.js | ДА | Deep Chat voice + wavesurfer.js + Pipecat-client-js; 1 select убрать |
| widgets | 30 | 0 | 21 | 3 / 71 | echarts | ДА | Gridstack (1 select убрать) |

Страниц проверено: 56; отмечено нарушений 90%: 53.

## Системные находки

- Шаблон nox-s4-lead.js (14,9 КБ) одинаков на 10 страницах (games, mail, map, nexus, social, calls, contacts, messenger, notifications, book-reader): 3 контрола, один и тот же код. Это заглушки по канону 7.1 ("каждая метка ведёт на реальный маршрут", "без мёртвых кнопок"). Ещё 4 страницы (benchmark, browser, ai-learning, advisors) ~2,7 КБ inline.
- Шаблон nox-s6-lead.js общий для about, constructor, install, integrations, intents, models, widgets, glance (25-36 КБ).
- Пять мозговых страниц (consciousness, soul, selffeel, growth, organism) подключают одинаковый набор 34 КБ.
- Видимые select (запрет владельца, канон 7.1): music 1, photo 2, projects 3, voice 1, widgets 1. Допустим только скрытый мост.
- Дубли: money и finance (один nox-fin-s1), assistant/pdf/editor делят nox-ai-s1/sl-s1/ds-s1.
- Движки vendor, ни разу не подключённые к страницам: arwes (FAIL: пусто в VENDOR_INDEX, HUD .nox-hud=0), cosmos-gl, assistant-ui как рантайм (только паттерны), butterchurn, cobe, embla, excalidraw, blocknote (нигде в списках used).
- nav.json: 35 пунктов, soon=0; вне меню 46 html (g01..g07, forge, ops, weights, resonance, planets и др.), на них аудит ограничен выборкой.

Примечание: колонка "Свыше 10% по смыслу" и "Чем заменить" выставлены по ревизорским вердиктам qa/audit.json и составу файлов (судейская оценка, не автоматический порог). Автоматически измерены только размеры, контролы и список движков.
