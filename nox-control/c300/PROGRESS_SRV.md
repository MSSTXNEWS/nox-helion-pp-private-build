# PROGRESS_SRV (дежурный)
- 2026-11-26 04:35 | судьи fast: verdict 30-33 с -> 6.8 с (auto 9-10 с); cascade под supervisord (RUNNING); диск 17 ГБ свободно (риск порога 15 ГБ от бэкапов, чужие каталоги не трогал); A/B MoE ждёт r033 (axis_guard следит).
- 2026-11-26 04:36 | LiteLLM этап 1: шлюз :8793 вызывает провайдеров через litellm.completion (флаг-выключатель state/gw_litellm.off, бэкап gateway.py.bak_litellm_*); 2 тест-запроса ок, usage пишется в state/gw_journal/usage-*.jsonl. Этап 2 после суток проверки.
