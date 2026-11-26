# CH_HANDOVER: чат «Резонанс» на Deep Chat (передача UI)

## Что сделано (на сервере, синхронизировано в pkg/webroot)
- `chat.html` перенаправляет на `chat-dc.html` (скрипт `/*CH-DC*/`). Фолбэк: `?legacy=1` или `?dc=0`. Бэкап: `chat.html.bak_ch_dc`.
- Готовое: Deep Chat (`vendor/deep-chat`), Shoelace (`sl-card`, `sl-tree`, `sl-split-panel`), оригинал Liquid Glass V29.3 (`vendor/nox-liquid-glass` = kwlck/liquid-glass-web, фолбэк `mode:css` при ECO/слабом железе/reduced-transparency).
- Адаптер `nox-dc.js`: `/api/turn` (NDJSON: meta/delta/done/error), стоп через `/api/turn/stop`, история в `nox.wow.threads`/`nox.wow.cur`, `K8meta.handle`, `NOXNote.add`, вложения (Deep Chat `files` -> `/api/upload`, большие кусками), голос (`speechToText` ru-RU), режимы Авто/Быстро/Глубоко (`nox.wow.cfg.mode`), быстрые запросы в приветствии (`deep-chat-suggestion-button`), иконки действий под ответом с подсказками, цитата, ответ с превью (`↩`), Tab-черновик (серый ghost-текст поверх поля, `/api/chat` nox_mode fast, 30 токенов, диалог `qa-draft`), тост «NOX пишет первым» (`/api/nox/outbox`, `/seen`).
- `nox-dc-cols.js` (только >=1440 px): `sl-split-panel` x2 (перетаскиваемые, позиции в `nox.dc.spA/spB`); колонки: диалоги (дерево по проектам) | быстрые команды | чат | заготовки (по проекту, закрепляемые, `nox.dc.prompts`) | система (`/api/nox-live`).
- Мини-чат на всех страницах: `nox-minichat.js` = iframe `chat-dc.html?mini=1&ctx=...`; на мобильном кнопка принудительно показана (иначе её прячет `nox-m-mobile.css`).
- Шапка 56 px, стекло на шапке, подложке поля и 2 карточках.

## Проверено на сервере (Playwright, qa- диалоги)
- «как дела» отвечает на 390/1920/2560, первый текст 2.4-3.1 с; полный ответ 14-60 с: нагрузка сервера (load 28-31, GPU 91%), не UI.
- Tab-черновик работает (подсказка пришла, Tab принял). Мини-чат на 390 открывается по tap и отвечает.
- Стекло: renderer svg, шапка 56 px.
- Ответ с превью: в тесте кнопку находил по префиксу и попадал в «Ответить с цитатой»; повторный тест (`dcreply.py`, ch_dc27) запущен, результат смотреть в логе ch_dc27. Локально на моке работает.

## Оценки
- vision 8104 (`dcqa.py`): последний замер 1920: A7 R6 WOW5, 390: A8 R7 WOW6 (замечания: плотные панели, контраст, мелкие элементы, слабая иерархия). До WOW>=8 не дошли.
- Axe: остался 1 критичный `label` (узел не найден) + `region` x2 на 1920.
- Lighthouse: падал без CHROME_PATH; в ch_dc27 добавлен путь из `tools/ms-playwright`, результат в логе ch_dc27.

## Что осталось до WOW >= 8
1. Иерархия и воздух: шрифт ответа 16-19, отступы по 8-пт сетке (частично сделано), контраст текста (добавлен блок «v3» в `nox-dc.css`), меньше мелких элементов.
2. Решить про liquidGL (WebGL) против текущего оригинала V29.3; сейчас оригинал.
3. Найти критичный `label` из axe (скорее всего внутри shadow Deep Chat, `lab()` в `nox-dc.js` покрывает input/button/#text-input).
4. Проверить на сервере reply-to с превью и `nox:first`-тост на 390; убрать лишние перекрытия на 390.
5. Эмодзи от NOX (серверная персона), 5 колонок на 1920: подобрать плотность по vision, переснять 390/1920/2560.
6. После каждого деплоя: `ensure.sh force` (Графит слетает до 640 B после рестартов) и `webroot_sync.sh`.

## Файлы и скрипты
- Код: `nox-control/c300/bundles/ch_dc1/`: `chat-dc.html`, `nox-dc.js`, `nox-dc.css`, `nox-dc-cols.js`, `nox-minichat.js`; тесты: `pwdc.py`, `dcqa.py` (axe+vision, пишет в `/workspace/nox/agent/out/dcqa.out`), `dctest.py`, `dcreply.py`.
- Деплой-скрипты: `ch_dc1.sh` ... `ch_dc28.sh` (новое имя каждый раз; `ch_dc9/11/17/25/28` читают `dcqa.out`). Старый слой: `bundles/ch_ui1/` (nox-chat-clean, fix5.css), `ch_sw` (service worker), golden/верификация моделей.
- Деплой: `curl` файлов с raw GitHub в `/workspace/nox/web/site`, затем `th_graphite/webroot_sync.sh`. Тестовые диалоги только `qa-`/`cf:`. Локальное зеркало: `/home/claude/chmirror` + `chsrv2.py` (:8093, мок /api/turn).
