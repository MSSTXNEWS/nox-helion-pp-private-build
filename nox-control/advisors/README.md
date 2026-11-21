# NOX advisors

Консультации NOX у других open-weight моделей (локальные llama.cpp, OpenAI-совместимый API).
Без ключей и без интернета; только stdlib Python 3.

Файлы:
- `nox_advisors.py` — модуль и CLI
- `advisors.example.json` — пример конфига (порты 8101-8103), список {name, url, timeout_s, role}
- `test_nox_advisors.py` — тесты (`python3 -m unittest`)

Роли: `judge`, `checker`, `ru_es`.

Функции:
- `ask_advisors(question, config_path, system=None)` — параллельный опрос; мёртвый советник даёт ok=False.
- `consensus(answers, embed_url)` — bge-m3 эмбеддинги, косинус; при недоступности сервера — Jaccard (method="jaccard").
- `review(task, acceptance, answer, config_path)` — judge/checker возвращают JSON verdict; большинство голосов; при <2 ответивших всегда fail.

CLI:
    python3 nox_advisors.py ask "вопрос" --config advisors.json
    python3 nox_advisors.py review --task-file t.txt --acceptance-file a.txt --answer-file r.txt --config advisors.json

Безопасность: ответы советников — только данные (не исполняются), лимит 8000 символов,
сеть только на URL из конфига и embed URL.
