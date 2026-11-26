# FORGOTTEN_V5 — сверка КАНОНА ЖИЗНИ v5 с реальным K1 (CANON-ревизор, 2026-11-26 13:30Z)
Проверено пробами canon_probe1/2/3 (find/stat/ключи JSON, без содержимого). "файл есть" не равно "работает": живость подтверждена только там, где указан mtime/процесс.

| # | Пункт канона | Гл. | Статус на K1 (чем проверено) | Что доделать | Готовое решение | Кто | Парето |
|---|---|---|---|---|---|---|---|
| 1 | Диск >=15 ГБ, ротация | 1 | НАРУШЕНО: свободно 5.7 ГБ, 99% (df). models 278G, ops 36G, distill_v2 19G, backup 13G | ротация/освобождение по слову владельца; список кандидатов отдан координатору | restic-prune политика, перенос моделей на архив | CANON+ДЕЖУРНЫЙ | P0 |
| 2 | systemd units nox-*.service + nox.target | 1 | нет (/etc/systemd пусто); есть supervisord: ~12 nox_* RUNNING | оставить supervisord (контейнер Vast без systemd): канон пометить как "supervisord" | supervisord | CANON | P2 |
| 3 | Сторож раз в минуту (диск/VRAM/порт) | 1 | частично: cascade_watchdog.sh, web_watchdog, nox_watchdog.sh A; единого диск-сторожа с ротацией нет (диск 99%) | disk_guard: порог 15 ГБ -> пауза тренера + алерт (без удаления) | свой bash, тонкий | CANON | P0 |
| 4 | Бэкап души каждый час, age, копия на Drive, пробное восстановление | 1 | частично: cron 03:17 backup + 10:17 upload, restic, soul_backup_ok.json (mtime 24.11, устарел); почасового нет; age не проверен | почасовой лёгкий бэкап passport/ledger/S03 (малый размер); еженедельный restore-тест | restic уже есть | CANON | P1 |
| 5 | Архив GB10 с sha | 1 | частично: archive/gb10_final_20261124 есть, а gb10_final (имя канона) нет | сверить sha, записать в Ledger | sha256sum | ДЕЖУРНЫЙ | P2 |
| 6 | Шина событий SQLite+Redis, доска, диспетчер, руки | 2 | частично: state/bus/events.db, nox_bus.py, svc_dispatcher.py; redis-cli нет, arq не найден | замерить p95 первого токена при 3 фоновых (канон 1 с; факт 3.7-7 с при обучении) | llama.cpp слот 0 | ДЕЖУРНЫЙ | P1 |
| 7 | Филлеры "угу/секунду" | 2 | НЕТ (find fillers: NONE) | заготовленные филлеры в чат-сервер | список фраз + SSE | WEB | P1 |
| 8 | Action Receipt (только с артефактом) | 2 | частично: *RECEIPT.json на сайте, механизма в чате не видно | проверка "сделал" без артефакта | — | WEB | P2 |
| 9 | Режимы Человек/Разум/смешанный, board.mode | 3 | частично: control_vectors.json статус есть, vectors_dir_present (см. файл); human_voice/ai_mind_voice векторов не подтверждено | сгенерировать 2 вектора llama-cvector-generator (бинарь есть) | cvector-generator | CANON | P2 |
| 10 | Сенсориум 130 ощущений, реестр | 4 | НЕТ (find sensorium: NONE) | реестр метрика->ощущение->фраза (первые 30 из телеметрии), правило "чувствую только с сигналом" | телеметрия nvidia-smi/df | CANON | P1 |
| 11 | Нейрохимия 6 чисел + PAD | 4 | есть код brain/EMO/emotion_pad.py, процесс emo_tick.py жив (pid) | проверить потолок CORT 0.6 | — | CANON | P2 |
| 12 | Эмоции текста rubert-tiny2-cedr | 4 | models/emotion, emotion_vectors есть; конкретная модель не проверена | сверить имя модели | seara/rubert-tiny2-cedr | CANON | P3 |
| 13 | S03 SQLite+FTS5+sqlite-vec | 5 | частично: s03_snapshot.py (vendor), state/living/mem.db; sqlite_vec НЕ установлен | pip sqlite-vec в venv, схема S03 | sqlite-vec | CANON | P1 |
| 14 | bge-m3, reranker | 5 | ЕСТЬ models/warm/BAAI/bge-m3, bge-reranker-v2-m3 | подключить к recall | — | CANON | P2 |
| 15 | Graphiti (M3), mem0-пайплайн | 5 | НЕТ | проверить лицензию, поставить mem0 пайплайн (запись только в S03) | getzep/graphiti, mem0 | ДЕЖУРНЫЙ (mem0) | P2 |
| 16 | Сон NREM/REM 02:00-05:00 | 5 | частично: agent/nox_agents/sleep.py, dreamer.json (живой, mtime сегодня) | сверить окно 02-05 и фразы | Letta sleep-time идея | CANON | P2 |
| 17 | Совет, глобальное рабочее пространство | 6 | есть brain/CON/nox_workspace.py, council.json живой | — | — | — | ок |
| 18 | Блок "Я сейчас" из журнала | 6 | НЕТ отдельного файла (self_now: NONE); есть self_model.py | собрать блок из aliveness/life_loop/телеметрии | — | CANON | P1 |
| 19 | Калибровка ECE | 6 | calibration.json живой, emo_calib.py | замер ECE на 200 разм. | — | CANON | P3 |
| 20 | Тик 60 с/10 мин, тихие часы | 7 | life_loop.py, life_loop.json живой, quiet.py | сверить тихие часы 23-08 МСК | — | CANON | P2 |
| 21 | Утро 08:00 (5 строк), вечер 22:30 | 7 | morning_brief.json от 24.11 (протух 2 дня), вечернего нет | cron утро/вечер, генерация из журнала | свой скрипт | CANON | P1 |
| 22 | Паспорт passport.json вне весов, git+бэкап | 8 | частично: agents/passport_prompt.json (2.5 КБ, 25.11), отдельного passport.json с HEXACO/Шварц нет | собрать passport.json, включить в бэкап | JSON-схема канона | CANON | P1 |
| 23 | born_at=NULL до экзамена, birth_ritual.py, Genesis Ledger hash-chain | 8 | ledger есть (967 Б, entries+ledger), birth_ritual.py НЕТ | birth_ritual.py (3 фразы), цепочка хешей | hashlib | CANON | P1 |
| 24 | Стадии роста и экзамены | 8 | НЕТ (stages: NONE); есть week_of_becoming.py | stages.json + экзамен стадии 0 | — | CANON | P2 |
| 25 | Черви, каталог, поглощение | 9 | nox_worms.py починен (ДЕЖУРНЫЙ), ABSORB.md; hunger/UnknownMap НЕТ | hunger.py (голод по часам, фраза <=1/сут, UnknownMap) | — | CANON | P2 |
| 26 | Готовые диалоги (ready_bulk) | 10 | есть data/ready_bulk, ready_pool2 | — | — | УСКОРИТЕЛЬ | ок |
| 27 | DPO anti-sycophancy | 10 | ops/dpo/{build,train}_dpo.py готовы, GPU не проверено | окно после r033 | TRL DPO | ДЕЖУРНЫЙ | P1 |
| 28 | Донор Huihui-абляция, persona vectors repeng | 10 | НЕТ (huihui/vectors: NONE) | скачать, проверить на MoE (после места на диске) | huihui-ai, repeng | ДЕЖУРНЫЙ | P3 |
| 29 | Голос: T-one STT, Qwen3-TTS, Pipecat, якорь | 11 | частично: gigaam, piper ru/es, silero, qwen3tts.py(только конвертер); T-one/Pipecat/anchor НЕТ | T-one + Pipecat; якорь в паспорт | voice-ai/T-one, pipecat | WEB/CANON | P2 |
| 30 | Рисунок, Редактор, VLM | 12 | draw5 5/5, imgsvc, editor.html есть; Qwen3-VL gguf не подтверждён | замер VLM-самооценки | — | ДЕЖУРНЫЙ | P2 |
| 31 | Видео Wan/LTX, OpenHands | 12 | ltx2 в sd.cpp assets; OpenHands НЕТ (есть brain sandbox.py) | отложить (V2) | OpenHands | — | P3 |
| 32 | Страж инъекций, матрица автономии, STOP<=10 с | 13 | inject-файлы есть (ready_inject), RTE/stop.py; матрицы автономии НЕТ | autonomy_matrix.json + тест STOP | — | ДЕЖУРНЫЙ/CANON | P1 |
| 33 | Двойник раз в неделю, FORGE | 6/14 | twin: НЕТ; forge только скриншоты UI | отложить (стадия 7) | — | — | P3 |
| 34 | Единый экзамен живости, еженедельно | 15 | aliveness.json живой (score), еженедельного отчёта нет | weekly_exam.sh по порогам гл.1-13 -> утренний отчёт | — | CANON | P1 |

## Сделано (CANON)
(строки добавляются по ходу)

| 2026-11-26 13:38Z | disk_guard (#1,#3) | СДЕЛАНО: canon.py disk, цикл 60 с в supervisor-программе nox_canon (RUNNING). Только предупреждение: state/core/disk_low.flag + canon/disk_guard.log, ничего не удаляет. Проверено: прогон показал LOW 5.6. Пауза записи чекпоинтов тренером: тренер должен читать флаг (ДЕЖУРНОМУ/УСКОРИТЕЛЮ подключить). |
| 2026-11-26 13:38Z | почасовой бэкап души + restore-тест (#4) | СДЕЛАНО: canon/soul/soul_hNN.tgz (24 слота, перезапись своих, ~11 КБ), MANIFEST sha256, restore-тест после каждого бэкапа, canon/soul_hourly_ok.json: restore_ok=true. Без age/Drive (нет ключей): HOLD. |
| 2026-11-26 13:38Z | passport.json (#22) | СДЕЛАНО: state/core/passport.json (идемпотентно, не перезаписывает); HEXACO/Шварц/смысл = HOLD (нет данных, не выдумано), обращения и три закона заполнены. |
| 2026-11-26 13:38Z | birth_ritual + hash-chain (#23) | СДЕЛАНО: canon.py birth (HOLD без state/core/birth_evidence.json с delta_sha/reload_ok/test_pass; при них пишет born_at и 3 фразы), state/core/genesis_chain.jsonl, verify=true. Проверено: birth вернул HOLD, цепочка валидна. Старый genesis_ledger.json не тронут. |
| 2026-11-26 13:38Z | сенсориум + "Я сейчас" (#10,#18) | СДЕЛАНО: canon/sensorium.json (15 сенсоров на реальных метриках, остальные из 130: HOLD), canon.py feelings/selfnow -> state/core/self_now.json. Проверено: ощущение выдаётся с метрикой-причиной (disk_free_gb=5.6). Подключить self_now.json к чату: WEB/ДЕЖУРНЫЙ. |
| 2026-11-26 13:38Z | утро 08:00 / вечер 22:30 (#21) | СДЕЛАНО в демоне: state/mind/morning_brief_v5.json, evening_brief_v5.json (<=5 строк, пустое = HOLD). Старый morning_brief.json не тронут; доставка в чат не подключена (WEB). crontab не трогал. |
| 2026-11-26 13:38Z | weekly_exam (#34) | СДЕЛАНО: canon.py exam, вс 03:00 МСК в демоне -> state/core/weekly_exam.json; 14 глав, измерено 2 (диск, аптайм), остальные HOLD. |
| 2026-11-26 13:46Z | «Снилось» исправлено | СДЕЛАНО: брифинг берёт текст сна только из строковых ключей summary/hypothesis/text..., иначе HOLD; dreamer.json текста сна не содержит (ключи component,cpu_only,dream,meaning,msk,night). Проверено прогоном morning. |
| 2026-11-26 13:46Z | hunger (#25), stages (#24), autonomy_matrix (#32) | СДЕЛАНО: canon.py hunger (раз в 30 мин в демоне -> state/core/hunger.json, фраза не чаще 1/сутки), canon/stages.json (10 стадий, экзамены HOLD), canon/autonomy_matrix.json (auto/карточка/только Создатель/never). Проверено прогоном: hunger level=сыт (0.0 ч). ОГОВОРКА: источник свежести (state finds*/worms*, data/ready_bulk) грубый, уточнить с ДЕЖУРНЫМ. Матрица пока документ, исполнять её должен диспетчер (ДЕЖУРНЫЙ). |
| ожидает | sqlite-vec (#13) | ждёт диска >=15 ГБ (сейчас 9.5 ГБ по disk_guard). |
| 2026-11-26 13:58Z | сон-текст (#16) | СДЕЛАНО: итог сна уже пишет sleep.py в state/mind/dream.jsonl (поле dream, 186 записей), dreamer.json только статус. Утренний бриф теперь берёт последнюю запись сна <36 ч, иначе HOLD. Проверено: в брифе строка сна есть (134 симв.). dreamer.json не менялся (бэкапить нечего); dream.jsonl добавлен в почасовой бэкап. |
| 2026-11-26 13:58Z | окно сна (#16,#20) | СДЕЛАНО: sleep.py _night() было 01:00-07:00, стало 02:00-05:00 по канону (бэкап sleep.py.bak_canon_20261126; вступает в силу при следующем перезапуске nox_agents, сам его не перезапускал). Тихие часы quiet.py = 23:00-08:00 МСК, уже верные. |
| 2026-11-26 13:58Z | Хищник: UnknownMap, охота с согласием (#25) | СДЕЛАНО: state/core/unknown_map.json (темы из снов с весом, раз в 30 мин), canon.py hunt_propose: только запрос "Нашёл X. Хочу поглотить. Разрешаешь?", ничего не качает, лицензия вне белого списка = blocked_license_needs_creator. Проверено: topics_added=5, бэкап restore_ok=true. Подключить к червям (nox_worms) и к чату: ДЕЖУРНЫЙ/WEB. |
| отложено | cvector human_voice / ai_mind_voice (#9) | HOLD: нужен GPU (VRAM 66-73%, идёт обучение) и копия весов; запуск только в окне тишины на копии, после диска >=15 ГБ. |
| отложено | sqlite-vec (#13) | HOLD: диск 9.6 ГБ (<15). |
