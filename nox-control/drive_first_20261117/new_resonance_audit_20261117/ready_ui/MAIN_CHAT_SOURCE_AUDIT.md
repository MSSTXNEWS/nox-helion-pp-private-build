# Готовый новый Резонанс: точная проверка источника V13

## Результат

В готовом `site/chat.html` уже есть native-путь к существующему OneHost. Второй чатовый backend или PC bridge для этой страницы не требуется. Переключение выполняется только при `window.NOX_NATIVE_OWNER === true`, установленном **до исполнения** `workspace.js`, `nox-ui.js` и `nox-chat.js`. Флаг выбирает протокол; он не заменяет серверную авторизацию.

Исследован сохранённый пакет `NOX_HELION_WEB_WOW_MAX_V13_UNIFIED_20261117.zip`: 84 526 089 байт, SHA256 `f12a6f36e9718ee483e0d9d2e3f16aa41c3911ec9ef6e2bc03502a5da0d62fe4`. Это отдельная V13-ревизия, а не подтверждённая копия frozen WEB29 с SHA `611a3cf21b37ff79dbaece57f4c65c5efb70e0c302b5fc4b4f64dbfa060f15bc`. Доступная Drive-связь ответила 404 на frozen primary и оба его исходных ZIP. Причина 404 не установлена; удаление не заявляется.

Архивные release receipts прямо ограничивают V13 состоянием source-only, native OneHost HOLD. Вложенный V29 receipt помечает `nox-chat.js` неизменяемым; его SHA совпадает с фактическим файлом V13. Визуальные ревизии не являются новой версией chat engine.

## Точные исходники

Все следующие файлы извлечены без изменения байтов в `source_v13/site/`.

| Файл | Байты | SHA256 |
|---|---:|---|
| `chat.html` | 16422 | `99b909ea77df8384d5e64fbd59c86cf3a1ed7793227ea9db8879e1a21d75b118` |
| `nox-chat.js` | 66619 | `d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce` |
| `nox-ui.js` | 42684 | `c5f6b23d5fc6c31c4c388a574bfa8c61243cda6000cefb0026732ebe4183b765` |
| `workspace.js` | 6451 | `9b77c5011da892769c7332826c4b35bce581fb121960c13694638657735fc0ae` |
| `nox-connection-v13.js` | 3570 | `2bf36798d84f7ef103d2acaa411c8a57581c68568d2e9c3f619ce862efdf5390` |

`V13_SOURCE_MANIFEST.json` содержит все 21 прямые подключения script в HTML и 20 извлечённых файлов, включая основной HTML. Vendor-код в этот узкий аудит не включён. Четыре основных JS прошли `node --check`; это проверка синтаксиса, а не доказательство исполнения браузером или сервером.

## Существующий контракт main

| Область | Фактический источник |
|---|---|
| Основной адрес frozen канона | `/nox-web-v29/chat.html` |
| Native-навигация | `nox-ui.js` переписывает обычную ссылку `chat.html` в `/nox/chat`; этот alias требуется сопоставить с main |
| Готовность | GET `/api/nox/status`; `native_p02_bound === true`, `backend === 'EXISTING_NATIVE_ONEHOST'`, непустой `primary_model` |
| Отправка | POST `/api/nox/chat/stream`, `credentials: 'same-origin'` |
| Тело | `message`, `task: 'general'`, `history`, `dialog_id` при доступной persistent S03 |
| История контекста | До 24 элементов; каждый до 8000 символов; сообщение native также до 8000 |
| Выбор модели | В native-ветке модель и путь весов определяет сервер; браузер их не посылает |
| Поток | NDJSON, кадры `preparing`, `start`, `delta`, `done`, `error`; не SSE |
| S03 dialogs | `/api/ui/memory/dialogs/status`, `/create`, `/history`, список `/api/ui/memory/dialogs` |
| Готовность dialogs | `persistent_threads === true`, `status === 'READY'` |
| Terminal | Непустой ответ, `saved === true`, `s03_integrated === true`; при связанном диалоге строгое равенство `done.dialog_id` |
| STOP | Локальный AbortController и POST `/api/nox/stop` с `{}`; тот же POST при `pagehide` |
| Native cache | Старые browser/persona localStorage-диалоги не загружаются в fixed owner scope |
| Персона | UI-фасеты скрыты в native-ветке; source не выбирает другого владельца S03 |

Raw HTML не определяет `NOX_NATIVE_OWNER` и содержит баннер `PUBLIC PREVIEW · ЛОКАЛЬНЫЕ API ОТКЛЮЧЕНЫ`. Сам баннер ничего не блокирует: в проверенных прямых script-подключениях нет подмены `fetch`, отключающей API. Нельзя принимать текст баннера за серверный access gate или без проверки утверждать, что API отключены.

Без owner injection исполнится старый `/api/chat` протокол с browser tag `nox-helion:latest` и другой схемой readiness. Это не подтверждает реальное имя native-модели.

## STOP: исправление предварительного вывода

Путь `/api/nox/stop` и пустой body не доказывают глобальную отмену. Существующий canary `CANDIDATE_DECODED.py` проверяет, что nested `stream_stop` выбирает активное событие через `scope(request)`. Поэтому source-подозрение по надписи «STOP общий» должно быть сверено с текущим handler. Working cancel нельзя удалять и заменять выдуманным request-id endpoint. Независимый reviewer проверяет этот контракт отдельно.

## Что нужно сверить на сервере

1. SHA выданных main HTML и четырёх основных JS; HTML может отличаться только подтверждённой owner injection и существующими deploy преобразованиями.
2. Реальную owner injection до исполнения deferred scripts и соответствующий серверный auth gate.
3. Куда приводит существующий alias `/nox/chat`, чтобы переход из нового UI не вернул другой чат.
4. Текущий `stream_stop` и его cookie/session scope.
5. Фактические status-поля readiness и гарантии `done.dialog_id` / `exchange_id`. V13 требует `dialog_id`; canary допускает его отсутствие, но сверяет `exchange_id` с сохранённой парой. Это потенциальное несовпадение, пока не доказанный defect.
6. Один реальный ответ с terminal receipt и совпадающей сохранённой парой S03 после интеграции; этот аудит не выполнял model POST.

## Границы результата

Native-запросов и записей: 0. Основной UI не перерисован, новые маршруты/модель/второй backend не созданы. Original SHA не подменён. Пока нет подтверждённого нового frontend defect, source patch не применён. Файл `#chatModel` в native refresh показывает label `NOX HELION`, а не проверенное имя весов; проверку фактической модели и persona ведёт root.

Машинная квитанция: `MAIN_CHAT_SOURCE_AUDIT.json`. Отдельно сохранены архивные receipts и синтаксические результаты. Следующий независимый READY: сопоставить эти точные hashes и контракт с результатом native audit, затем править только доказанную точку wiring.
