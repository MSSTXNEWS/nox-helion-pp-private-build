# L2_NOX_B: сервер, обучение, внешнее (selftools)

Исполнитель: NOX-B. Код: `nox-control/selftools/`. Всё, что требует внешнего ресурса, возвращает `{"ok":false,"blocked":...,"need":...}`; такой результат фиксировать в отчёте, не обходить. Шаги DRAFT_FOR_OWNER_APPROVAL ждут решения владельца.

| # | Шаг | Критерий приёмки | Статус |
|---|---|---|---|
| B1 | `health_probe` (8091, 8082, bridge) на сервере | по каждой цели up/down и ms; down объяснён | TODO |
| B2 | `speed_bench` на :8098, 3 прогона | avg_ttft_s и avg_tok_s записаны как baseline; недоступность даёт `blocked` | TODO |
| B3 | `gpu_alloc` + `mem_alloc` + `disk_guard` report | отчёт GPU/RAM/диск; предупреждение warn при >=85% | TODO |
| B4 | `disk_guard` plan_clean, затем clean только с confirm | в плане только белый список (*.bak, *.tmp, *.part, *.pyc); после clean освобождено не меньше плана | DRAFT_FOR_OWNER_APPROVAL |
| B5 | `svc_ctl` status всех сервисов; restart одного тестового в dry-run | status читается; restart вне allowlist отклонён | TODO |
| B6 | `corpus_build` (карточки + коммиты) в корпус на сервере | новый jsonl, повторный запуск даёт new=0 (дедуп) | TODO |
| B7 | `eval_gate` score на holdout до и после; gate с max_drop 0.02 | pass=true только если после >= до - 0.02 | TODO |
| B8 | `train_ctl`: положить train.json, start dry-run, set_stop_flag, start (должен быть blocked), clear, status | поведение STOP-флага подтверждено; реальный start только после решения владельца | DRAFT_FOR_OWNER_APPROVAL |
| B9 | `lora_swap` swap на тестовый адаптер с health_url | при провале здоровья ссылка возвращена на прежний адаптер (rolled_back=true) | DRAFT_FOR_OWNER_APPROVAL |
| B10 | `pc_pull` (Tailscale 100.84.111.36) dry-run; `model_dl` с SHA256 по явной команде | без ssh-доступа: blocked + need; с доступом: rsync -n список; model_dl при неверном SHA256 удаляет .part | DRAFT_FOR_OWNER_APPROVAL |

Правила: деньги, доступ, удаление данных, снятие защит согласовывать с владельцем; остальное решать самому и не останавливать работу.
