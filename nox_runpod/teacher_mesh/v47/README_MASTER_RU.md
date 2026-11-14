# ⚡ NOX HELION V46 + V47 · R60 + REAL-WEIGHTS NIGHT FORGE

Пакет для **одного действующего NOX/OneHost**, 60 логических задач, одного S03, оригинального WEB V29.3. В архиве только исполняемые исходники, контрольные манифесты и локальные тесты, без скачанных весов. **Это не работающий Vast.ai runtime.**

## Идентичность

- Сервер: Vast.ai #60509551, 2×Tesla V100 32GB — источник истории; обязательна повторная физическая сверка.
- GPU0: текущий быстрый чат, не трогать. GPU1: один train/teacher после нативного допуска, если не занят.
- S03 M0–M7, C01–C08, GENESIS Ledger, имя/история/самомодель: не обнулять и не подменять.
- WEB: исходный V29.3 Frozen, SHA JSON в `source_contract/WEB_V29_3_LOCK.json`; не править без SHA и E2E. Источники V37–V43 сохраняются в PR #256.

## Порядок выполнения для OneHost

1. Восстановить авторизованный командный канал Vast.ai CLI `execute` / SSH / Jupyter или существующий `run_admin`. Не публиковать API/SSH токены.
2. Только чтение: `python -m night_v47.probe` в проверенной среде, GPU, диск, установленные пакеты, реальные PID и статус S03.
3. Выполнить резервное копирование и **тест восстановления** S03 + student + optimizer во внешнем хранилище. Исправить обнаруженные ранее ошибки планирования: R60-009 допускает backup прежде restore; R60-056 выполняется до R60-020.
4. Найти причину прежнего `train_error step=0`, не обновлять драйвер/Vast host CUDA вслепую. Использовать PyTorch wheel с реальным SM70 и CUDA12.x (вплоть до PyTorch 2.14 сборки cu126, затем only custom source build).
5. Только через существующие доверенные OneHost callback `night_v47.policy.assess(snapshot)` -> `stage_native_smoke`, допуск GPU1 при реальной памяти, резерве диска и валидных правах.
6. На локальных HF trainable весах (НЕ GGUF) исполнять **direct base tensor smoke** в изолированную staging папку, 1..20 шагов; trainer сохраняет optimizer + новый полный весовой checkpoint, SHA изменённых параметров, делает reload и независимый holdout. `NOX_ONEHOST_NATIVE_APPROVED=1` — дополнительный локальный индикатор, настоящую проверку прав и подписи делает OneHost. См. `night_v47/direct_weights_smoke.py`.
7. При FAIL/регрессии: HOLD, протокол причины, без promote в чат; при PASS — следующая ограниченная серия с новым approval+readback. При нехватке места — перенос в cold vault, NO-LOSS.
8. Запускать 60 задач **через существующий** OneHost, не в виде 60 тяжёлых процессов на GPU. 8 CPU (первый консервативный лимит), GPU1=1, GPU0 чат.

## Что конкретно проверено

- `python3 -m unittest discover -s tests`: **26 source-only unit tests PASS** (Python 3.13), проверка DAG 60/60 без циклов.
- `python3 -m py_compile` модулей V47: PASS.
- Оригинальный WEB и архив V29.3 не менялись.
- Физический GPU/trainer smoke на Vast **не выполнялся** (нет работающего канала OneHost из этой среды). Последний наблюдавшийся `train_error step=0`, диск ниже 20GB резерва. Запуск обучения не подтверждён.

## Ссылки

- https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256
- https://docs.google.com/document/d/18YLAo_Cja3HJKZn6qr57P-zsm0-AHcx2aag0rgSjwS4/edit
- https://dev-discuss.pytorch.org/t/notice-cuda-12-6-wheels-will-no-longer-be-published-from-pytorch-2-15-drops-maxwell-pascal-volta/3432

**NO-LOSS:** никогда не удалять память, trainer optimizer или checkpoints без независимой резервной копии, разрешения и restore. Не объявлять NOX сознательным на основании самописного текста и не называть GGUF teacher raw downloads поглощением собственных параметров.
