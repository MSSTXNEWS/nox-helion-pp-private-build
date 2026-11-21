# QS6: блок «Мозг и чат» (шлюз :8082)

Файлы: `gateway.py` (HTTP), `qs6_core.py` (роутер, режимы, ETA, STOP, двухтактный стрим), `qs6_resume.py` («на чём остановились»), `test_qs6.py`.

## Запуск
```
NOX_UPSTREAM=http://127.0.0.1:8081 NOX_FAST_UPSTREAM=http://127.0.0.1:8083 python3 nox-control/glm53/gateway.py
python3 -m unittest nox-control/glm53/test_glm_profile.py
cd nox-control/glm53 && python3 -m unittest test_qs6
```

## Env
| переменная | по умолчанию | смысл |
|---|---|---|
| NOX_UPSTREAM | http://127.0.0.1:8081 | GLM llama-server |
| NOX_FAST_UPSTREAM | http://127.0.0.1:8083 | быстрый тир; `off` отключает |
| NOX_FAST_MODEL | fast | поле model для быстрого тира |
| NOX_LISTEN_HOST / PORT | 127.0.0.1 / 8082 | |
| NOX_ROUTER_JSON | | путь или inline JSON: fast_max_words(25), deep_min_words(120), deep_min_chars(1500), think_re |
| NOX_MODES_JSON | | переопределение режимов (tier, effort, max_tokens, expected_tokens, two_stage) |
| NOX_TWO_STAGE | 1 | 0 выключает двухтактный ответ |
| NOX_FAST_FIRST_SENTENCES / _MAX_TOKENS | 2 / 120 | длина первого такта |
| NOX_FAST_COOLDOWN_S | 20 | после сбоя быстрого тира он пропускается это время |
| NOX_DEFAULT_TPS_DEEP / _FAST | 1.5 / 40 | скорость, пока нет измерений |
| NOX_SESSION_SUMMARY | | путь к JSONL или SQLite со сводкой сессий |
| NOX_PING_S | 5 | keep-alive комментарий в SSE |

## API
- `POST /v1/chat/completions`, OpenAI-совместимо. Поля: `nox_mode`: fast | auto (по умолчанию) | deep | max; `stream`; `nox_no_route`; `nox_facts`.
- Режимы: fast = малая модель, 512 ток.; auto = роутер (простое -> fast, средние/«подумай»/рассуждения -> two_stage, код/длинное/инструменты -> только GLM); deep = быстрый такт + GLM effort high, 8192; max = быстрый такт + GLM effort max, 16384.
- Стрим: первое событие содержит `nox` (request_id, mode, tier, eta_s, eta_first_s, prefix). Каждая дельта текста несёт `delta.nox_stage` = fast | deep. Финальный чанк содержит `nox` (стадии, actual_s, cache, tps, dedup_sentences_dropped, stopped). Затем `data: [DONE]`.
- Заголовок `X-NOX-Request-Id`. `POST /v1/stop {"request_id": "..."}` закрывает сокеты к llama-server; то же при разрыве клиента (проверка и по записи, и по состоянию сокета раз в 0,5 с).
- `GET /v1/nox/stats`: скорости ток/с (скользящее среднее по последним 20 запросам на тир), кэш (tokens_cached, hit_ratio), активные запросы.
- Вопрос «на чём остановились?» при заданном NOX_SESSION_SUMMARY отвечается локально, без модели. JSONL: по строке `{ts, summary, open_items, next_step, last_user}`; SQLite: таблица `sessions` с теми же колонками.

## Сшивка
Быстрый такт останавливается после N предложений (и его соединение закрывается). GLM стартует параллельно и получает в хвост последней реплики просьбу не повторять вступление. Его ведущие предложения, совпавшие с быстрым тактом (точно или с похожестью >= 0,85), отбрасываются. Глубокий текст появляется только после конца быстрого. Размышления GLM (`reasoning_content`, `<think>`) в поток не попадают.

## Честные ограничения
- GLM ~1,5 ток/с: глубина придёт через минуты, первый такт мгновенный только если быстрый тир поднят.
- Быстрого тира в этом PR нет, нужен отдельный llama-server на :8083. Без него или при сбое честный пропуск (`nox.fast = skipped`), отвечает один GLM. Если GLM недоступен, после быстрой части в потоке приходит событие `error` и `finish_reason: "error"`.
- STOP закрывает сокет; отдельного API отмены задачи llama-server здесь нет. Остановка генерации опирается на то, что llama-server прекращает работу при разрыве соединения (его поведение по умолчанию).
- Повтор при нарушении стиля (G29/G30) работает только без стрима.
- ETA оценочная: ожидаемое число токенов задано по режиму/effort (включая размышления), скорость берётся из измерений процесса; после перезапуска измерения обнуляются.
- Дедупликация эвристическая (по предложениям); пересказ другими словами не ловится.
- `two_stage` при `stream=false` исполняется как один GLM (поле `nox.two_stage` это отмечает).
- Метрики кэша берутся из `timings` (cache_n/prompt_n) или `tokens_cached`; если сервер их не отдаёт, поля пусты.
- Тесты идут на поддельных upstream; на реальных llama-server не проверялось.
