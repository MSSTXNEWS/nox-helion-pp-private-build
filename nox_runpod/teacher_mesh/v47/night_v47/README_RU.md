# NOX V47 · NIGHT FORGE ADMISSION — НОЧНОЕ УСКОРЕНИЕ БЕЗ ФАЛЬШИВОГО УСПЕХА

Текущий архив содержит код для интеграции в **существующий OneHost**, а не работающий второй сервер или самостоятельный scheduler. Существующий чат на GPU0, S03, STOP, история и checkpoints сохраняются.

## Четыре шага

1. На живом Vast.ai #60509551 выполнить только чтение `python -m night_v47.probe` **через уже авторизованный OneHost/SSH/Jupyter/CLI**. Убедиться в двух настоящих V100 SM70, RAM/VRAM, процессах тренера и наличии диска.
2. Проверить ошибку `train_error step=0`, совместимость текущего PyTorch со `sm70` и CUDA12.x/FP16. **Никакого слепого `pip upgrade torch` и никаких обновлений host-драйверов из контейнера.** На V100 PyTorch 2.15+ предустановленные бинарники без CUDA12.6 не поддерживают SM70; используйте проверенную версию с cu126 либо соберите из исходников отдельно (https://dev-discuss.pytorch.org/t/notice-cuda-12-6-wheels-will-no-longer-be-published-from-pytorch-2-15-drops-maxwell-pascal-volta/3432).
3. Сохранить восстановимую копию student (не GGUF-only), optimizer, S03, зафиксировать SHA и проверить внешний restore, лицензию и независимый holdout. Проверять запас диска >= ожидаемый checkpoint + 20GB, на GPU1 >=3GB запаса. Если текущий student 35B Q4 GGUF — он только для инференса и не годится для full-parameter training. Не подменять его без тестов.
4. `night_v47.policy.assess(native_snapshot)` даёт READY только при всех проверках; `night_v47.native_cycle.stage_native_smoke(...)` передаёт **один** разрешённый smoke в доверенный OneHost. Затем штатный FORGE выполняет optimizer.step и сохраняет проверяемые checkpoint/benchmark. Следующий цикл — только после фактического шага, SHA и reload. STOP в любой момент.

Текущий статус: **SOURCE_READY / LIVE_VAST_HOLD**. В подготовленной среде ChatGPT нет работающей авторизации/канала запуска на Vast.ai. Ни один optimizer step, обновление GPU-драйвера или перезапуск НЕ выполнялись этим кодом.

## Сценарии работы

- Пока нет доступа, разрешено: обзор каталога, исходников, тестов, независимый benchmark corpus; нельзя подтверждать изменённые веса.
- Пока есть доступ, но нет проверенного offsite backup: read-only preflight и подготовка восстановления, **без обучения**.
- После полного допуска: тест 1-20 шагов, checkpoint, затем версия независимого экзамена и только после успешных receipt дальнейший тренинг с паузами для S03 и чата.
- На 2xV100: GPU0 — существующий чат; GPU1 — максимум один допущенный train или учитель; CPU — до 8 лёгких задач согласно показателям.
- **Субъективное сознание не заявляется; functional self-model NOX сохраняется в S03.**

## Исполняемый прямой smoke-тренер (без LoRA)

`night_v47/direct_weights_smoke.py` действительно выполняет AdamW+FP16 GradScaler для **последнего слоя исходной HF-модели**, не создавая адаптеров. Полученные веса размещаются в новой изолированной папке, исходные и текущий чат не изменяются. Он фиксирует SHA изменённых базовых тензоров, повторно загружает checkpoint, сравнивает независимые holdout loss, сохраняет optimizer state и не активирует модель автоматически. Это **частичное обновление параметров настоящей модели**, а не подтверждение полного 9B/35B distillation.

Допуск: только доверенный OneHost должен обеспечить `NOX_ONEHOST_NATIVE_APPROVED=1` после проверки подписи/прав, а оператор передаёт `--execute` и конкретные локальные пути. Признак окружения сам по себе **не является доказательством авторизации**. Данные train/holdout должны быть source-disjoint и иметь `rights_verified:true` и `privacy_approved:true`; исходный студент обязан быть локальным HF checkpoint (не GGUF), перед запуском внешний backup и native admission. См. `night_v47/policy.py`.

**Образец команды (НЕ запускалось на Vast):**

```bash
python -m night_v47.direct_weights_smoke --student /workspace/nox/student_hf --train /workspace/nox/datasets/approved_train.jsonl --holdout /workspace/nox/datasets/sealed_holdout.jsonl --out /workspace/nox/checkpoints/staging-v47-001 --steps 1 --execute
```

Не выполняйте с `sudo`, не устанавливайте PyTorch без сверки, не совмещайте с работающим тренером на GPU1. При неготовых условиях возвращает `HOLD`, не PASS.
