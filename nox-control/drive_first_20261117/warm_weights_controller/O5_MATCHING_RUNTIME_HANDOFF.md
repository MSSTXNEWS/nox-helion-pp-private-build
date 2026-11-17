# O5: согласованная пара runtime 0.2

**SOURCE_TESTED, не native USED.** Этот документ не задаёт нового dispatcher,
queue API или loop. O5 сохраняет своё владение existing OneHost binding.
Native source-staging отдельного immutable каталога выполняет root; прежний
`drive_first_20261117_0c40501f9068` не подменяется и не считается обновлённым.

| Пакет | Закреплённый source commit | Проверенный behavior |
|---|---|---|
| integrations_bridge 0.2.0 | `690342457804f096b918664731756e1a79564631` | Memfd SHA `ec9910a67228cc8681a1f1157f9107003bac4634548ec3130bc43573745b1386`; Drive SHA `2d985e33ed6501b95a085b85abbf5654d576513b9570710f706e678e8ff78c3b` |
| warm_weights_controller 0.2.0 | `7ce6290420bf1765fefd1c0b082175a1bea42ab9` | Controller SHA `1312845745150bbfc52863fa6eab85d67da12d5108fb1cc1a7776d56621b5d05` |

Версия согласована: старый handle без `release_identity()` или без подтверждённого
ACK от close остаётся HOLD. После независимого review поведение не менялось;
добавлены только version 0.2 metadata и описание контрактов.

## Что именно привязать к существующему host

1. `owner_should_pause() -> bool` — реальная активность/STOP владельца. Это
   обязательный callback, который нельзя заменить локальным `should_pause`.
   Их значения объединяются через OR; UNKNOWN/не bool даёт HOLD.

2. `host_resource_admission(request)` — существующий атомарный arbiter,
   принимающий `transition_id`, expected source mode/loaded groups, load/unload,
   RAM/GPU bytes и `resume_lease`. Подтверждённый grant содержит
   `granted=true, scope=host, lease_id, fencing_token` (строго integer).
   `host_release_resource(lease)` возвращает `{"released": true}`.
   Это будущий binding к существующему arbiter, не доказательство, что такой
   callback уже зарегистрирован в native dispatcher.

3. `host_reserve_ram(bytes)` выдаёт отдельный retained RAM lease той же формы;
   `host_release_ram(lease)` возвращает явный `{"released": true}`. Ошибка,
   `None` или неподтверждённый ACK не засчитываются. Новая RAM загрузка не
   перезаписывает handle с неопределённым освобождением.

4. Model hooks `drain/checkpoint/pause/unload/load/resume/health` сохраняют
   существующий ключ операции. Успех: `{"ok": true, "operation_key": key}`.
   Неизвестный исход `load` оставляет STARTED и удерживает RAM. Через
   `inspect_operation` существующий host подтверждает DONE с exact receipt
   либо NOT_STARTED; UNKNOWN не разрешает слепой повтор.

5. После фактического окончания всех loader/child/mmap references host
   передаёт `release_owned_ram(group, receipt)`. Минимальные поля receipt:
   `group`, `verified=true`, `loader_refs_released=true` и три поля из
   **этого же** `handle.release_identity()`:
   `ram_handle_id`, `ram_lease_identity_sha256`, `ram_fencing_token`.
   Ни raw fd, ни raw RAM reservation token не экспортируются. Pending
   transition/STARTED load или unload группы блокирует освобождение независимо
   от наличия старой квитанции. Registry pop разрешён только после
   `closed=true, lease_released=true`.

## Потерянные ACK и продолжение

При неопределённом RAM release повторный close даёт HOLD без нового вызова
release. Сначала host читает свой текущий authoritative lease record. Затем
`controller.reconcile_owned_ram_release(group, receipt)` получает
`verified=true`, **точные** `lease_id` и integer `fencing_token`, `released`.
Подтверждённое `released=true` завершает lost-ACK ситуацию; подтверждённое
`false` у сохранённого handle разрешает один явный последующий close. Когда
handle отсутствует после прерванного download, существующий host сначала
сам подтверждает освобождение своего held lease. Этот helper не выполняет
native query и не выдумывает результат.

Намерение transition admission/release записывается до callback.
`resource_lease_state=UNKNOWN` запрещает повтор admission. Для
`adopt_verified_state` после HOLD нужны настоящие verified/source/observed_at
и `settled_transition_id`, `pending_operations_settled=true`,
`resource_lease_settled=true`, точные `settled_lease_id` и
`settled_fencing_token`. Если admission ACK не получен и lease ID неизвестен,
host сверяет исход по `settled_resource_request_id=transition_id`. Нельзя
считать отсутствие ответа или истёкший TTL доказательством освобождения.
После readback операции помечаются RECONCILED, не DONE, и следующий transition
использует новый ID. TRAIN→WORK→TRAIN восстанавливает сохранённый checkpoint;
перед resume повторно проверяются компоненты и SHA.

## Минимальная дальнейшая интеграция

Существующий `IntegrationBridge.execute("nox.integrations.drive.check.v1", {},
task_id=host_task_id)` имеет подтверждённый inner payload. Его host.py SHA
`5130d9028d60a9f78f5c0b3644c067329219f98d389859b1fdd6d933f946da1d` не изменялся.
Но actual native task envelope, TaskID mapping, handler registration,
authorize/result_sink/readback, owner cancel и OAuth project configuration
остаётся получить из O5 native binding. WP/relay IDs не являются native IDs.
Source-staging не включает эти callbacks и не запускает Drive request.

После реального разрешённого binding сначала один read-only Drive check с
durable receipt/readback. Затем отдельный крошечный Drive→ownedRAM fixture
через существующий resource lease/owner gate; loader/реальные веса/обучение
не объявляются готовыми по одному sealed memfd. Для отмены прекращается
admission новых наших действий; прежние handler bindings и основная модель
сохраняются. Неопределённый исход сначала сверяется, затем выполняется
узкий version rollback владельцем. Ни reboot, ни новый daemon/queue не нужны.

**Проверки:** integration 26, controller 20 локальных тестов; независимый
review двух дополнительных regressions. На прежних исходниках три integration
и три controller regressions падают; новые проходят. Эти результаты относятся
к временным файлам, локальным subprocess fixtures и kernel memfd, без native
Drive, модели, V100, trainer, HTTP API или подключения callbacks.
