# NOX agent (шаги 31-36, 39)

Python 3 stdlib. Тесты без сети: `cd nox-control && python3 -m unittest discover -s agent -t . -p 'test_*.py'` (91 тест; поддельный шлюз на loopback, временные git-репозитории).
Запуск модулей: из `nox-control/` как `python3 -m agent.<модуль>`.

| Файл | Шаг | Что делает |
|---|---|---|
| `loop.py`, `gateway_client.py` | 31 | Цикл план -> вызов инструмента -> проверка -> шаг -> итог. OpenAI `tools` через шлюз :8082; запасной формат ```` ```tool {JSON}``` ````; лимиты шагов/времени/токенов; STOP; журнал JSONL |
| `tools/` | 32 | `shell`, `read_file`, `write_file`, `edit_file`, `git`, `run_tests`, `web_search`, `fetch_page`, `browser`, `skill_search`, `code_where`; `approvals.py` очередь подтверждений |
| `release.py` | 33 | Песочница-worktree `nox/<задача>`, выкатка только при зелёных тестах И судье ok, автооткат по health, STOP |
| `selfbuild.py` | 34 | Задача из канбана -> патч циклом -> тесты -> судья (быстрый тир) -> merge/откат; опасное только через владельца |
| `skills.py` | 35 | Рецепты успешных решений, FTS5, подстановка в промпт |
| `codeindex.py` | 36 | Индекс своего кода (файл, символ, docstring), «где у меня X» |
| `planner.py` | 39 | Канбан + календарь как источник задач, напоминания, отчёт |

## Быстрый старт
```
cd nox-control
python3 -m agent.loop run "прочитай README.md и скажи, сколько в нём строк" --workdir /путь/к/ветке   # один прогон цикла
python3 -m agent.loop stop          # поставить STOP (файл-флаг); снять: clear-stop
python3 -m agent.selfbuild --once   # взять одну кодовую задачу из owner_inbox.jsonl
python3 -m agent.selfbuild --daemon --interval 300
python3 -m agent.tools.approvals list | approve ID | deny ID      # решения владельца
python3 -m agent.planner list | next | tick | digest | remind 2026-11-22T12:00 "текст"
python3 -m agent.codeindex where "роутер тиров"      # индекс строится сам
python3 -m agent.skills search "добавить эндпоинт"
```

## Пользователь nox-agent (песочница shell)
```
useradd -m -s /bin/bash nox-agent
mkdir -p /root/nox/state/agent/work && chown -R nox-agent: /root/nox/state/agent     # рабочие ветки и состояние
```
Рекомендуется запускать агента от `nox-agent` целиком. Если процесс запущен от root, shell и тесты роняют права до `nox-agent` (uid/gid, без групп); если пользователя нет, команда НЕ запускается (`NOX_AGENT_ALLOW_ROOT=1` только для отладки). Секреты (GH_TOKEN и т.п.) живут в окружении процесса агента, в shell окружение чистое (PATH, HOME=ветка, LANG). `git push` делает инструмент `git` процесса агента, а не shell.

## Цикл (31)
- Шлюз вызывается без stream (в stream-режиме шлюз не пропускает `tool_calls`), `nox_mode=deep`, `nox_no_route`, `nox_no_retry`. Системного сообщения нет: инструкции идут первым user-сообщением (шлюз сам ставит persona как system).
- Формат вызова: нативный `message.tool_calls` (llama-server с `--jinja`); если их нет, разбираются блоки ```` ```tool ```` с `{"name","arguments"}` (объект или список). Невалидный JSON возвращается модели как ошибка. Завершение: `finish(summary, success)` или текст без вызовов.
- Проверка результата: каждый результат помечается ok/ошибка; при ошибке модели напоминается сменить подход; одна и та же ошибка `NOX_AGENT_STUCK` раз подряд даёт `stuck`; 5 одинаковых удачных вызовов подряд тоже `stuck`. Необязательный `verify`-хук после `finish` (selfbuild ставит run_tests) возвращает модель на доработку.
- Лимиты: шаги, секунды, токены (сумма `usage.total_tokens`). Контекст сжимается (старые результаты инструментов обрезаются, середина истории удаляется без разрыва пар assistant/tool).
- STOP: файл `NOX_AGENT_STOP_FILE` (проверяется перед шагом, перед каждым инструментом и каждые 0,2 с во время вызова шлюза), `stop_event`, SIGTERM/SIGINT. Во время вызова: закрывается сокет и шлюзу уходит `POST /v1/stop` для id запросов, которые появились в `/v1/nox/stats.active` после начала нашего вызова.
- Журнал: `NOX_AGENT_LOG_DIR/<run_id>.jsonl`, события `start, plan, model, tool, check, verify, compact, stop, end`. Секреты (ghp_, sk-, token=, password=) маскируются.

## Инструменты (32)
- `shell`: однострочная команда, cwd = ветка, таймаут (по умолчанию 60 с, максимум 600), rlimits (CPU, память, файлы, процессы), группа процессов убивается целиком, вывод с обрезкой. Запрещено: `rm -rf /` и корня/ветки, `dd`, `mkfs`, `curl|sh`, `sudo/su`, `ssh/scp/rsync`, `printenv/env`, подстановки `$x`, `$(..)`, `` ` ``, heredoc, пути вне ветки (включая `..` и симлинки), `/root`, `.env`, ключи, `.ssh`, `/etc/shadow`, `/proc/*/environ`, git-команды кроме чтения (остальное через инструмент `git`). Подтверждение владельца: удаление (`rm`, `find -delete`), деньги (stripe, оплата...), доступы (chmod/chown/useradd/gh auth...), Vast, управление сервисами, установка пакетов.
- Подтверждения: `approvals.jsonl` (запрос, решение владельца, использование). Одобрение одноразовое и привязано к точному тексту команды. Инструмент возвращает `needs_confirmation`, цикл останавливается со статусом `awaiting_owner`.
- `read_file/write_file/edit_file`: только внутри ветки; запись только когда HEAD = `nox/*`; секреты и `.git` недоступны.
- `git`: `branch` (создать/перейти `nox/<имя>`), `status`, `diff`, `log`, `commit` (отказ, если в изменениях секреты/`.pyc`), `push` только `nox/*` без force.
- `run_tests`: только `python3 -m unittest ...` (по умолчанию `NOX_AGENT_TEST_CMD`) в песочнице; результат `ok/ran/failures/errors/tail`; 0 тестов = не ok.
- `web_search` (DuckDuckGo HTML или SearXNG JSON) и `fetch_page` идут через `NOX_AGENT_HTTP_PROXY` (или `HTTPS_PROXY`); лимиты: байты, символы, число веб-вызовов за прогон, таймаут; HTML чистится (script/style/nav/footer/form убраны); защита от SSRF (локальные/приватные адреса, редиректы перепроверяются); результат помечен `untrusted`.
- `browser`: Playwright, если установлен и есть chromium (`pip install playwright && python3 -m playwright install chromium`); иначе ошибка `Playwright не установлен` + что поставить.

## Песочница и откат (33)
`Sandbox.create` делает `git worktree add -b nox/<задача>` от `NOX_AGENT_BASE_BRANCH`. `Release.deploy` вливает ветку (`merge --no-ff`) в живой репо только если: ветка закоммичена; `run_tests` зелёные; судья вернул строго `ok: true` (без судьи или при диффе больше `NOX_AGENT_JUDGE_MAX_DIFF` выкатки нет); нет удалений файлов и правок защитных модулей (`NOX_AGENT_PROTECTED`: release, approvals, shell, files, gitops, .github) без подтверждения владельца; живой репо на base и чистый; health до выкатки зелёный. После merge: `NOX_AGENT_DEPLOY_CMD` (необязательно, argv без shell), затем `NOX_AGENT_HEALTH_CHECKS` проверок `NOX_AGENT_HEALTH_URL`; при падении или STOP: откат (`reset --hard` на pre-sha, если наш merge последний, иначе `revert -m 1`) и повторный deploy. `NOX_AGENT_MERGE=0` (или `--no-merge`) оставляет ветку готовой, не вливая.

## Самосборка (34)
Задача берётся из `owner_inbox.jsonl` (реальный формат: `{"id","class":"owner_order","handler","title","status":"pending","ts"}`, см. `community/heartbeat_md.to_task`) и `queue.jsonl` диспетчера. Кодовая задача: `handler`/`class` = `selfbuild`, либо `selfbuild: true`, либо заголовок `код:`/`code:`/`selfbuild:`. Остальные задачи (напоминания `track`) не трогаются. Порядок: опасное в тексте задачи (удаление, деньги, доступы, S2, Vast) -> запрос владельцу ДО правок -> worktree -> подсказки (codeindex, skills) -> цикл с проверкой run_tests на `finish` -> commit -> `release.deploy` (тесты, `judge(task, diff, test_report)` на быстром тире, опасное в диффе) -> при успехе рецепт в skills и удаление worktree. После решения владельца следующий запуск продолжает задачу (с этапа выкатки, если ждали на ней). Статусы пишет `task_state.jsonl`; файлы-источники не меняются.

## Навыки, индекс кода, планировщик (35, 36, 39)
- `skills.py`: рецепт `{name, condition, steps, tools, check, source_task, uses, successes}` строится из журнала удачного прогона (шаги = удавшиеся вызовы, проверка = последний зелёный run_tests); повтор того же рецепта увеличивает счётчик; поиск FTS5 (bm25, префиксы основ для русского); `prompt_for(текст)` вставляет рецепты в промпт.
- `codeindex.py`: Python через `ast` (модуль, классы, функции, методы, docstring), Markdown (заголовки), shell/JS (функции); идентификаторы режутся на слова; инкрементально по mtime+размер. Ответ: `путь:строка`, символ, docstring.
- `planner.py`: `next()` даёт следующую задачу (приоритет, срок, время создания; попытки ограничены `NOX_AGENT_TASK_RETRIES`); календарь JSONL `{"id","title","start","duration_min","remind_before_min":[..],"repeat":"none|daily|weekly","task":true}` (событие с `task` в момент старта становится задачей, любое событие даёт напоминания); `remind/tick/due_reminders` (JSONL, выдаются один раз); `report` после выполнения и `digest`.

## Env
| переменная | по умолчанию |
|---|---|
| NOX_AGENT_GATEWAY / _MODE / _JUDGE_MODE | http://127.0.0.1:8082 / deep / fast |
| NOX_AGENT_MAX_STEPS / _MAX_SECONDS / _MAX_TOKENS / _STEP_MAX_TOKENS | 30 / 1800 / 200000 / 4096 |
| NOX_AGENT_STATE | /root/nox/state/agent (если /root/nox/state доступен), иначе /tmp/nox-agent-state |
| NOX_AGENT_STOP_FILE / _LOG_DIR / _APPROVALS | <STATE>/STOP, <STATE>/journal, <STATE>/approvals.jsonl |
| NOX_AGENT_REPO / _BASE_BRANCH / _WORK | корень репозитория / main / <STATE>/work |
| NOX_AGENT_USER / _ALLOW_ROOT / _SHELL_TIMEOUT / _SHELL_MEM_MB / _SHELL_NO_NET | nox-agent / 0 / 60 / 1024 / 0 |
| NOX_AGENT_TEST_CMD / _TEST_CWD / _TEST_TIMEOUT | `python3 -m unittest discover -s agent -t . -p test_*.py` / nox-control / 900 |
| NOX_AGENT_HTTP_PROXY (или HTTPS_PROXY), _SEARCH_URL, _SEARCH_KIND, _WEB_* | пусто, DuckDuckGo html, ddg |
| NOX_AGENT_HEALTH_URL / _HEALTH_CHECKS / _HEALTH_INTERVAL / _DEPLOY_CMD / _MERGE | :8082/v1/nox/stats / 3 / 5 / пусто / 1 |
| NOX_AGENT_JUDGE_MAX_DIFF / _PROTECTED | 24000 / защитные модули |
| NOX_AGENT_INBOX / _QUEUE / _CALENDAR | /root/nox/state/dispatcher/owner_inbox.jsonl / .../queue.jsonl / <STATE>/calendar.jsonl |
| NOX_AGENT_SKILLS_DB / _CODE_DB / _TASK_STATE / _REMINDERS / _REPORTS | <STATE>/... |

## Честные ограничения
- На реальных llama-server/GLM не проверялось: тесты идут на поддельном шлюзе. Качество планов и разбор tool_calls на живой модели не измерены (GLM ~1,5 ток/с: шаг цикла занимает минуты).
- `/v1/stop` шлюза принимает id запроса, а шлюз отдаёт его только после ответа. Поэтому при STOP во время вызова агент останавливает все запросы, появившиеся в `active` после начала вызова; чужой чат, начатый в этот же момент, тоже может быть остановлен. Остановка llama-server опирается на разрыв соединения.
- Статический разбор shell это второй рубеж (токены, regex): интерпретатор (`python3 -c`) может сделать то, что regex не видит. Настоящая граница: пользователь `nox-agent` без доступа к /root и секретам и права на каталоги. `NOX_AGENT_SHELL_NO_NET=1` требует `unshare -n` (root или user namespaces), иначе команды не запускаются.
- Судья это модель быстрого тира: он снижает риск, но не гарантирует корректность; решающее условие по-прежнему зелёные тесты. Если быстрый тир недоступен, шлюз отвечает глубоким GLM (медленно).
- Диф больше `NOX_AGENT_JUDGE_MAX_DIFF` не выкатывается (разбей задачу). Правки защитных модулей агента и удаления требуют владельца.
- Браузер (Playwright) не запускался: в тестах проверена только ветка «не установлен». Поиск DuckDuckGo парсится по вёрстке html-версии (может измениться); надёжнее свой SearXNG (`NOX_AGENT_SEARCH_KIND=searx`).
- Откат по health ловит только падение health-URL и deploy-команды, а не скрытые функциональные поломки. Откат `reset --hard` затрагивает только живой репо в состоянии «наш merge последний».
- Календарь: локальное наивное время; повторы только daily/weekly. Диспетчер NOX не подключён: агент читает `owner_inbox.jsonl`/`queue.jsonl` и ведёт собственное состояние. В systemd/cron и на серверах ничего не разворачивалось.
