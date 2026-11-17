# NOX runtime 0.2 — source staging only

Отдельный entry размещает **12 проверенных Python-файлов** integrations и warm controller в новом каталоге `/root/nox/extensions/drive_first_20261117_<bundleSHA12>`. Он не импортирует и не выполняет установленный runtime, не подключает callbacks и не меняет работающий OneHost. Повтор legacy warm patch, canary, config scan и GGUF probe отсутствует.

## Проверяемый контракт

`directory()` и `stage()` адаптированы из ранее проверенного `native_release/entry.template.py`. Сохранены обход каталогов через directory fd/O_NOFOLLOW, owner/mode guards, O_EXCL без перезаписи, fsync и точный readback. Добавлены полный preflight всех source pins до записи, фиксированный список runtime-файлов, owner/mode проверки существующих файлов и неблокирующее открытие неподходящих типов. Коллизия или symlink дают HOLD; чужие bytes не удаляются. Незавершённый файл после прерывания остаётся для явного reconciliation, а не перезаписывается при повторе.

Перед записью требуются контекст действующего owner runner (`NOX_OWNER_REQUEST_ID`, `NOX_OWNER_SOURCE_SHA`), известный `CHAT_ACTIVE=0` и существующий `owner_maintenance.lock`. Контекст среды сам по себе не является аутентификацией: прежние actor/repository/source/host проверки оператора должны сохраниться. Flag только читается — entry не ставит паузу, не вызывает STOP и не меняет режим. Owner flag повторно проверяется перед каждым файлом. Lock сериализует cooperating writers; исключительность против произвольного внешнего writer не заявляется.

По умолчанию entry берёт existing flock самостоятельно. Если существующий runner уже удерживает lock, он может передать **реальный наследуемый fd** через `--maintenance-lock-fd`; fd сверяется с inode существующего lock. Новые lock-файлы, сервисы, scheduler или очереди не создаются.

Максимум JSON bundle — 2 MiB, compressed bundle — 512 KiB, отдельный source — 250000 bytes. В текущем bundle 98385 source bytes. Проверки SHA — явные условия, не `assert`; действуют при `python -O`.

## Результат

Успех печатает `NOX_MAINT_REPAIR=<JSON>` со статусом `SOURCE_INSTALLED_NOT_BOUND`, per-file size/SHA и затем `NOX_MAINT_REPAIR_COMPLETE=true`. Этот marker подтверждает **только staging исходников**. `runtime_bound=false`, `runtime_imported=false`, `native_chat_canary_pass=false`, model requests/downloads/new services/workers — 0.

Источник — согласованные package commits integrations `690342457804f096b918664731756e1a79564631` и controller `7ce6290420bf1765fefd1c0b082175a1bea42ab9`. Их behavioral fixes независимо проверены на commits `2e78cc5d037c824aac0749ae6a953e39673401ed` и `f1b7df742f26d4acf3733c9a91da34809d2b87f4`. Controller и MemfdHandle должны идти совместимым комплектом; прежние native директории не затрагиваются.

## Локальная сборка и проверка

`python build.py` сверяет каждый исходный файл с `inputs.lock.json` и строит frozen entry/manifest. Любой новый файл или изменение bytes требует нового reviewed input lock. Builder не обращается к сети и native paths.

`python -m unittest discover -s tests -v` запускает четыре локальные проверки: безопасное повторное размещение с неизменными inode/mtime; collision/symlink/mode без перезаписи; input pin drift до записи; owner activity и existing lock/inherited fd. Fixtures используют временные каталоги и код, который намеренно упал бы при импорте, — runtime не исполняется.

Native invocation выполняет только root после review через прежний owner action. В этой задаче native запуск, внешняя публикация и включение runtime не выполнялись.
