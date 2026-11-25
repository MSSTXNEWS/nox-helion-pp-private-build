# PROC_AUDIT K1 (P2), 2026-11-25 ~17:00 UTC
Источник: p2_audit.sh (только чтение), p2_clean1.sh (чистка). Секреты из ps не приведены.

## Состояние
- Load avg 32/32 ядра (перегруз CPU), RAM used 109/128 ГБ, avail 17.9 ГБ, swap 0.3/8 ГБ.
- GPU Quadro RTX 8000: 34.1/49.2 ГБ VRAM (69%), util 35%, 78C. Главный потребитель: distill_v2.py train (26.6 ГБ), llama-server 8104 (3.1 ГБ), invokeai (2.3 ГБ).
- Диск: /workspace 399 ГБ, свободно 41 ГБ (90%) -> 42.9 ГБ после чистки; / (overlay) 15.1 -> 15.4 ГБ. Порог >=15 ГБ выполнен (цифра "около 10" в задаче не подтвердилась).
- Зомби: 0. Systemd нет (контейнер, supervisor). tmux: 1 сессия ssh_tmux. screen нет.

## Порты
Слушают: 8200 (llama-swap), 8104, 8300 (judge_service), 8400, 8130, 18215, 18216, 8793, 4210, 4000 (litellm), 4220, 4100.
**8091 НЕ слушает** на K1 (есть 18091 caddy / nox_web_chat_auth, uptime 1д15ч). Требует проверки координатором: чат на 8091 либо за другим интерфейсом, либо упал.
supervisor: nox_tools_gateway = FATAL (Exited too quickly). jupyter, pyworker EXITED с 22.11 (штатно).

## Процессы по ресурсам
- Обучение: distill_v2.py train --steps 400 (раунд r028, autotrain.sh, ckpt_guard) 88% CPU, 4.4 ГБ RAM, 3 ч. Не трогал. Арбитр arbiter.py жив.
- judge_service 8300: 24.9 ГБ RSS (19% RAM), 127% CPU, 23 ч.
- llama-server 8106 gpt-oss-20b -ngl 0: 18.6 ГБ RSS, 193% CPU, 46 ч, не из списка защищённых. Кандидат на остановку решением владельца/арбитра (ест 2 ядра и 18 ГБ RAM на CPU).
- llama-server 8104 Qwen3.6-35B (486% CPU, 20 ГБ), 8141 и 8151 оба грузят Qwen3.5-9B (дубль модели на разных портах, 6.5+8.3 ГБ RAM), 8142 и 8152 оба T-lite-2.1 (4.6+4.7 ГБ). Дубли по модели, не по скрипту: НЕ трогал, кандидат на слияние (освободит ~13 ГБ RAM).
- embed_server.py 8082: 8.3 ГБ, 76% CPU.
- Playwright/chromium: ~5 одновременных QA-сессий (qa_audit, one.py, qa_ctl), суммарно ~5 ядер CPU. Короткоживущие, остатков >1 дня нет.
- 33 torch inductor compile_worker принадлежат обучению (норма для torch.compile).
- Дубли bash (start_all.sh x5, liska_alive_services.sh x4+3, nox_watchdog x4, d_svc_install x4) - дочерние subshell от cron-guard, не реальные дубли; не убивал.
- Процессов >1 суток с CPU<1%: только инфраструктура vast/supervisor/caddy/cloudflared/syncthing/jupyter. Мусора для убийства не найдено, ни один процесс не убит.
- Крон уже чистит чекпоинты/снапшоты/transfers каждые 5-30 мин.

## Чистка (p2_clean1.sh)
| Действие | Проверка | Результат |
|---|---|---|
| pip cache purge (system + venv) | только кэш | 117 файлов, ~26 МБ |
| npm cache | npm не установлен | пропущено |
| /tmp: обычные файлы >180 мин, не открытые процессами, не *.lock/*.pid/*.sock/c300* | список open fd | 9512 файлов, 213 МБ |
| HF кэш /workspace/.hf_home 1.9 ГБ, hf_home 0.6 ГБ | не трогал (могут быть веса) | нет |
| Старые бэкапы | найдено: /workspace/nox/backup 8.3 ГБ (nox_backup.sh по cron), вне правила "2 последних" не удалял | кандидат, нужен ls |
Итого освобождено ~0.3 ГБ кэшей/tmp; рост /workspace +1.9 ГБ - работа cron-чисток обучения. Запретов классификатора не было.

## Утечка секретов
В аргументах процессов видны master-key meilisearch и api-key syncthing (ps открыт любому процессу и попадает в логи Actions). Рекомендация: перенести в env/файл и ротировать ключи. Значения здесь не приведены.

## Требует решения владельца
1. 8091 не слушает; nox_tools_gateway FATAL.
2. Остановить 8106 (gpt-oss-20b CPU) и слить дубли 8141/8151, 8142/8152: -13..30 ГБ RAM, -3 ядра.
3. Ротация ключей meili/syncthing.
