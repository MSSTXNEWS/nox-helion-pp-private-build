# READY_MAP_SRV: самописное на сервере K1 и готовые замены (SRV, 26.11)

Факты собраны только чтением (srv_map1-3, srv_gw4-5). Секреты не печатались.
Схема замены: готовое + тонкий адаптер, бэкап, флаг отката, замер до/после. web_server.py и ядро BRAIN не трогаем.

## Что уже стоит на сервере (не надо ставить)
supervisord (13 программ: caddy, cron, tunnel_manager, nox_sun_adapter, nox_searxng, nox_ops_core, nox_web_chat_*, syncthing, tensorboard...), litellm 1.110 (venv, proxy уже работает на :4000 с fallbacks по advisor-*), rq 2.12 (нет redis-server), huey 3.5 (agents/venv), APScheduler, prometheus_client (venv_tools), trl 1.14.2, unsloth 2026.11.9, peft, beszel (:18203), uptime-kuma (:18205), glance (:18200), node (tools/node), playwright. Нет: logrotate, vector, netdata, node_exporter, Lighthouse CI, promptfoo, lm-eval, axolotl, LLaMA-Factory, s6, pm2.

## Таблица: компонент, поломки, топ-3 замены, решение по Парето

| Компонент (самописное) | Что ломается (факты) | Топ-3 готовых | Решение |
|---|---|---|---|
| Сторожа/watchdog: cascade_watchdog.sh, stewards (19 файлов, 1506 строк), operators/watchdog.sh, run_guard/run_orch по cron каждые 2 мин, run_supervisor.sh по cron каждую минуту, ~10 @reboot | cascade_watchdog 29683 раза падал на bind (сирота держал :8400); дубли supervisor | 1) supervisord (уже есть, conf.d, autorestart, startsecs, startretries, stopasgroup) 2) s6-overlay 3) pm2 | supervisord. Сначала cascade (пилот), затем 8082 embed, 18217 pipeline, 8300 judge, 8793 gateway. Политики приоритета (chat_guard cpuset/SIGSTOP) остаются: готового аналога нет |
| Очереди и flock (36 файлов с flock/fcntl, dispatcher_worm, bigjudge_queue.jsonl) | гонки tmp-файлов (status.json.tmp, исправлено ATOMIC_P3) | 1) Huey + SQLite (уже в agents/venv, без redis) 2) RQ (нужен redis, нет сервера) 3) APScheduler (есть) | Huey SQLite только для новых фоновых задач; существующее не переписывать |
| Журналы | logrotate нет; самый большой лог 33 МБ (cascade_8400, из-за bind-ошибок) | 1) logrotate (apt есть кандидат 3.19, copytruncate) 2) supervisord stdout_logfile_maxbytes (уже в конфигах программ) 3) vector | Пилот: supervisord maxbytes для переведённых программ; logrotate по cron для agent/out/*.log, когда apt согласован. Срочности нет |
| Мониторинг (p3_status_svc :18230, chat_speed_watch, status.json) | дублируют друг друга | 1) uptime-kuma + beszel (уже работают) 2) prometheus_client /metrics (есть в venv_tools) 3) netdata | Использовать kuma для health-портов 8090/8091/8104/8793/8300/18217/8400/8082; своё оставить как источник данных |
| QA (qa_audit.py, Playwright, зависал дважды, 2 chrome по 130-250% CPU) | зависания, нагрузка | 1) Lighthouse CI (node есть) 2) Playwright Test runner 3) Pa11y | Lighthouse CI для perf/a11y 12 страниц, qa_audit оставить для функциональных проверок и запускать под таймаутом |
| Судьи (judge_service 19 моделей, fidelity_test.py) | в фазе train все судьи на CPU: один /judge 30-33 с, verdict timeout 22 с в ~50% | 1) lm-evaluation-harness (свои задачи по осям) 2) promptfoo (asserts) 3) DeepEval | lm-eval для ворот обучения (пороги те же); judge_service оставить для чата с режимом fast |
| Обучение (distill_v2.py ~2800 строк, autotrain.sh, ckpt_guard, gates) | 3 дня без прироста, 5/5 кандидатов NO_GAIN | 1) TRL SFT/DPO/KTO (стоит) 2) LLaMA-Factory 3) Axolotl | TRL напрямую (уже в venv, Unsloth совместим). Персона и анти-лесть через DPO. Сравнение раунд к раунду по с/шаг и осям. См. ниже |
| Шлюз советников (advisors/gateway.py, 311 строк) | ротация, квоты, кэш, backoff, фильтр приватного, журнал: всё самописное | 1) LiteLLM (стоит) 2) OpenRouter-стиль роутер 3) Portkey OSS | Поэтапно: этап 1 вызов провайдеров через litellm.completion внутри шлюза (retry, Retry-After, usage, колбэки), этап 2 фронт на LiteLLM proxy с callback приватности и приоритета чата |

## Обучение: решение
1. Стек: TRL DPOTrainer (+Unsloth patch, QLoRA NF4, fp16) для персоны и анти-лести. SFT-ветка distill_v2 остаётся для знаний.
2. Данные: пары chosen/rejected: Anti-Sycophancy-DPO (apache-2.0, 3480 пар) + свои (chosen из gen1-3 персоны, rejected, сгенерированные льстивыми системными подсказками локальными моделями). Всё через P3_FILTER.
3. Оценка: lm-evaluation-harness, кастомные задачи nox_flattery, nox_false_memory, nox_rename, nox_directness с правилами из brain/SLP/fidelity_test.py (rule_check); пороги: падение оси не более 2 п.п. к базе.
4. Сравнение: один раунд DPO против текущего SFT в окно после r032; метрики: с/шаг и оси.
