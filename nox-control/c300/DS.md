# NOX DS (S3): общая дизайн-система

Файлы: `nox-ds.css`, `nox-ds.js` (подключаются на всех страницах; подстраховка: `nox-dock-pop.js` подключает их сам, если на странице их нет).

- Шрифты: 12/14/16/20/24/32 px (`--ds-fs-1..6`); подписи не мельче 12 px. Сетка 8 px (`--ds-s1..s4`), цель нажатия не меньше 44 px (`--ds-hit`).
- Shoelace в стекле: button, input, select, option, tab, badge, tooltip; состояния hover, active, focus-visible (контур 2 px), disabled, loading (`NOXds.busy(btn, promise)`).
- Компоненты: `.ds-empty` (пустое состояние), `NOXds.unavailable(el, причина)` + бейдж `.ds-badge-off` «недоступно» (один на все страницы), `.ds-skel` скелетон (`NOXds.skeleton(el, n)`).
- ECharts: тема `nox` регистрируется автоматически (`echarts.init(el, 'nox')`).
- Шапка и док: один ряд; в шапке 4+4 системных пункта, иконки-действия справа; на 1200-1700 px компактный режим без иконок в подписях; детали в nox-unify.css (S3-HDR, S3-HDR2) и nox-ds.css.
- Правило для страниц: данные не выводить сырым HTML (esc), пустое/ошибочное состояние через `NOXds.empty/unavailable`.

## Слои и безопасные зоны (S3)
- z-index: `--z-content 10`, `--z-float 800` (мини-чат, «?», крошка), `--z-dock 900`, `--z-header 950`, `--z-pult 1000`, `--z-sheet 1100`, `--z-toast 1200`.
- `--ds-dock-h` и `--ds-head-h` выставляет nox-ds.js по факту; main получает padding-bottom = высота дока + safe-area + 24 px; плавающие элементы (`#nxnavx`, `.nmc-fab`, `#nxmPill`) прижаты над доком (`bottom: dock + 12 px`).
- На мобильном все общие элементы (док, шапка, солнце, пульт, FAB) не меньше 44x44 px.
- Проверка: на 1440 и 390 на index, chat, photo, news, music, settings плавающие элементы не пересекают шапку и док.
