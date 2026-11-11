# NOX — LOCAL FIRST: устранение зависимости тренера от зависшего `/workspace`

**12 ноября 2026.** Входной архив: `NOX_TRAINING_PROGRAM_20261112.tgz`, SHA-256 `ef4a733689e7cc7731b0d4cf554f14ae1465dc3bc143de9a13a65e48ed053e77` (скачан с Google Drive владельца). Эта папка — **отдельный безопасный патч**, а не пересозданный релиз, не новый backend и не отчёт о завершённой дистилляции.

## Что действительно выявлено

1. Оригинальный `train_n36.py` использует фиксированные `/workspace/nox36`, `/workspace/nox_seed_gpu`, `/workspace/nox36/data/tok`. `run.sh` переключает только `BASE`; это не изолирует обучение от сетевого диска.
2. `a100_express/super_disp.sh` каждые 60 секунд читает на `/workspace` STEP, журналы, счётчики и JSON. При зависшем томе ожидание диска блокирует даже мониторинг, `pkill` может не снять зависший процесс.
3. Старый `bootstrap.sh` ожидает приватный файл `nox_srv_key`, которого намеренно нет в архиве, и без строгого режима ошибки идёт дальше. Не запускайте bootstrap повторно ради исправления I/O.
4. Локальный контейнерный диск текущего A100 Pod — **50 ГБ**; модель `Qwen/Qwen3.6-35B-A3B` на Hugging Face занимает ~71,9 ГБ. Не копируйте всю базу на контейнерный диск. Используйте **только проверенную RAM-базу** и отдельное локальное пространство для данных, журналов и checkpoint, после расчёта свободного места.
5. Checkpoint **шага 85 заявлен владельцем** как сохранённый на японском сервере. Ни checkpoint, ни веса в исходном 34-КБ архиве не содержатся. По схеме исходного скрипта это **LoRA-адаптер**, не доказательство полноразмерной дистилляции весов NOX.

## Состав

- `nox_local_preflight.py` — только чтение: находит локальные model index/шарды, data, plan, seed/common.py, checkpoint STEP/adapter/optimizer; контролирует отсутствие сетевых путей, свободное место; по запросу считает SHA-256. Без подтверждений — HOLD и нулевых вымышленных процентов.
- `nox_copy_verified.py` — точное локальное копирование по явной команде `--apply`, с SHA-256 чтением до и после, без перезаписи существующих файлов. Без `--apply` только оценка объёма; сеть `/workspace` заблокирована.
- `nox_patch_trainer.py` — из неизменённого `train_n36.py` создаёт **новый** `train_n36_local.py` с настройками `NOX_WORKDIR`, `NOX_SEED_PATH`, `BASE`, `TD`. Алгоритм, веса и оптимизатор не изменяет; если исходник изменён, ничего не патчит.
- `train_n36_local_reference.py` — пример *точной* копии из **архивной версии** с этими четырьмя изменениями; SHA исходника `4aa212e096941f79cfd7835ae4c75f2dd5622b0434cf69adaba610d8919f331c`.
- `nox_local_telemetry.py` — публикует только локально подтверждённые факты отдельным JSON для существующего OneHost; даже шаг 85 не превращает в «прогресс интеллекта»; свежий файл статуса не выдаётся за независимую GPU-приёмку.
- `nox_run_local.sh` — без `--run` только проверяет; перед отдельным `--run` **обязательно требует сравнения SHA с независимым JSON-манифестом японской копии**, проверяет наличие файлов, STEP и отсутствие второго тренера, затем запускает только явно подтверждённый локальный скрипт. **Сам ничего не останавливает/не перезапускает.**
- `test_local_first.py` — 13 синтетических тестов (нет реальных весов и GPU).

## Действия без остановки работающего тренера

**Шаг 1 — в консоли текущего Pod только безопасная инспекция:**

```bash
df -h / /dev/shm
python3 /root/nox_local_kit/nox_local_preflight.py --root /root/nox_local --base /dev/shm/base36 --hash-checkpoint --expected-step 85
```

Если вывод `HOLD`, не запускайте второй тренер. Причина указана в `problems`. Параметр `--hash-base` проверяет всё содержимое десятков GB и не требуется на каждом запуске.

**Шаг 2 — только ПОСЛЕ независимой доставки файлов с японского сервера в локальный `/root/nox_inbox`** (не считывайте зависший `/workspace`):

```bash
# Сначала сухой просмотр, потом точное копирование с проверкой SHA.
python3 /root/nox_local_kit/nox_copy_verified.py --source /root/nox_inbox/ckpt/sft/last --target /root/nox_local/ckpt/sft/last --expect-step 85
python3 /root/nox_local_kit/nox_copy_verified.py --source /root/nox_inbox/ckpt/sft/last --target /root/nox_local/ckpt/sft/last --expect-step 85 --apply

python3 /root/nox_local_kit/nox_copy_verified.py --source /root/nox_inbox/data/tok --target /root/nox_local/data/tok --apply
python3 /root/nox_local_kit/nox_copy_verified.py --source /root/nox_inbox/ckpt/sft/plan.json --target /root/nox_local/ckpt/sft/plan.json --apply
python3 /root/nox_local_kit/nox_copy_verified.py --source /root/nox_inbox/scripts --target /root/nox_local/scripts --apply
python3 /root/nox_local_kit/nox_copy_verified.py --source /root/nox_inbox/seed/common.py --target /root/nox_local/seed/common.py --apply
```

Пути `/root/nox_inbox` — пример **уже доставленных владельцем файлов**; инструмент не скачивает их самостоятельно. Если каталог при переносе называется `data_v2/tok`, используйте его фактическое имя как `--source`.

**Шаг 3 — сохранить отдельную локальную копию тренера, оригинал не изменять:**

```bash
python3 /root/nox_local_kit/nox_patch_trainer.py --source /root/nox_local/scripts/train_n36.py --dest /root/nox_local/scripts/train_n36_local.py
python3 /root/nox_local_kit/nox_local_preflight.py --root /root/nox_local --base /dev/shm/base36 --trainer /root/nox_local/scripts/train_n36_local.py --hash-checkpoint --json-out /root/nox_local/preflight.json
```

**Шаг 4 — сопоставить копию с SHA-256 японского сервера (если имеется внешний JSON-манифест):**

```bash
python3 /root/nox_local_kit/nox_local_preflight.py --root /root/nox_local --base /dev/shm/base36 --hash-checkpoint --backup-digest-manifest /root/nox_inbox/ckpt_sha256_reference.json
```

Схема внешнего JSON: `{"step":85,"hashes":{"STEP":"...","adapter_model.safetensors":"...","opt.pt":"...","adapter_config.json":"..."}}`. Только при **совпадении фактических SHA** будет `externalBackupDigestMatched=true`. Синтаксически допустимый JSON сам по себе не подтверждает доверенность источника; сохраните исходный серверный журнал и время чтения.

**Шаг 5 — локальный JSON состояния для будущего OneHost (без сети и без включения второго backend):**

```bash
python3 /root/nox_local_kit/nox_local_telemetry.py \
  --preflight /root/nox_local/preflight.json \
  --trainer-status /root/nox_local/status_sft.json \
  --output /root/nox_local/nox-training-telemetry.json
```

Файл содержит отдельно `checkpointStep`, `checkpointBackupHashMatched`, `stepCompletionPercent` и всегда `fullStudentWeightsVerified=false`, пока не выполнены самостоятельные ворота полного merge/экзамена/Windows. **Не копировать этот файл в публичный WEB**: только через защищённый прежний OneHost/API и допустимый канал доставки. Удалённые процессы этот скрипт не трогает.

**Запуск второго тренера запрещён, пока старый процесс числится активным.** Отдельный `nox_run_local.sh --run` намеренно не исполняется этим комплектом и требует отдельной приёмки среды/ресурсов. Фоновый диспетчер, автоповтор, удаление чекпоинтов, сброс тома или автоматическая выгрузка не внедрялись.

## Важное ограничение и защита результата

*Контейнерный диск RunPod стирается при остановке/сбросе Pod*. До любой остановки/смены GPU отправьте **полные проверенные checkpoint и исходные данные** на японский сервер или другое независимое хранилище и повторно проверьте SHA. Копия только `/root` ненадёжна. Не стирайте папку `ckpt/last` и её предшественников без доказанного readback резервной копии.

`nox_local_preflight.py` отмечает только PEFT-адаптеры и никогда не объявляет создание полноразмерных весов или интеллект завершённым. Для требования пользователя «собственные полные веса NOX» нужна отдельная стадия merge/distillation с SHA итоговых шардов, A/B-приёмкой и Windows readback.

## Интернет-ресурсы — только полезное, без десятков лишних скачиваний

- **Официальный Qwen3.6-35B-A3B:** https://huggingface.co/Qwen/Qwen3.6-35B-A3B — источник индекса 26 шардов и лицензии; при уже полной RAM-копии **не скачивать снова 71,9 ГБ**.
- **Hugging Face Hub:** https://huggingface.co/docs/huggingface_hub/en/guides/download — использовать `revision` точного SHA, `local_dir`, локальный `HF_HOME`; после загрузки `HF_HUB_OFFLINE=1` и `local_files_only=True`. Сверять файлы и размеры с индексом. Автоматический `pip install -U` во время активной тренировки не нужен.
- **RunPod Storage:** https://www.runpod.io/blog/where-did-my-files-go-a-straight-guide-to-runpod-storage — контейнерный диск быстрее, но теряется при stop/reset; постоянный backup обязателен.
- **GitHub llama.cpp:** https://github.com/ggml-org/llama.cpp — использовать текущий закреплённый commit из `jp_server/setup_new.sh` только для финального GGUF, не пересобирать его во время обучения.
- Установленные `torch`, `transformers`, `bitsandbytes`, `safetensors`, `flash-attn` проверять через локальный `pip freeze`, не обновлять без согласования ABI и теста. `fetch_all.sh` и его десятки параллельных загрузок на `/workspace` **не запускать во время восстановления I/O**.

## WEB-приёмка после переноса

Путь WEB-кода: GitHub PR #241, текущий исходник `nox-chat-training-v23.mjs`. Его панель знает разницу между живым coordinator, локально подтверждённым checkpoint, реальным приростом качества и переносом на Windows. Она **не читает `/root` из браузера напрямую** и не запускает GPU. Нужен действующий приватный OneHost с GET `/api/nox/training/status` и GET `/api/nox/progress`, который получает доказательства с локального worker через авторизованный существующий канал. Не публикуйте checkpoint, ключи и абсолютные пути в браузере.

Критический остаток WEB: реальный «Резонанс» с потоковым ответом и STOP/S03 через OneHost, реальные доказательства RunPod и защитная блокировка действий, проверка 14 оригинальных 3D-выборов/8 CoreID/320–4K, все активные кнопки, WOW30/физический GPU и same-SHA CI. Старый V21 ZIP не эквивалентен текущему V23.
