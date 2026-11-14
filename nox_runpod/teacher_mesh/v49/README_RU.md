# NOX HELION V49 — защищённый исходящий мост к существующему OneHost

**Состояние на 14.11.2026: SOURCE VERIFIED, LIVE HOLD.** Проверка GitHub Actions №43594171493: 28/28 unit-тестов PASS на тестовых native callbacks; ни одна команда на Vast.ai #60509551 этим пакетом пока не запускалась. Не путать CI с настоящим подключением.

## Что построено

```text
ChatGPT (существующий GitHub connector)
   ↕ GitHub API (HTTPS; текущая ветка PR #256)
coordination/bridge/NOX_BRIDGE_INBOX.json
   ↓ один poll/tick ТОЛЬКО в существующем планировщике NOX
OneHost V39.NativeAdmin (ACL + STOP)
   ↓ существующие, внедрённые владельцем native callbacks
S03 (атомарный claim nonce + проверенный аудит)
   ↑ результат без сырых личных данных, логов и секретов
coordination/bridge/NOX_BRIDGE_RECEIPTS.json
   ↑ читает ChatGPT через GitHub plugin
```

**НЕ создаётся:** другой backend, HTTP/MCP listener, LLM, база, очередь, watchdog, cron, shell-агент, второе хранилище памяти. GitHub — транспорт, не источник прав и не доказательство реального исполнения.

### Реализованные гарантии

- Точный Vast instance ID `60509551`, GitHub repo и feature branch PR #256.
- Один запрос не более 300 секунд, HMAC-SHA256 подписывает каждый байт канонического тела. 32+ байта секретного ключа обязательны, в репозиторий он не попадает.
- `NativeAdmin` уже существует в `v39/native_control.py`; разрешены только его `READ`-операции (например, `server.status`, `nox.queue.status`, `nox.s03.status`). Удалённые `nox.training.resume`, `nox.queue.enqueue`, START/STOP контейнера, `run_shell` и всё остальное запрещены **на уровне кода**.
- Предварительно обязательны native STOP, scope ACL, атомарная и долговечная уникальность `request_id` в существующей S03; после каждого вызова — S03 audit+readback. Иначе HOLD.
- Публикуются только `state`, SHA-256, подпись квитанции, факт native readback и флаг долговечности аудита. Сырые `stdout/stderr`, токены, IP, пути и частные воспоминания в GitHub НЕ сохраняются.
- GitHub transport допускает только два фиксированных файла и HTTPS/TLS с обычной проверкой CA; запрещены редиректы с Authorization. Запись receipts — по текущему GitHub SHA, без слепых повторов и потери чужих изменений.
- Все проверки против заглушек реализованы в `tests/test_onehost_bridge.py`.

## Привязка в работающем OneHost: обязательная процедура

1. Подтвердить физический канал владельца к **работающему** Vast: SSH с уже доверенным ключом либо HTTPS Jupyter с доверенным сертификатом. Не использовать `vastai execute`: на RUNNING он отвечает HTTP 400; не останавливать сервер. Никаких HTTP-запросов с Jupyter token.
2. Проверить текущий SHA установки, S03, STOP и baseline P02. Сверить доступное место (`df`) и внешний backup перед любыми следующими операциями. Мосту хватает CPU и он ничего не скачивает из HF.
3. Привязать `NativeAdmin(HostAdmin(...))` к действительным, уже зарегистрированным функциям OneHost. Передать `NativePorts(stop,claim_request,append_s03,verify_s03)`. `claim_request(id,sha)` **обязана атомарно сохранять идентификатор в единой S03** между перезапусками; заглушки недопустимы.
4. Хранить независимый `NOX_BRIDGE_HMAC_KEY` (случайный, минимум 32 байта) в защищённом хранилище доверенного signer и существующего OneHost. Не использовать вместо него Vast API секрет `NOX2`; `NOX2` уже работает и не требует замены. Отдельный ограниченный по репозиторию GitHub token с правом Contents read/write нужен серверу, чтобы сохранить только обезличенные receipts. Не помещать токены в чат, исходники, Notion и GitHub logs.
5. Из существующего безопасного scheduler вызывается только `poll_existing_onehost(bridge, github_token=...)` с периодом не более 120 с. **Никаких независимых daemon / scheduler.** Если owner/native/S03 нет — bridge не активировать.
6. Через доверенную подписывающую сторону отправить **ровно один** read-only `server.status`; проверить подпись, receipt в GitHub, native report и S03 readback; затем STOP/ACL/replay/expired и после-restart проверки. До этого считать `HOLD_NATIVE_INTEGRATION`.
7. Запись и управление реальными заданиями R60 идут **только через** `v47/control/dispatcher.py` и native OneHost approval+queue readback. Этот мост не подменяет их, `registered_count=0` до физических квитанций.

Код импорта существующего runtime (не отдельный сервер):

```python
from nox_runpod.teacher_mesh.v39.native_control import NativeAdmin, HostAdmin
from nox_runpod.teacher_mesh.v49.onehost_bridge import OutboundOneHostBridge, NativePorts
from nox_runpod.teacher_mesh.v49.github_https import poll_existing_onehost

# Только штатный код OneHost имеет право подставлять native callback
# и извлекать секреты из защищённого vault. Не запускать из недоверенного чата.
bridge = OutboundOneHostBridge(native_admin, native_s03_ports, bridge_hmac_key)
result = poll_existing_onehost(bridge, github_token=repo_scoped_token)
# existing_scheduler сохраняет status/receipt и обрабатывает HOLD.
```

## Контрольные ссылки

- [PR #256](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256)
- [Вариант без shell: V39 NativeAdmin](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/feature/nox-v38-synaptic-brain-20261114/nox_runpod/teacher_mesh/v39/native_control.py)
- [Исходная R60 матрица](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/feature/nox-v38-synaptic-brain-20261114/nox_runpod/teacher_mesh/v47/control/TASKS_60_V46.json)
- [GitHub CI](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43594171493)
- [Vast read-only API PASS](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43591152693)
- [Jupyter 401 / TLS HOLD](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43592821513)

**Осталось для LIVE:** доверенный native канал, проверенные callback OneHost/S03, секрет signer+host, ограниченные GitHub-права, один подписанный end-to-end запрос и reverse receipt. Нельзя назвать мост полностью подключённым до этого.
