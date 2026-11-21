# L1_NOX_B: память, GPU, обучение

Исполнитель: NOX-B. Код: `nox-control/l1/`. Статус карточки: ACTIVE; DRAFT_FOR_OWNER_APPROVAL там, где нужно решение владельца.

| # | Шаг | Критерий приёмки | Статус |
|---|---|---|---|
| B1 | `bash resource_plan.sh` (dry-run) на сервере, сохранить вывод | вывод содержит GPU/RAM/диск/supervisor и рекомендации 1-9 | TODO |
| B2 | `bash disk_report.sh`, сохранить вывод | топ-20 путей и кандидаты; ничего не удалено (df до = после) | TODO |
| B3 | Согласовать список очистки диска (97%) | владелец отметил, что можно удалять; цель <85% | DRAFT_FOR_OWNER_APPROVAL |
| B4 | `resource_plan.sh --apply` при работающем trainer | trainer nice=10, oom_score_adj=500, swappiness=10; бэкап создан | DRAFT_FOR_OWNER_APPROVAL |
| B5 | Проверить `--rollback` | значения nice/oom/swappiness вернулись к бэкапу | TODO |
| B6 | Убедиться, что trainer идёт на GPU с большим free VRAM и MIN_FREE_MIB соблюдается (c59) | в логе trainer указан GPU с max free; чат не получил OOM | TODO |
| B7 | Замерить tok/s чата с trainer и без | падение tok/s чата <10% при работающем trainer | TODO |
| B8 | THREADS: рекомендация из плана проверить c78 bench (с откатом) | tok/s не хуже baseline, иначе откат | DRAFT_FOR_OWNER_APPROVAL |
| B9 | MOE_CACHE_MIB и cgroup memory.high для trainer: пробный запуск | нет swap-штурма (si/so ~0 в vmstat 5 мин), чат стабилен | DRAFT_FOR_OWNER_APPROVAL |
| B10 | Отчёт: до/после по RAM, VRAM, диску, скорости | таблица в coordination/, без секретов | TODO |

Правила: drop caches запрещён, STOP-флаги соблюдать, не трогать run_update.py/deploy и файлы V29.3.
