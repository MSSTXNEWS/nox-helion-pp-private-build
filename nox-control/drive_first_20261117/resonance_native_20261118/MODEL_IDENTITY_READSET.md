# Проверка происхождения имени и действующего backend NOX

Статус: **проверен исходный код; native identity audit ещё не выполнен**.

`model_identity_projection.py` — чистые функции для существующего owner audit.
Модуль не открывает файлы, не импортирует NOX, не выполняет запросы и не запускает
процессы. `MODEL_SOURCE_CONTRACT.json` закрепляет пять точных исходников,
совпавших с последними installed receipts. Копии исходников остаются приватным
входом, а не публикуемым deliverable.

## Что выяснено по точному коду

| Наблюдение | Реальное происхождение | Что оно подтверждает |
|---|---|---|
| `/api/nox/status.primary_model` | Bridge выбирает поле `model` из результата `nox_status`; тот читает `/root/nox/status/status.json` | Имя в дисковом снимке; само по себе не является ответом запущенной модели |
| `load_backend()` | `/root/nox/config/backend.json`, только `host`, `port`, `model`, `model_name`; defaults `127.0.0.1:8081` | Настроенный маршрут |
| Основная проверка готовности | `_nox_t153_port_ok` обращается к `127.0.0.1:<configured port>/health` | Штатный предикат HTTP readiness на момент проверки |
| Резерв | После основной ошибки проверяется `127.0.0.1:8085/health`; completion URL переключается на 8085 | Возможный fallback; результат кешируется на две секунды |
| Owner inference | Proxy передаёт URL в `agent_loop.owner_completion`; в конце модуля `owner_chat_stream.install(globals())` заменяет callback; `_model_events` стримит POST на тот же URL | Проверенную связь исходных функций; требуется связать её с фактическим процессом |
| Proxy `/v1/models` | Формируется из config `model_name` | Это синтетический список, поэтому он не используется как доказательство live backend |

Прошлый `safe_status` оставлял только ASCII-имя до 120 символов и отбрасывал
значения с `/root/`. Поэтому обычный путь GGUF способен превратиться в
`[WITHHELD_OR_UNAVAILABLE]`. Предыдущий audit не сохранил причину, длину и тип;
отсутствие модели из этого результата вывести нельзя. Новая проекция отдельно
показывает missing/null/object/string, длину, hash и причину старой маскировки.
Из корректного пути под `/root/nox/models/` выводится только имя файла.

## Следующая native проверка в существующем owner audit

1. Под действующим owner claim и maintenance lock проверить SHA пяти source
   files из `SOURCE_PINS`. Чтения должны быть bounded, с защитой от symlink и
   изменившегося inode/mtime. Не исполнять native Python modules.
2. Прочитать два фиксированных JSON-файла из `JSON_READSET`, отклоняя дубли
   ключей. Сохранить metadata чтения и время/возраст снимка; raw JSON не
   выводить. API status и disk snapshot считать разными наблюдениями.
3. Вызвать `status_projection` и `backend_probe_plan`. Вторая функция не
   допускает внешний host или некорректный port. Если completion host равен
   `localhost`, не подменять доказательство его разрешения одним health на
   `127.0.0.1`: это различие явно присутствует в результате.
4. Через уже существующий bounded loopback client выполнить один GET primary
   `/health`; fallback GET допускается только после определённого failure.
   Redirects, environment proxy, отправка модели и новые endpoints не нужны.
   `health_projection(..., truncated=True)` возвращает UNKNOWN.
5. Связать выбранный listening socket с фактическими PID/start_ticks/exe по
   существующему process readset и проверить неизменность identity до/после.
   Только для этого процесса передать bounded argv в `model_argv_projection`.
   Environment не читать; полный argv и credential flags не публиковать.
6. При необходимости связать model-аргумент с существующим file/mmap witness
   по той же process identity. Имя файла само по себе не доказывает содержимое
   весов, архитектуру, обученный контекст или чтение всех shards.

Проекция argv по умолчанию оставляет `listener_process_binding_verified=false`:
она проверяет формат уже переданных значений, а socket/PID witness должен
дать вызывающий audit. Она поглощает значения credential options, даже если
значение похоже на `--model=…`, и экспортирует только known-root GGUF reference.
Неопределённые значения полностью скрываются, включая hash и длину.

Полученный текущий read-only snapshot не восстанавливает model backend
прошлого completed canary. Новый model POST для этой проверки не нужен;
canary run44177251374 не повторяется.

## Проверки кода

Пять whole-source SHA совпали. Шесть исходных focused cases PASS; после
независимо найденного `--api-key`/`--model=` parsing случая добавлен один
regression с тремя подслучаями — PASS. Нативных вызовов этим модулем не было.
