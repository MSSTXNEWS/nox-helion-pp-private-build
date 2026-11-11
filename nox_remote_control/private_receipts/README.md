# NOX — защищённый обратный канал диагностики

Цель: ChatGPT записывает read-only задания в существующие GitHub очереди NOX; изолированные наблюдатели Vast.ai и RunPod сохраняют квитанции локально. Этот модуль забирает **только эти квитанции**, удаляет лишние детали и отправляет в существующий **приватный** репозиторий `MSSTXNEWS/runpod-control` по `receipts/<node>/<task-id>.json`.

Поддерживаются ноды `vast-60254538` и `runpod-5f3j8hwyicc0bp`. Разрешены только `gpu`, `disk`, `processes`, `checkpoints`, `health`. Результаты ограничены измерениями и количествами. Нет команд shell, root RPC, STOP, управления тренером или доступа к приватной памяти.

### Однократная авторизация

В настройках GitHub создайте **fine-grained Personal Access Token**: только выбранный репозиторий `MSSTXNEWS/runpod-control`, разрешение **Contents: Read and write**; срок действия ограничен. Никаких токенов в чат. В каждом серверном терминале отдельно запустить установщик — он запросит токен без отображения и сохранит в root-only config. Установщик проверяет SHA Git blob и `py_compile`. Не запускать его без проверки источника.

Vast.ai:
```bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/ef1d8105cb8ceeebdd0c3bb663b71ede0f9b8dbd/nox_remote_control/private_receipts/install_private_receipts.sh -o /tmp/nox-private-channel.sh && bash /tmp/nox-private-channel.sh vast-60254538
```

RunPod:
```bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/ef1d8105cb8ceeebdd0c3bb663b71ede0f9b8dbd/nox_remote_control/private_receipts/install_private_receipts.sh -o /tmp/nox-private-channel.sh && bash /tmp/nox-private-channel.sh runpod-5f3j8hwyicc0bp
```

### Acceptance
- Private repository remains non-public.
- Existing observer emits receipt for a fresh nonexpired ID.
- Sidecar returns `PRIVATE_RECEIPTS_STARTED`, and its log reports `NOX_PRIVATE_RECEIPTS ... count 1` or more.
- File `receipts/<node>/<id>.json` available to ChatGPT via connected GitHub; no shell logs or private data.
- RunPod/Vast process, checkpoint and training owner unchanged.
- A private repo token is a security credential, never include it in GitHub source, logs, chat, command args, screenshots or PR.
- Failures must retain HOLD, no fake PASS.

This is **scoped read-only diagnostic control** and not unrestricted system access.
