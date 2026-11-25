# LIVING_ENGINES: готовые движки для пробелов LIVING300 (исполнитель N, 25.11)
Лицензии: проверены лично только для rubert-tiny2 (карточка HF); остальное по памяти, отдельно не открывалось, перед промышленным использованием сверить LICENSE.

| Пробелы (№ LIVING300) | Движок | Ссылка | Лицензия | Размер | Подключение / статус |
|---|---|---|---|---|---|
| 6, 7, 11, 12, 13, 14, 206, 235, 293 память | **nox-living mem** (свой слой на SQLite FTS5 по паттернам mem0/Letta: core+archival, журнал, экспорт, забвение) | https://github.com/mem0ai/mem0, https://github.com/letta-ai/letta | mem0 Apache-2.0, Letta Apache-2.0 | 0 МБ (stdlib) | **ВНЕДРЕНО**: сервис 127.0.0.1:18215, /svc/nox-living/. mem0/Letta не взяты: нужны LLM+вектор-БД+эмбеддер, тяжёлые зависимости, диск 9-11 ГБ. Обновление: добавить эмбеддинги e5-small позже |
| граф памяти (9, 10, 40) | Zep/Graphiti, A-MEM, LangMem | github.com/getzep/graphiti, github.com/WujiangXu/A-mem, github.com/langchain-ai/langmem | Apache-2.0 / MIT / MIT | нужен граф-БД и LLM | не внедрено: нужна граф-БД; отложено |
| 21-27, 133, 261, 262 эмоции текста | **cointegrated/rubert-tiny2-cedr-emotion-detection** (6 меток: нет, радость, грусть, удивление, страх, злость), экспорт в ONNX, onnxruntime CPU | https://huggingface.co/cointegrated/rubert-tiny2-cedr-emotion-detection | лицензия в карточке не указана (база rubert-tiny2 MIT); для личной сборки ок, для публикации уточнить | 117 МБ ONNX, 29M параметров | **ВНЕДРЕНО**: /emo, подмешивание подсказки «назови эмоцию» в чат, лог меток без текстов (state/living/emo.jsonl). Порог 0.6, «радость» не подсказывает. Известный минус: короткие приветствия иногда дают «радость» |
| 1, 4 проактивность, расписание, ритуалы | **APScheduler** | https://github.com/agronholm/apscheduler | MIT | ~1 МБ | **ВНЕДРЕНО**: утро 08:30, вечер 21:00, ночь 23:40 (консолидация + дневник state/living/day_*.md); пишут в outbox_owner.jsonl (kind=living); тихие часы и лимит в день state/living/quiet.json |
| 2 обратная связь | свой /feedback (+ существующий /api/feedback) | - | - | - | /api/feedback отвечает 200 (проверено 25.11); дублирующая запись в сервисе: POST /svc/nox-living/feedback |
| команды /команды | разбор в сервисе (/запомни, /память, /забудь, /забудь_всё да, /экспорт, /учить, /коротко, /подробно, /статус, /тихие_часы) | - | - | - | **ВНЕДРЕНО**, без вызова модели |
| голос с эмоцией, выбор голоса NOX | Silero TTS (SSML prosody) | https://github.com/snakers4/silero-models | код MIT/AGPL по версии, модели v3/v4 CC BY-NC-SA 4.0 (некоммерч.) - проверить | уже есть в voice2 (:8095) | не внедрено: следующий шаг, выбор голоса по состоянию через scheduler + запись в state/living/voice.json |
| суммаризация дня | ночной ритуал: список тем из web_conv за день | - | - | - | базовая версия в night; LLM-сводка через /glm - позже |
| советники (подсказки, черновик) | FTS5-ранжирование базы заготовок (awesome-chatgpt-prompts CC0, Fabric MIT) + /glm | https://github.com/f/awesome-chatgpt-prompts, https://github.com/danielmiessler/fabric | CC0 / MIT | ~1 МБ | см. раздел «Очередь» |
| субисполнители | smolagents / Aider / OpenCode / Goose | github.com/huggingface/smolagents | Apache-2.0 и др. | - | см. «Очередь» |

## Решения и ограничения
- Диск /workspace: свободно 9-11 ГБ (порог 15 уже нарушен другими процессами). Поставлено всего ~390 МБ (venv_living 273 МБ + модель 117 МБ). Больше моделей не ставил.
- Python: /workspace/nox/venv_living (onnxruntime, tokenizers, numpy, apscheduler). Модель: /workspace/nox/models/living/emo.onnx.
- Память пишется ТОЛЬКО по явной просьбе (/запомни): это и есть согласие. Чувствительное помечается. «Без памяти» (nox_incognito=true или incognito=true в теле запроса): ни чтения, ни записи, ни лога эмоций.
- Подключение к чату: chat_core.py (бэкап chat_core.py.bak_n_1). Флаги: persona.json -> living_engines {mem0, emotion, rituals}. Перед ответом: POST /pre (команды отвечают сразу без модели; иначе контекст памяти + подсказка эмоции в system). После ответа: POST /post. Таймаут 4 с, при ошибке чат работает как раньше. Тест: /api/turn, 4 сообщения, CHAT_OK; автооткат сработал на неверном тесте и сохранил исходник.
- web_server.py не менялся. Для /svc/nox-living/ нужен только svc_registry (сделано, бэкап .bak_n_1); start_extra.sh дополнен (бэкап .bak_n_1).
- Эндпоинт чата: **/api/turn** работает (SSE, поля conversation_id + message). **/api/chat** на тесте отвечает 400 «нет сообщения пользователя» при теле {conversation_id, message, text, prompt}: у него другая форма тела (не выяснено). S1 использовать /api/turn.
- Нужно от web_server (не трогал): ничего обязательного.

## Очередь (не сделано)
1. Советники: GET /svc/advisors/suggest, POST /pin, GET /pins, GET /draft (контракт в LIVING_UI.md).
2. Субисполнители-роли (Программист, Веб-дизайнер, Исследователь) на smolagents; сначала проверить operators :8130 и cascade :8400 на переиспользование.
3. Голос по состоянию, смена мира/музыки по настроению (с согласием на глобальное).
4. Кодерская модель (Qwen2.5-Coder-7B) - ставить после освобождения диска до 15 ГБ.
