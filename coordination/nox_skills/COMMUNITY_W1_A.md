# COMMUNITY W1 A

Часть A пакета `nox-control/community/` (идеи открытых проектов сообщества, код написан самостоятельно). Подробности и ограничения: `nox-control/community/README_A.md`.

- smart_turn: VAD + адаптивные паузы по PCM 16 кГц; опциональный ONNX Smart Turn v3.x, `backend()` говорит, что активно (ONNX не проверен на реальной модели).
- chalie_router: `route(messages)` -> answer / clarify / act / ignore до модели, RU/EN, <5 мс. API для `glm53/gateway.py` (файл не менялся).
- ada_monologue: монолог через `/completion` llama-server, молчание допустимо, JSONL, файлы личности read-only с проверкой SHA256 до/после, при расхождении блокировка + инцидент.
- heartbeat_md: парсер HEARTBEAT.md (RU) -> расписания, `due(now)`, состояние, JSONL-задачи для `owner_inbox.jsonl`.

Тесты: `cd nox-control && python3 -m unittest discover -s community -t . -p "test_*.py"` - 46 OK.
Статус интеграции: не подключено к шлюзу и диспетчеру, ожидает решения владельца.
