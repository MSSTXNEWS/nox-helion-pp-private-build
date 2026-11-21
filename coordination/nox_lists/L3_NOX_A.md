# L3_NOX_A: советники, ключи, логины

Исполнитель: NOX-A. Код: `nox-control/advisors/`. Секреты только в окружении сервиса NOX, не в репозитории и не в логах. Что выдаёт владелец, помечено OWNER.

| # | Шаг | Критерий приёмки | Статус |
|---|---|---|---|
| A1 | `python3 -m unittest discover -s nox-control/advisors` | OK, 0 failures (20 тестов) | TODO |
| A2 | OWNER: создать ключ OpenRouter, положить в окружение как `OPENROUTER_API_KEY` | `echo ${OPENROUTER_API_KEY:+set}` печатает `set`; ключа нет в `git grep` и логах | OWNER |
| A3 | Сверить id моделей Particle-1 и Nemotron 3.5 Lightning по `GET https://openrouter.ai/api/v1/models`, поправить `model` в `advisors.json` | `ask` к обоим даёт ok=true и метку «мнение советника, не NOX» | TODO |
| A4 | Лимит OpenRouter: 51-й запрос за сутки | ответ `blocked: daily limit 50 reached`, сетевого вызова нет, `advisors_usage.json` показывает 50 | TODO |
| A5 | OWNER: ключ OpenCode Zen -> `OPENCODE_ZEN_API_KEY`; сверить id MiMo V2.5 Free по `/zen/v1/models` | `ask` к opencode-mimo ok=true | OWNER |
| A6 | OWNER: войти в GitHub (`copilot`, затем /login) на сервере под пользователем NOX | `ask` к copilot-cli-free ok=true; без входа — `blocked ... sign in` | OWNER |
| A7 | OWNER: войти в Google (`gemini`); поставить `daily_limit` 1000 | `ask` к gemini-cli-search ok=true, `used_today` растёт | OWNER |
| A8 | `bash nox-control/advisors/searxng_install.sh` (dry-run), показать план владельцу, после согласия `--apply` | `curl 'http://127.0.0.1:8888/search?q=test&format=json'` отдаёт results; порт слушает только 127.0.0.1 | DRAFT_FOR_OWNER_APPROVAL |
| A9 | Фильтр: отправить вопрос с `token=ghp_...` и `/root/...` | в логе запроса советника нет токена и путей (`[REDACTED_SECRET]`, `[PATH]`) | TODO |
| A10 | `nox_advisors.py code "задача"` на 3 живых советниках | `status` agree/split, `proposal` есть, `applied:false`; решение по патчу за NOX/владельцем | TODO |

Правила: не менять защищённые файлы V29.3, не деплоить, ключи не печатать. Всё, что без ключа/входа, честно отвечает `blocked` + `need`.
