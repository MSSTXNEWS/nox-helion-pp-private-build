# NOX community, часть A

Python 3, только stdlib. numpy/onnxruntime опциональны (только для ONNX-бэкенда smart_turn). Тесты без сети.

Запуск тестов: `cd nox-control && python3 -m unittest discover -s community -t . -p "test_*.py"` (46 тестов).

| Модуль | Что делает |
|---|---|
| `smart_turn.py` | «Человек договорил?» по PCM 16 кГц mono int16. VAD по энергии+ZCR, адаптивный порог шума (10-й перцентиль), адаптивная длина паузы (подстраивается под внутренние паузы говорящего). Опционально ONNX pipecat Smart Turn v3.x (`NOX_SMART_TURN_MODEL` или `load_onnx(path)`); `backend()` -> `"onnx"` / `"heuristic"`. `analyze(pcm)`, `is_turn_complete(pcm)`, `TurnDetector.feed()`. |
| `chalie_router.py` | Правила до модели: `route(messages)` -> `Decision(action, reason, confidence, features)`, action = answer / clarify / act / ignore. Рус./англ. Для шлюза `glm53/gateway.py` (он НЕ изменён): `from community.chalie_router import route`. |
| `ada_monologue.py` | Цикл мыслей через `POST {url}/completion` (по умолч. `http://127.0.0.1:8081` или `NOX_LLAMA_URL`). Пустая мысль = молчание (kind=silence). JSONL-журнал. Файлы личности только читаются; SHA256 до и после цикла; расхождение -> блокировка, мысль не сохраняется, инцидент в `<журнал>.incidents.jsonl`. |
| `heartbeat_md.py` | Парсер HEARTBEAT.md на русском (и базовый английский) + `Scheduler.due(now)`, состояние в JSON, `to_task()` / `fire_due(now, inbox)` -> строки JSONL для `owner_inbox.jsonl` (`id, class=owner_order, handler=track, title, status=pending, ts`). |

CLI: `python3 -m community.heartbeat_md HEARTBEAT.md --state state.json --inbox owner_inbox.jsonl`; `python3 -m community.ada_monologue --journal m.jsonl --persona p.md --cycles 3`.

## Ограничения (честно)
- smart_turn: эвристика различает речь/тишину по громкости, а не смысл фразы; музыка и громкий фон дают ложную «речь». ONNX-путь (лог-мел признаки как у Whisper, вход последние 8 с) написан по описанию модели и НЕ проверен на реальном файле модели: в тестах onnx-модели нет. При любой ошибке происходит откат на эвристику.
- chalie_router: словарные правила, не понимает смысл; сарказм, редкие глаголы, сленг - ошибки возможны. Замер на CPU: в среднем десятки микросекунд на сообщение (порог теста 5 мс).
- ada_monologue: защита от записи - проверка хеша (обнаружение), а не запрет ОС; для жёсткой защиты сделайте файлы личности read-only (chmod/chattr). Берётся только первая строка ответа модели.
- heartbeat_md: времена локальные и наивные (без часовых поясов); «через N минут» отсчитывается от первого чтения правила планировщиком; пропущенные срабатывания схлопываются в одно; не поддерживается «каждые 2 дня в 9:00», «каждый второй вторник», даты вида «15 декабря». Без времени daily/weekly/monthly = 09:00. Нераспознанные строки возвращаются в `errors`, не теряются молча.
- Интеграция в шлюз, systemd/cron и запись в реальный `/root/nox/state/dispatcher/owner_inbox.jsonl` не выполнялись (серверы не трогались).
