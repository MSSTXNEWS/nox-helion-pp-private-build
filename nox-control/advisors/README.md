# NOX advisors

Консультации NOX у других open-weight моделей (локальные llama.cpp, OpenAI-совместимый API).
Только stdlib Python 3. Локальные советники работают без ключей и интернета; удалённые (OpenAI-совместимые, CLI, SearXNG) добавляются в конфиг.

Файлы:
- `nox_advisors.py` — модуль и CLI
- `advisors.example.json` — пример конфига (порты 8101-8103), список {name, url, timeout_s, role}
- `test_nox_advisors.py`, `test_nox_advisors_remote.py` — тесты (`python3 -m unittest`)
- `searxng_install.sh` — локальный SearXNG :8888 (dry-run по умолчанию, `--apply` для установки)

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

## Удалённые советники (список 3)
Поля конфига: `kind` = `openai` (по умолчанию) | `cli` | `searxng`; `model`, `api_key_env` (имя переменной окружения; ключ только из env, не в файлах и логах),
`retries` (ретраи 408/429/5xx/сеть с backoff, 4xx не ретраятся), `timeout_s`, `daily_limit` (счётчик в `advisors_usage.json` рядом с конфигом или `$NOX_ADVISORS_STATE`, сутки по UTC),
`cli`: `copilot` | `gemini` (allowlist; запуск без shell, в пустой temp-папке, урезанное окружение, без флагов записи), `enabled`.
- Ответы удалённых советников начинаются с «[мнение советника, не NOX: имя]»; поле `label` есть всегда.
- Исходящий текст удалённым советникам фильтруется: ключи/токены/приватные ключи -> `[REDACTED_SECRET]`, пути -> `[PATH]`.
- Нет ключа/CLI/логина или лимит исчерпан: `{"ok":false,"blocked":"...","need":"..."}`, сетевой запрос не делается.
- Режим «консенсус кода»: `python3 nox_advisors.py code "задача" --config advisors.json` -> ask с просьбой о diff, сравнение, `proposal` (патч-предложение). Патч никогда не применяется (`applied:false`); решает NOX/владелец.
- `advisors.example.json`: Copilot CLI Free (вход GitHub), OpenCode+MiMo V2.5 Free (ключ OpenCode Zen), Particle-1 Free и Nemotron 3.5 Lightning Free (OpenRouter, 50/день), Gemini CLI + Google Search (вход Google, 1000/день), SearXNG (:8888). Точные id моделей владелец сверяет через `/models` соответствующего сервиса.
