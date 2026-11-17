# NOX Warm Weights Controller

Компактный модуль Python stdlib для **существующего OneHost**: ограниченный preload весов, cgroup admission и переходы WORK / TRAIN / PAUSED_TRAIN. Канонический путь по последнему решению владельца: **внешний источник → проверенный Google Drive → собственный RAM memfd → существующий loader**. Новый daemon, scheduler, очередь или trainer не создаётся. На сервере пакет не установлен; нативных действий при разработке не выполнялось.

## Политика источников и памяти

`source_policy: DRIVE_FIRST` и `startup_storage: ownedRAM` — значения по умолчанию. Manifest принимает относительные пути внутри уже настроенного Drive project root, точный размер и SHA256. Этот контроллер не скачивает произвольные URL и не реализует внешний ingest: перед включением модели её объект должен быть загружен в Drive и проверен существующим адаптером. Backup работает через `DriveAdapter.upload_artifact(...)`, без новой backup очереди.

| Уровень | Реальное поведение |
|---|---|
| `coldDrive` | Много канонических моделей, датасетов и артефактов в Drive. Количество хранимых объектов не обещает их одновременную загрузку. Один manifest содержит до128 групп. |
| `ownedRAM` | По умолчанию только выбранные WORK-группы, по приоритету, byte caps и `startup_max_groups`. Адаптер создаёт новый собственный memfd, проверяет size/SHA, устанавливает Linux seals. Host держит handle и RAM lease. |
| `warmSSD` | Только явное `allow_ssd_cache: true` + `startup_storage: warmSSD` в manifest и `NOX_ALLOW_DISK_CACHE=1` у Drive adapter. Не является обязательной промежуточной стадией RAM загрузки. |
| GPU / engine | Только существующий host loader после отдельного RAM/GPU admission. Успешная передача в RAM означает `OWNED_RAM_VERIFIED_NOT_MODEL`, а не работающую модель. |

Первичный chat/core/backbone/Engram не дублируется startup-веткой. Такие роли защищены от unload; `protected: true` всегда сильнее `may_unload: true`, противоречивый manifest отклоняется. Без живой привязки к OneHost и его арбитру apply возвращает HOLD. CLI не владеет постоянным RAM registry и не может безопасно сохранить RAM handle после завершения; его RAM apply поэтому также получает HOLD.

## Реализованные механизмы

- Manifest групп: pinned размер/SHA256, Drive/cache пути, приоритет, WORK/TRAIN, tier, selected preload, отдельные оценки RAM/GPU загрузки. `startup_ram_bytes` включает вес и запас64MiB на каждую новую передачу. `startup_transfer_bytes` отдельно ограничивает байты источников; `startup_max_groups` по умолчанию6, допустимо1–24. Нулевые лимиты ничего не загружают.
- cgroup v2: `memory.current`, `memory.max`, `memory.stat`, PSI и системный `MemAvailable`. Гарантированный остаток — минимум системного available и остатка до cgroup max. `shmem` уже учтён в charged memory. `inactive_file` отражается только как верхняя граница кандидата, **гарантированное освобождение0**.
- Отдельные CHAT-, TRAIN- и системный резервы. Preload сохраняет все три. Большая PSI или недостаточный остаток дают HOLD. План не считает будущий unload уже состоявшимся.
- Для каждого apply transfer/hash/warm обязателен существующий host-wide writer lease и callback активности владельца. Нет binding, владелец активен или запросил паузу —0 новых transfer/warming effects. Owner callback проверяется на границах chunk; arbiter обеспечивает конкурирующие допуски, snapshot сам по себе их не заменяет.
- Drive→RAM: отдельный retained RAM lease на `size + 64MiB`, новый собственный sealed memfd, проверка fd/size/seals и повторный SHA readback через ограниченные `pread` chunks. fd не попадает в JSON-квитанции. Регистр handles живёт в процессе OneHost. Только `ram_handle_for_loader(group)` отдаёт доверенному loader действующий handle.
- `release_owned_ram(group, receipt)` закрывает только собственный handle, после verified readback `loader_refs_released: true`, когда группа больше не числится загруженной. Proof также содержит точные поля `handle.release_identity()`: nonce handle, SHA идентичности lease и integer fence. Незавершённый transition или STARTED load/unload этой группы дают HOLD до reconciliation. Защищённые группы не закрывает. Host обязан учесть дочерние/inherited fd и mmap references; закрытие единственного controller fd без освобождения прочих ссылок не обещает вернуть RAM.
- При паузе CPU-передачи адаптер прекращает только свою передачу. Незавершённый RAM memfd закрывается адаптером с release; следующее чтение начинается из проверенного Drive. Пауза тренера сама освобождает0 байт. Никаких SIGSTOP CUDA, killall, глобального drop_caches или удаления старого Engram memfd.
- Для опционального SSD: atomic staging `.part`, SHA/size, fsync, hardlink+unlink без перезаписи существующего файла. Конфликтующий файл не удаляется; local copy сохраняет свой `.part` при паузе. Проверенные файлы получают inode/device/mtime/size/SHA квитанцию. Неизменившийся файл не хешируется заново при каждом плане.
- Опциональное SSD warming читает ограниченный префикс через mmap с owner/admission guard на chunk. Это файловый cache hint; страницы не закрепляются, mmap не удерживается. `touched_bytes` не является точным RSS или обещанием резидентности. Основной RAM путь отдельный: sealed memfd с учтённой памятью.
- WORK/TRAIN: drain → checkpoint/pause при уходе из TRAIN → разрешённый unload → свежий admission → load → resume при TRAIN → health → durable DONE. Нового trainer нет: все model-specific действия выполняет действующий host через проверяемые callbacks.
- Журнал хранит operation key до callback. DONE повторно возвращает receipt; неопределённый шаг требует inspect_operation. После timeout нельзя выдать другой transition поверх неизвестного эффекта. HOLD сохраняет успешные шаги и точный rollback plan. Восстановление выполняется через readback, reconciliation и настоящий обратный переход.

`ram_bytes` в mode admission обозначает дополнительную память loader/workspace, а не повторную оплату уже удержанного RAM источника. Host arbiter обязан учитывать одновременно retained leases, VRAM, workspace и текущие primary-процессы. Unload engine не закрывает источник автоматически: собственный RAM источник разрешается освободить отдельным `release_owned_ram` после фактического окончания loader references. Если новый admission не проходит, переход остаётся HOLD; controller не выдумывает освобождённые байты.

## Внешний snapshot сервера

Основной исполнитель сообщил native snapshot **17.11.2026 20:22:12 МСК**:

```text
memory.current   193361956864
memory.max       194065203200
file             190119346176
shmem             75403325440
file_mapped      121937813504
inactive_file     92654321664
anon               2324660224
PSI avg10                   0
```

Остаток до cgroup max —703246336 байт, около670,67MiB. Это большой file cache и защищённый shmem. Контроллер не прибавляет inactive_file к свободному бюджету и не вытесняет основную модель. При нормальных резервных бюджетах новое обучение/preload получает HOLD. Snapshot получен от основного исполнителя; этим пакетом сервер не измерялся. Опциональное заимствование доказанно своего cold cache здесь не реализовано.

## Привязка к существующему OneHost

Интерфейс согласован с пакетом `nox_integrations` commit `391953ee09807a890f0eaf37225e6e3670c1f4a9`. Его основной метод:

```text
download_memfd_verified(remote_path, expected_sha256, size_bytes,
    *, reserve_ram, release_ram, should_pause) → MemfdHandle
```

Форма встраивания в существующий host; все функции справа должны быть его реальными, уже подключёнными реализациями:

```python
controller = Controller(
    manifest, cache_root, journal_path,
    snapshot=current_cgroup_snapshot,
    hooks=existing_host_hooks,
    host_resource_admission=existing_arbiter_acquire,
    host_release_resource=existing_arbiter_release,
    owner_should_pause=existing_owner_active_or_stop,
    download_memfd_verified=drive_adapter.download_memfd_verified,
    host_reserve_ram=existing_ram_reserve,
    host_release_ram=existing_ram_release,
    persistent_host=True,
    owned_ram_registry=existing_process_handle_registry,
)
plan = controller.startup(apply=False)
# existing dispatcher calls startup(apply=True) only under its normal lifecycle.
# Its loader resolves an owned_handle_key via controller.ram_handle_for_loader().
```

`persistent_host=True` — заявленный контракт реального долгоживущего OneHost, а не способ обойти HOLD в коротком скрипте. Host registry не должен открывать доступ к handles из произвольного LLM-кода. Во время рестарта процесса memfd исчезает, если не осталось законных ссылок другого процесса; journal не восстанавливает fd. При отсутствии handles требуется новый admission и загрузка из Drive. Journal state не является live process probe.

Для SSD опционально передаётся `download_verified=drive_adapter.download_verified`, cache root совпадает с `NOX_DRIVE_CACHE_ROOT`. Callback принимает remote_path/cache_path/SHA/size и should_pause, возвращает `downloaded_verified` либо `cache_hit_verified`. Controller повторно проверяет локальные байты перед использованием. Секреты и произвольные URL в manifest не нужны.

## Контракты host callbacks

### Проверяемое завершение cache lease

Cache/preload writer admission и release теперь записывают намерение в тот же
журнал controller до вызова host. Потерянный ACK оставляет UNKNOWN; новый
`cache_local`/startup group не повторяет admission и не затирает прежний lease.
После завершённого цикла следующий запрос получает новый сохранённый epoch.

Доверенный host читает свой существующий lease ledger и вызывает
`reconcile_cache_lease(receipt)`: обязательны `verified=true`, `source`,
`observed_at`, boolean `released` и точные `lease_id`/integer `fencing_token`.
При потерянном admission, когда lease ID ещё неизвестен, требуется точный
`settled_resource_request_id` из записанного request и `released=true`;
незавершённый запрос сначала урегулирует сам host. Метод не вызывает сеть,
admission или release. Readback `released=false` для известного lease разрешает
один явный `release_reconciled_cache_lease()`; повтор после ещё одного потерянного
ACK опять требует readback. Старый `cache_lease_reconcile` journal поддержан.

Это source-исправление существующего controller, без нового scheduler или
native binding. Установленный ранее runtime0.2 автоматически не меняется.

Callbacks получают стабильный operation_key и возвращают `{ok: true, operation_key: ...}` **после реального действия и readback**. Они работают в доверенном административном слое.

| Callback | Обязательное поведение |
|---|---|
| `drain` | Остановить приём новой фоновой работы, дождаться безопасной границы. При недопустимом конфликте с чатом отказать. |
| `checkpoint` | Настоящий trainer пишет durable checkpoint/manifest с model, optimizer, scaler, RNG и data cursor; квитанция содержит path/SHA/components/durable_verified. Controller сверяет файл и SHA. Реальная полнота компонентов — ответственность trainer. |
| `pause` | Кооперативная пауза после checkpoint. Память не считается освобождённой. |
| `unload` | Выгрузить только разрешённую группу, preserve_source=true, remove_memfd=false. Подтвердить фактическое окончание engine/loader references. |
| `load` | Загрузить проверенный источник. Для RAM — owned_handle_key с разрешением handle внутри текущего host; для SSD — точный путь/SHA. Не возвращать успех до загрузки. |
| `resume` | Восстановить настоящий trainer из сохранённого checkpoint или начать разрешённую новую работу. |
| `health` | Подтвердить целевой режим и фактически работающие группы. Передача файла не считается health. |
| `inspect_operation` | DONE с исходной receipt либо доказанный NOT_STARTED; неизвестное состояние оставляет HOLD. |

Admission получает source mode, expected loaded, load/unload groups, RAM/GPU budget и resume lease. Host проверяет свежую реальность, владение ресурсом и stale journal. Ответ: granted=true, scope=host, lease_id, fencing_token; release: released=true. Один cache/mode writer обеспечивается существующим арбитром. Неопределённая операция не разрешает выдавать её ресурс повторно только по истёкшему TTL.

### Изменения lifecycle 0.2

Owner callback обязателен и проверяется первым. Дополнительный `should_pause`
объединяется с ним через OR; локальный `False` не отменяет активность владельца.
Небулевое/неизвестное состояние даёт HOLD.

TRAIN→WORK сохраняет проверенный checkpoint. Следующий WORK→TRAIN передаёт
`resume_from_verified_checkpoint=true` и вновь проверяет SHA/completeness;
первый разрешённый запуск без checkpoint остаётся отдельным случаем fresh start.
TRAIN→TRAIN с новым ID проверяет health без повторных drain/checkpoint/pause.
Повтор одного незавершённого перехода использует журнал и проверку исхода
операции; уже использованный старый ID не запускается после другого перехода.

Намерение resource admission и release записывается до callback. Потерянный
ACK оставляет `resource_lease_state=UNKNOWN`; повтор не выдаёт новый ресурс
вслепую. Для `adopt_verified_state` после HOLD нужны прежние поля settlement,
а также `resource_lease_settled=true`, точные `settled_lease_id` и
`settled_fencing_token`. Когда admission ACK вообще не получен, нужен
`settled_resource_request_id`, равный transition ID. Только существующий host
может подтвердить эти факты. STARTED операции после такого readback становятся
RECONCILED, не DONE; продолжение использует новый transition ID.

Удерживаемый handle удаляется из реестра только после явного
`closed=true, lease_released=true`. При ошибке/потерянном release ACK handle и
неопределённый lease сохраняются для reconciliation; startup не перезаписывает
такую группу новой загрузкой. `reconcile_owned_ram_release(group, receipt)`
принимает настоящий host readback с exact lease/fence, а не выполняет запрос
самостоятельно. Нужна согласованная версия `MemfdHandle` 0.2; старые handles
без identity/ACK дают HOLD. Полнота и свежесть native readback принадлежат
существующему owner/lifecycle, JSON от модели не заменяет это доказательство.

`CommandHooks` — необязательный мост к доверенным административным скриптам: exact argv, SHA исполняемого файла, shell=False, JSON stdin/stdout, timeout. Команды не берутся из LLM. Wrapper должен иметь ограниченный stdout; его timeout не доказывает остановку внешнего trainer. RAM handle нельзя восстановить из JSON — RAM loader binding остаётся внутри постоянного host. Секреты в argv/квитанциях запрещены конфигурацией хоста.

## CLI и проверка

Из корня без установки зависимостей:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
PYTHONPATH=. python -m nox_warm --help
```

Общий синтаксис:

```text
python -m nox_warm --manifest MANIFEST --cache-root CACHE --journal JOURNAL
                  [--cgroup CGROUP] [--meminfo MEMINFO] [--hooks HOOKS]
                  [--apply] status|startup|transition TARGET TRANSITION_ID|
                  cache-local GROUP SOURCE|adopt-host-state RECEIPT|rollback-plan
```

По умолчанию dry run: transfer/load/unload не выполняются. `status` показывает snapshot и journal, `native_ready:false`, live probe не заявляет. RAM startup apply из CLI HOLD, потому что процесс не владеет постоянным binding. `cache-local` работает только при explicit SSD opt-in и реальных owner/host lease callbacks; это инструмент trusted local fixture/artifact, не обход канонического Drive происхождения моделей.

`examples/pin_manifest.py` хеширует реальный локальный файл, создаёт DRIVE_FIRST/ownedRAM manifest с нулевыми startup budgets и protected=true/may_unload=false. Сам helper ничего не загружает в Drive. Перед активацией канонический Drive объект должен существовать и пройти проверку; оценки RAM/GPU задаются после измерения.

Начальное состояние UNKNOWN. `adopt-host-state` принимает trusted host readback с verified/source/observed_at. При pending effect нужны settled_transition_id и pending_operations_settled=true. Самодельный JSON не становится доказательством реального работающего процесса.

Откат: `rollback-plan` → урегулировать pending operation keys действующим host → принять свежий readback → transition к restore_mode с новым ID. Admission/health остаются обязательными. Слепого reload поверх неизвестного CUDA действия нет.

## Проверка и границы результата

20 локальных тестов проверяют настоящие временные файлы, Linux sealed memfd и изолированные callback fixtures: cgroup/shmem; manifest/path; atomic pause/resume и неверный SHA; low-headroom/0effects; bounded mmap; checkpoint/idempotency; journal recovery; protected wins; health failure; reconciliation и обратный переход; Drive cache hit; обязательные owner/lease и OR cancellation; RAM persistent binding/64MiB lease/retained handle/verified release; потерянные lease ACK; checkpoint при возврате из WORK; отказ повторного старого transition ID. Три адресных новых случая воспроизведены на прежнем source: 3/3 FAIL до исправления. Дополнительный независимый review воспроизвёл и затем подтвердил исправление двух случаев: живой dup(fd) при неизвестном load ACK и stale settlement fence.

Это не тест реального trainer, модели, Drive сети или native запуска. Предыдущая версия источников staged на OneHost в `drive_first_20261117_0c40501f9068`; исправления lifecycle 0.2 туда не применялись. Callback binding и native acceptance остаются необходимыми. Никаких серверных весов, существующего Engram memfd, активных V100 процессов, cron или чужого scheduler при разработке не изменяли.
