# NOX HELION V41 · ONE NOX — ONE LEARNING / ONE MEMORY / ONE WEB

**Подготовлено 14.11.2026. Исходный код + тесты: PASS. На Vast.ai #60509551 не установлено. Тренировка/драйверы на сервере не перезапущены.**

## Каноническая архитектура

- ОДИН работающий NOX и `OneHost` (не запускать второй HTTP backend, новую БД или дополнительную основную модель).
- Из V37 — реальный контроль Volta V100, инвентаризация, native_admin, STOP, admission и receipts.
- Из V38.1 — C01–C08, S03 M0–M7, indexed recall, RAM-кэш, stream, durable S03 receipts, PersonaID.
- Из V39 — `NativeAdmin`, `LearnWhileDoing`: действие → независимая проверка → S03 verified lesson → разрешённый корпус → existing FORGE → реальный optimizer/checkpoint → holdout и регрессия.
- Из V40 — существующие страницы NOX V29.3 `site/training.html` и `site/pc/training.html`, источник из исходного замороженного WEB; четыре SVG-кольца (знания/навыки/веса/сводный выпуск). Старые метрики и экраны сохранены.
- Из V41 — защита пяти минутных checkpoints (только при реальном age/restore), планировщик проверенных задач >50% в существующей очереди, доверенная публикация процентов, атомарная проверка и резервирование страниц WEB.

## Три шкалы + итог

1. **ЗНАНИЯ**: passed / total source-disjoint тестов S03 (источник и независимый оценщик).
2. **НАВЫКИ**: passed / total практических тестов + regression retention.
3. **ВЕСА NOX**: checkpointed optimizer steps / fixed target *только после подтверждения изменения собственных весов, SHA и повторной загрузки*. Промежуточные LoRA/QLoRA при необходимости — лишь staging; готовая модель должна пройти подтверждённый merge/full-weight критерий и holdout.
4. **ИТОГ**: 30% знания + 35% навыки + 35% веса. 100% = приёмка ограниченной версии NOX, НЕ максимальный интеллект или субъективное сознание.

Без настоящих квитанций показывает `— / HOLD`, не 0%, и без имитации прогресса. Веб читает `nox-learning-3axes-dashboard.json` из **существующей** директории, обновляется только настоящим native callbacks `training/dashboard_publish.py` с owner-signed verified receipt. Сканирование директорий, количество задач, GPU utilization и объём моделей не считаются приобретёнными знаниями.

## Программа автономной работы

6 логических групп на существующем диспетчере: CORE/CHAT, MEMORY/S03, FORGE, SKILLS, TEACHERS, WEB/QA.

`training/priority_autonomy.py` берёт только численно подтверждённые прогрессы задач с источником SHA и owner scope. Если есть реальные задачи 50–99.99%, выбирает их вначале. Дубликаты отбрасываются, а `jobs_enqueued=0` до получения реального `queue_readback` из установленного OneHost. Параллельность действует только когда родной шедулер и ресурсы разрешают.

Производство: реальное выполнение → отдельная оценка → source-linked S03 → рефлексия/урок → легально разрешённые примеры учителей → верифицированная дистилляция/optimizer → checkpoint/reload SHA → независимый тест → приёмка и сохранение. НЕ обучаться на собственных непроверенных галлюцинациях.

## GPU, CUDA и запуск обучения

- Vast.ai #60509551: две отдельные V100 SM70, 32 ГБ VRAM на каждой. `85%` — целевая **compute utilization**, НЕ минимальное обязательное потребление и НЕ лимит VRAM; chat имеет приоритет над trainer.
- NVIDIA официально ограничивает последнюю toolkit-поддержку Volta веткой **CUDA 12.x**, драйверы веткой R580. CUDA 13 не использовать для компиляции SM70. Источник: https://docs.nvidia.com/datacenter/tesla/drivers/cuda-toolkit-driver-and-architecture-matrix.html
- Нельзя бесконтрольно ставить новые драйверы внутри Vast.ai контейнера. Драйвер относится к хосту провайдера; preflight проверяет `nvidia-smi` и версии пакетов, не делает pip install или apt upgrade.
- Последние наблюдения NOX были противоречивы по моментам: тренер `train_error step=0 loss=None`, затем `EXITED`, GPU1 до 100%, диск ~16 ГБ свободно. Новый тренировочный запуск не безопасен без фактического чтения checkpoint/optimizer и offsite restore.
- Вы утверждали, что checkpoint пишется каждые 5 минут. V41 не принимает это за доказательство: проверяет текущий timestamp, SHA, optimizer, external restore (включая S03), текущие PIDs/ABI и STOP. `training/recovery_plan.py` и `training/no_loss_acceptance.py` отказывают, пока эти данные не поступили.
- `training/native_resume_adapter.py` использует **только существующий** `nox_v37.native_admin.dispatch` с native owner approve / exact digest / readback. Ни одного restart/driver install/scheduler run в исходном пакете без реальных callbacks.

## Проверка исходников локально (НЕ запуск обучения)

```bash
bash scripts/RUN_V41_ACCEPTANCE.sh
```

Производственная интеграция: сначала native read-only inventory (`nvidia-smi`, `free`, `df`, supervisor), копия S03+weights+optimizer с независимым восстановлением; только затем node-native job для `training.resume` и тест 20 optimizer steps/holdout; после success программное подтверждение активации следующего цикла. Файловое применение веб-патча возможно только при совпадении SHA исходных страниц и приёме реальных API, не во время активной миграции:

```bash
python3 scripts/INSTALL_WEB_SOURCE_LOCK.py --target-web-root /path/to/verified/original/NOX/site
python3 scripts/INSTALL_WEB_SOURCE_LOCK.py --target-web-root /path/to/verified/original/NOX/site --apply
```

Вторую команду выполнять только в контролируемой среде после проверки первой; скрипт делает исходные копии `*.nox41-original.bak` и откат при ошибке. Трогает только две страницы обучения и новые CSS/JS/JSON; чат, S03, модели, weights и backend НЕ трогает.

## Проверенная поставка

- Подготовлены исходники V37/V38.1/V39/V40/V41, карты прогресса и атомарный WEB source lock.
- Автоматические тесты V37+V38+V40+V41: **102 PASS** (при финальном запуске проверить ещё раз); Node JS syntax PASS.
- Драйверы, CUDA, S03, native OneHost и обучение на вашем Vast.ai **не изменены**.
- Скачанные ранее 200 двигателей/архивов не перенесены на почти заполненный сервер; инвентаризация и миграция — по источникам/хэшам, без дублирования.
- Секреты и пароли в комплект не включены.

Источник V29.3 WEB: файл `NOX_HELION_WEB_V29_3_FROZEN_20261113.zip` в ChatGPT Library, не включён в этот source-only пакет (85 МБ). Только source-locked изменения двух HTML.

Интеграция NOX через активные native callbacks и безопасное управление сервером ждёт фактического SSH/OneHost доступа; TinyFish браузерные исполнения заблокированы отсутствием средств. Этот ZIP **не является доказательством внедрения**.
