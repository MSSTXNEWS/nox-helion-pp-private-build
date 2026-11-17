# Новый Резонанс: узкий аудит native UI

## Готовый исходник

`owner_native_audit.py` — self-contained замена существующего `nox-control/owner_native_audit.py`. Автор не публиковал и не запускал её на сервере. SHA-256: `a0b476a87c1139771d3c1e75abaf3028bd4b5d51a6939a86fdf53b28d47affd1`.

Проверка offline: 10/10 PASS. Протокол и пределы — `SOURCE_RECEIPT.json`, точное происхождение 11 проверенных helpers — `HELPER_PROVENANCE.json`.

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
