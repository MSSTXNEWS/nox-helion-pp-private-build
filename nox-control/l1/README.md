# L1: умнее ответы NOX + память/ресурсы под обучение

| Файл | Назначение |
|---|---|
| `system_prompt_ru.txt` | системный промпт NOX (RU) |
| `sampling.json` | temperature .55, top_p .9, repeat_penalty 1.05; режимы `fast` / `precise` |
| `rag_stub.py` | индексация `coordination/*.md`: bge-m3 (порт 8082), при недоступности — BM25; только stdlib |
| `resource_plan.sh` | read-only dry-run план; `--apply` — только nice/ionice/oom_score_adj trainer и swappiness=10; `--rollback` |
| `disk_report.sh` | топ-20 тяжёлых путей, кандидаты на очистку; ничего не удаляет |

```
python3 nox-control/l1/rag_stub.py index --root . && python3 nox-control/l1/rag_stub.py query "диск"
bash nox-control/l1/resource_plan.sh            # dry-run
bash nox-control/l1/resource_plan.sh --apply    # безопасное, бэкап в /root/nox/state/l1_backup
bash nox-control/l1/resource_plan.sh --rollback
bash nox-control/l1/disk_report.sh
python3 -m unittest discover -s nox-control/l1/tests
```
Не делает: drop caches, рестарты сервисов, удаления, правки run_update.py/deploy/файлов V29.3.
Ограничение: cgroup memory.high и THREADS/MOE_CACHE_MIB только рекомендуются (применяет владелец/главный агент).
