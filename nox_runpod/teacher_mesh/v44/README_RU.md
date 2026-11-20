# NOX V44 · EXECUTOR #2 · ночной FORGE / R60 · только существующий OneHost

**Статус:** готовый код для интеграции, **не установлен на Vast**. Живого OneHost receipt или тренировочного checkpoint из этой поставки нет. Не запускать самодеятельный CLI/демон, второй чат или GPU scheduler. Не использовать RunPod или новые платные машины.

## Физическое назначение

`overnight_forge.py` выполняет **настоящий** PyTorch forward/backward/optimizer.step() на переданных из существующего OneHost студенческих весах, тренажёре, лицензированном pre-tokenized корпусе. На GPU1 только после проверки SM70, CUDA12, FP16, дискового и RAM резерва, optimizer state, SHA исходных весов, подписанного owner разрешения, STOP, полного внешнего восстановления S03 и checkpoints. GPU0 остаётся за основным чатом. Один активный тренер, никаких автоматически новых учителей/скачиваний.

Сразу после optimizer steps вычисляются реальные SHA всех исходных/изменённых тензоров. Для полного успеха нужны независимое уменьшение holdout loss, regression PASS, сохранение optimizer+weights, реальный checkpoint SHA и перезагрузка checkpoint. Результат — **только кандидат** без переключения основного NOX. Неуспех возвращает контроль нативному rollback; запись `URGENT_ROLLBACK_FAILED` запрещает дальнейшую работу.

`cpu_test_mode=True` существует только для проверок алгоритма на игрушечной модели и возвращает `CPU_UNIT_TEST_REAL_TENSOR_UPDATE`, **не** live-обучение NOX. Никакие числа тестов не переносить в продакшен.

`r60_executor2.py` создаёт 30 уникальных подготовленных R60-021–040,051–060 и `merge_without_overwrite()` для существующего мастера. Не записывает их сам и не имитирует нативные task_ids. Изменять `NOX_R60_MASTER.json` разрешено только единственному владельцу OneHost через CAS + native readback; №1 задачи не перезаписываются.

## Максимальная скорость без потери данных

Использовать фактические измерения: изменять microbatch/gradient accumulation **только между checkpoint**, не при активном optimizer.step; заранее токенизировать и упаковывать лицензированные короткие примеры на CPU, `pin_memory`, dataloader workers — лишь если измеренные RAM/SSD позволяют. GPU compute target 85–95% на **допущенной** задаче, не принудительно 100% VRAM. GPU0 — защищённый чат, GPU1 — один тренер. Снижать microbatch после OOM, возвращать исходный checkpoint при регрессии. S03 и GENESIS — одно достоверное хранилище подтверждённой истории.

Для 35B AdamW full weights 2×V100 по 32ГБ и известный ранее RAM ~96ГБ недостаточны; нужна предварительно найденная и проверенная меньшая обучаемая модель NOX или нативно проверенный ZeRO/FSDP offload с реальными бюджетами, но никакой молчаливой замены студента. GGUF Q4 учителя не являются обученными весами NOX.

## Локальная приёмка

`python -m unittest -v test_overnight_forge.py test_r60_executor2.py` — только CPU unit-tests, никакого живого CUDA/Vast/P02/S03.

## Обязательные живые входы OneHost

Реальные GPU/UUID/PID, CUDA12 ABI; student model state SHA и optimizer state, train/holdout SHA; offsite checkpoint + проверенный restore; свободный диск >= max(20GB, 2×checkpoint+2GB); owner-signed request и STOP; independently held-out benchmark, checkpoint+optimizer reload и S03 GENESIS append/readback. Любой пробел => HOLD, никаких фальшивых PASS.

Источники: draft PR #256; V37 `nox_v37/native_admin.py`, `admission.py`; V39 `learning_cycle.py`; V41 `training/recovery_plan.py`, `priority_autonomy.py`; V42/V43 Resource Brain.
