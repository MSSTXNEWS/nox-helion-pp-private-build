# Новый Резонанс: узкий аудит native UI

## Готовый исходник

`owner_native_audit.py` — self-contained исходник существующего `nox-control/owner_native_audit.py`. Текущий SHA-256 после переноса двух native source pins: `4e22e0fd73f46c759d9663b9a6be58d0cb48a9c3fce636d2ee1b6e18821c8b6a`. Исходник и единственный native dispatch публикует/выполняет root; автор не делает native вызовов.

Первоначальный SHA `a0b476a87c1139771d3c1e75abaf3028bd4b5d51a6939a86fdf53b28d47affd1` прошёл 10/10 offline checks и независимый review. Исторический `SOURCE_RECEIPT.json` сохранён без изменения; перенос pins описан отдельно в `PIN_REBASE_RECEIPT.json`. Точное происхождение 11 проверенных helpers — `HELPER_PROVENANCE.json`.

## Почему обновлены два pins

O1 install из source commit `be4750aae3cb456e09df0ddcb39fcf0fd1673bd1`, run `44171616874`, job `134351926185`, установил четыре source файла и выполнил reload. Сохранённая postimage-квитанция имеет состояние `APPLIED_RELOADED_USE_PENDING`; она не заявляет model USED/ACCEPTED.

После этого первый root audit, run `44171929567`, job `134353031742`, остановился на `HOLD_PROXY_SHA_CHANGED` за 1 ms: HTTP/loopback requests=0, bytes=0, model requests=0. Cleanup: `DETACHED_AND_VERIFIED`. Проверка авторизации и UI ещё не выполнялась; этот результат подтверждает source drift после известной установки, а не дефект login/parser.

Root заменил только `PROXY_SHA` и `BRIDGE_SHA` на exact postimages O1. `WRAPPER_SHA`, auth resolver, lease, маршруты, deadline и поведение аудита сохранены. Обратная замена этих двух строк в памяти восстанавливает первоначальный SHA. Полный test suite повторно не запускался ради изменения constants. Независимый review этой дельты — PASS (`independent_review/PIN_REBIND_REVIEW.json`). Следующий единственный audit dispatch остаётся у root.

## Что делает один разрешённый запуск

1. Проверяет source/request binding, прежние native source pins, существующий maintenance lease. Разрешает пароль статическим AST resolver и читает root-owned regular file без перехода по symlink.
2. Входит через существующий `/chat/login`; cookie остаётся только в памяти.
3. Читает `/nox-web-v29/chat.html`, до 24 непосредственно подключённых локальных JS, затем известный alias `/nox/chat`. `/api/nox/status` читает только после наблюдения точного literal в UI исходнике.
4. Выводит HTTP status, bounded body hashes, безопасный title/DOM-ID projection, подключённые script paths и их порядок, статические API routes, наличие `sendNative` и owner flag. Возвращает только поля статуса `native_p02_bound`, `backend`, `primary_model`.
5. При позднем timeout/ошибке сохраняет уже прочитанные безопасные метаданные, выставляет HOLD и `NOX_MAINT_AUDIT_COMPLETE=false`. Пароли, cookie, исходные bodies, private state и raw exception messages не печатает.

`owner_flag_before_critical_scripts` — консервативное свидетельство порядка статических script tags: оно не доказывает исполнение условного JavaScript. `owner_flag_activation_verified` всегда false; это проверяется отдельным разрешённым runtime gate.

## Пределы и смысл результата

Origin фиксирован: `http://127.0.0.1:18775`. Общий deadline 90 секунд, body 256 KiB, суммарно 6 MiB; redirects запрещены. Model API, create/stop диалога, reload и native mutations отсутствуют. Alias — подтверждённый существующий маршрут V13, его получение не выдаётся за literal discovery.

`UI_AUDIT_COMPLETE*` означает завершённый диагностический обход, а не готовность модели или публичного туннеля. При pins drift, недоступности страницы или неполной выборке сохраняются ограничения результата. Исходники CSS и транзитивные module imports не обходятся.

## Следующий владелец

Root публикует только этот frozen source после независимого review, затем использует уже существующий owner workflow. Новый workflow, оператор, расписание или backend не требуются. Результат native audit принимает назначенный независимый reviewer относительно V13 source manifest.
