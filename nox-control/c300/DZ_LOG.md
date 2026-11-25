# DZ_LOG: дизайнер NOX HELION (site/creative.html)

- 25.11 Этап 1: DESIGN100.md (105 функций, у кого подсмотрено, модуль, передача в ИИ), PHOTOREAL100.md (113 настроек и анти-настроек). Топ-3 референса для раскладки: Figma, Photoshop web/Firefly, Krea + tldraw make-real.
- Бэкап: site/creative.html.bak_dz_1. creative.html переписан: убраны nox-s2.css, nox-s2-creative.js, nox-s6-sl.js (S6 отключён на этой странице). Новые: site/nox-dz-creative.js, site/nox-dz-creative.css. editor.html редиректит на creative.html.
- Движки: Fabric 7.4 (vendor/fabric), Shoelace (sl-* контролы), Sortable (слои, если есть vendor/sortablejs). Excalidraw/Filerobot не подключены: хватило Fabric.
- ИИ: POST /vision/describe {image, prompt} (Qwen3.6 :8104, до 500 токенов). Ответ SVG разбирается в отдельные слои с именами из id (house/roof, house/door), текст остаётся fabric.Textbox. /glm/v1/chat/completions закрыт веб-сервером (410), web_server.py не менялся.
- Маска (кисть/лассо): результат ИИ ограничивается clipPath из маски, оригинальные пиксели вне маски не затрагиваются (результат всегда новые слои поверх).
- Генератор /img/generate: проба POST раз в минуту; 503 korea_img_disabled даёт состояние «недоступно, включится после обучения». Рабочая проба с пустым prompt даёт 400, поэтому проба идёт с prompt (64x64, 1 шаг).
- QA на сервере (Playwright, /web/creative.html): 1440, 390, 3840: 0 ошибок JS, 0 мёртвых data-act, 0 целей меньше 44 px (sl-button, sl-icon-button, sl-select, sl-input, sl-switch, sl-color-picker, sl-tab).
- Тест «каракули -> ИИ»: рисунок домика (doodle-кисть, 4 штриха) -> /vision/describe -> 4-6 слоёв SVG: house/wall, house/roof, house/door, house/window-1, (window-2, chimney). 35-150 с на реальной модели.
- Инфраструктура: GitHub API rate limit (общий на всех исполнителей) задерживал запуск; run.sh опрашивает gh слишком часто.
