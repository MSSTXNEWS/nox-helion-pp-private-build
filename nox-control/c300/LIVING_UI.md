# LIVING_UI: кнопки и UI для дизайнера чата S1 (исполнитель L)
Логику (команды, правила) делает L. Здесь только то, что нужно сверстать. Все функции работают и без кнопок через чат-команды.

| Страница | Элемент | Что делает | Команда / эндпоинт |
|---|---|---|---|
| chat | чип «Запомнить» у ответа | сохраняет факт из ответа в память | чат-команда /запомни <текст> (правило в living/rules.md; API памяти в разработке) |
| chat | кнопка «Что ты помнишь» | показывает список фактов | /память |
| chat | кнопка «Забыть всё» (с подтверждением) | удаление памяти | /забудь_всё, confirm=true |
| chat | переключатель «Без памяти» | временный чат | флаг сессии nox_incognito |
| chat | быстрые ответы (2-3 чипа под ответом) | продолжить тему | отправка чипа как chat.send |
| chat | значок источника у ответа (память / поиск / модель) | прозрачность | поле meta в ответе |
| chat | строка статуса «чем занимаюсь» в шапке | живое присутствие | GET /api/nox/status |
| chat | плашка «модель занята обучением, ответ до 2 минут» | честное ожидание | GET /api/chat/health |
| chat | кнопки 👍/👎 | обучение стилю | POST /api/feedback |
| chat | режимы: /учить, /коротко, /подробно | выбор режима | команды чата |
| settings | «Тихие часы» (от-до) и лимит проактивных в день | управление инициативой | state/living/quiet.json |
| settings | ползунки личности + переключатель «Правила живого общения» | включает living | persona.json: living=true/false |

## N: бэкенд живых движков (проверено 25.11)
Эндпоинт чата: **POST /api/turn** (SSE, тело {conversation_id, message, nox_incognito?}). /api/chat на тесте даёт 400.
События SSE: meta, level, delta, done. В `done` и в сохранённом сообщении есть поле **meta**: {sources:[«память»|«команда»|«режим»], emo:«грусть», quick:[чипы быстрых ответов], incognito}. Чипы отправлять как обычное сообщение.
Команды (отвечают мгновенно без модели, backend=living): /запомни <текст>, /память [запрос], /забудь <№>, /забудь_всё (первый раз просит подтверждение; кнопка шлёт «/забудь_всё да»), /экспорт, /учить [выкл], /коротко, /подробно, /статус, /тихие_часы 23:00-08:00, /помощь.
«Без памяти»: слать в теле /api/turn `"nox_incognito": true`.
Сервис (через прокси /svc/nox-living/): GET /mem/list, /mem/search?q=, /mem/export, /mem/journal, /status, /quiet, /emo?text=; POST /mem/add {text}, /mem/forget {id} или {all:true, confirm:true}, /quiet {from,to,daily_limit,enabled}, /ritual/run {name: morning|evening|night, force}, /feedback {rating, conversation_id}.
Строка «я сейчас»: GET /svc/nox-living/status -> {status, ts, quiet}.
Ритуалы приходят в GET /api/nox/outbox (kind=living, ritual=morning|evening). Панель «Тихие часы»: GET/POST /svc/nox-living/quiet.
/api/feedback отвечает 200 (проверено), 503 больше не воспроизводится.

## V: внешние советники (шлюз)
Подробный контракт: ADVISORS_EXT.md. Кратко: шлюз OpenAI-совместимый на 127.0.0.1:8793 (`POST /v1/chat/completions`, `model`=`провайдер/модель` или `auto`; `GET /v1/models` со статусами). Реестр советников: /workspace/nox/state/advisors_external.json (id, provider, model, strengths, status, latency_ms, limits). Выключатель «можно наружу»: advisors_cfg.json `external_enabled`; личные данные не уходят, пока `allow_personal=false`. Ключи: /workspace/nox/state/secrets/advisors.env. UI (settings): переключатель «Внешние советники» + список из /v1/models с индикатором available/needs_key.

## Арбитр ресурсов (O, 25.11)
- /workspace/nox/agent/arbiter.py — демон (stdlib, pidfile state/arbiter.pid, автозапуск из svc/start_extra.sh). Правило владельца: чат и задачи в приоритете; обучение (distill_v2.py train, python v5_*) уходит на SIGSTOP при активности, через 60 с тишины SIGCONT; пауза не дольше 30 мин; запись ckpt не прерывается; цель GPU до 90%.
- Состояние: /workspace/nox/state/arbiter.json {mode: chat|tasks|train, since, util, mem_mb, reason, paused, procs, signals, owner{}}. Параметры владельца — блок owner в том же файле: gpu_cap (по умолчанию 90), no_stop (true = только renice 19), force_pause. Журнал: /workspace/nox/arbiter.log (ротация 1 МБ).
- Шина: команда arbiter.status (только чтение) = `python3 /workspace/nox/agent/arbiter.py status` -> JSON. Для виджета «Тело/Обучение» (S1): mode, since, util, mem_mb, reason, paused, procs.
