# L2_NOX_A: чтение, правка, PR, тесты (selftools)

Исполнитель: NOX-A. Код: `nox-control/selftools/` (реестр `registry.py`, 30 инструментов, README с таблицей). Режимы: read / write (dry-run по умолчанию, .bak) / danger (confirm). Не менять защищённые файлы V29.3, деплой делает главный агент.

| # | Шаг | Критерий приёмки | Статус |
|---|---|---|---|
| A1 | Прогнать `python3 -m unittest discover -s nox-control/selftools/tests` | OK, 37 tests, 0 failures | TODO |
| A2 | `registry.py list` и сверка с README | 30 инструментов, имена совпадают с таблицей | TODO |
| A3 | `repo_grep` + `repo_read` + `self_map` по `nox-control` | находит `def main` в nox_advisors.py; self_map перечисляет модули без ошибок | TODO |
| A4 | `lint_syntax` по всем `selftools/*.py` и `*.sh` в nox-control | `bad: 0` (js-файлы: ok или blocked «node not installed») | TODO |
| A5 | `patch_apply` на копии файла в /tmp: dry-run, затем dry_run=false | dry-run файл не меняет; реальный даёт .bak; повторное применение возвращает ошибку контекста | TODO |
| A6 | `rollback` после A5 | файл равен исходному; создан .bak текущей версии | TODO |
| A7 | `branch_pr` action=open_pr в dry-run для тестовой ветки | в payload тело заканчивается строкой «Generated with Claude Code»; коммит-dry-run содержит трейлеры Co-Authored-By и Claude-Session | TODO |
| A8 | `test_runner` на `nox-control/advisors` | ran >= 1, failures 0 | TODO |
| A9 | `task_board` list/add/pop на копии NOX_DISPATCH_DIR во временной папке | параллельные 20 add без потерь; файл-лок работает | TODO |
| A10 | `inspector_hook` на coordination/inspector | возвращает count, newest_age_s, флаг stale | TODO |

Правила: ничего не удалять, реальные записи только после dry-run, блокировки (`blocked`) не обходить, а сообщать владельцу поле `need`.
