# NOX: установка runtime self-model и меню

**Статус: payload собран и локально проверен; native execution ещё не было.**
Используется уже успешный OneHost owner repair route. Root публикует payload
на approved mutating base `4438d67bae87a59b857bb3a5f8af0927c0509e7f`
(родитель `8b7f431f419a3618bed7a9442ccf1072a48e747a`). Operator/workflow не меняются.

Entrypoint: `nox-control/owner_resonance_canary_v3_20261117.py`, action `repair`.
Имя entrypoint историческое: этот payload не запускает canary или generation.
Оно сохраняет уже разрешённый transport route.

## Ровно пять runtime файлов

| Native path | Exact before | Exact after |
|---|---|---|
| `/root/nox/scripts/chat_proxy.py` | b202301a… /103637 B |30207a85… /103831 B |
| `/root/nox/scripts/owner_chat_stream.py` |2c4ae86d… /26210 B |38f4dc29… /26955 B |
| `/root/nox/scripts/nox_v29_chat_bridge.py` |17932e2f… /51632 B |9d747542… /51865 B |
| `/root/nox/scripts/owner_model_reference_binding.py` | Must be absent |b9f4addc… /18265 B,0600 |
| `/root/nox/state/verified_model_reference.json` | Must be absent |0d0a839b… /1204 B,0600 |

Полные digest есть в `BUILD_MANIFEST.json` и compatibility transform. Последние
два файла созданы только из опубликованного source package `9a4e3b18…`.
Существующие неизвестные helper/snapshot файлы не перезаписываются даже при
похожем названии. Это HOLD до STOP, с сохранением исходных данных.

Menu меняет одну tuple entry в existing bridge overlay; frozen UI file
`/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-ui.js`
читается с exact `c5f6b23d…` pin и остаётся неизменным.

## Конкретные gates

Существующий lifecycle module `native_v24_dialog_installer.py` перенесён
**byte-for-byte**, SHA `dff6a3841d76a07de5552e81476a8f322179091b641a3b14a3795ee120b6ef27`.
Это ровно embedded module успешного `be4750…`.

До source mutation проверяются root owner request context, metadata, существующая
maintenance lock с dev36/ino59886214, все прежние STOP, свежие `CHAT_ACTIVE=0`,
`MODE=IDLE`, priority status и свободные model slots через known GET8098/slots.
Координатор сохраняет короткое согласованное окно обслуживания. Этот lock
сериализует cooperating maintenance writers; он не объявляется атомарной
блокировкой нового пользовательского запроса.

Перед первым STOP требуется current proxy PID3550426/start174075151,
argv SHA `da23c227…`, exe `/usr/bin/python3.12`, cwd `/root/nox/scripts`,
Supervisor config SHA `ddec2af7…`. Reuse base дополнительно проверяет
service/group ownership, стабильность lifetime/config, исчезновение прежнего
proxy lifetime и новый PID после start. Unchanged dependencies: agent_loop
`0ecec93b…`, legacy common `618b2b24…`. Modern O5/common не подставляется.

Shared legacy counter4 не является gate этого ранее проверенного proxy
installer и не сбрасывается. **Общая pending O2 writer closure сама по себе
не блокирует эту отдельную установку.** Если конкретный lease, owner-idle,
STOP, metadata, source или proxy-lifetime gate не проходит, установка HOLD.

Унаследованный process identity helper читает bounded `/proc/PID/environ` для
поля Supervisor process name; значения environment не экспортируются. Нового
поиска credentials, ключей или других секретов здесь нет.

## Transaction, сохранение и восстановление

Порядок: compile/transform в памяти → protected stage → originals backup →
повторные idle/lease/lifetime/source checks → stop только `nox-proxy` →
проверка смерти старого lifetime → helper+snapshot → три source replacement →
полный readback → start того же `nox-proxy` → health8080 + новый lifetime.

Stage: `/root/nox/scripts/.owner-model-reference-<request>/`, mode0700.
Originals: внутри `originals/`, исходные три source bodies mode0600 с проверкой
byte digest/inode/metadata. Для каждого подготовленного source отдельно
закреплён staged inode; его владелец, группа, mode, размер и bytes повторно
проверяются перед каждым rollback restore. Одинаковые bytes на чужом inode
дают HOLD, а не право его перезаписать. Native receipt записывается по существующему пути
`/root/nox/state/owner_v24_dialog_<request>.json`; его schema теперь
`NOX_MODEL_REFERENCE_PROXY_INSTALL_V1`.

Два новых файла создаются atomic no-clobber hardlink из stage с последующим
удалением staged link, fsync обоих parents и readback. После этого nlink=1 и
mode0600 обязательны. Target CAS сопоставляет body и исходный staged inode;
неожиданный target никогда не заменяется. При filesystem uncertainty состояние
фиксируется, а automatic replay запрещён.

Любая ошибка после STOP включает прежний проверенный recovery path. Пока
proxy остановлен, source возвращаются к exact before bytes с исходными
owner/group/mode; затем удаляются только новые файлы, созданные этим request
и всё ещё совпадающие по body/inode/metadata. Старый proxy запускается заново.
Новый owner STOP сохраняется; неизвестный start/lifetime/foreign mutation
останавливает автоматический recovery и требует readback вместо повторения.

Это automatic rollback текущей transaction. Отдельный post-success rollback
после внешнего QA должен быть привязан к её конкретному receipt/backup; этот
install payload нельзя повторно запускать как rollback. До такого решения
не удаляются backups и результаты QA.

Никаких model POST, model reload, counter/queue reset, S03 reset/migration,
удаления диалогов или смены auth этот installer не делает. История будет
подтверждена через один changed-path QA; source-level отсутствие reset не
выдаётся за уже выполненную runtime history проверку.

## Проверено локально

Пять TempFS checks PASS: exact пять файлов apply/undo, partial fsync effect
после первого new target, сохранение foreign target, wrong current proxy
lifetime/config до STOP, финальный readback всех пяти postimages. Один
адресный повтор последнего теста подтвердил отказ при mode drift snapshot
с прежним body hash; full suite не повторялся. Payload compile PASS; wrapper
не выполнялся. Старая lifecycle suite не повторялась.

Независимый review нашёл конкретный inherited hash-only rollback gap: чужой
inode с теми же postimage bytes мог быть перезаписан. Base dff6 не изменён;
минимальный override закрепил source staged inode и проверяет его до restore.
Независимый reproducer стал GREEN; повторены только два затронутых transaction
cases (3/3 targeted PASS). Остальные lifecycle проверки не повторялись.
Независимый review PASS зафиксировал main40b93279… и payload18582aff…;
receipt SHA61a25ad4…, base dff6 byte-identical. Никакие
native installed/USED claims до actual receipt не сделаны.

## Следующая проверка — один изменённый маршрут

После actual install SUCCESS и свежего postimage/proxy PID binding root
разрешает ровно один вопрос **«Какая модель в твоей основе сейчас?»** в уже
существующем owned QA dialog `12092579cf5144419cfa4fadc2e3a03b`. New-dialog
creation=0; отдельный durable intent/new nonce; model POST≤1; automatic retry=0.
Проверяются полный SSE terminal, сохранение prefix history и новый exchange
в S03. Это новый source path, а не повтор старого completed canary.

Остаётся один точно известный runtime gap: размер `apply_system('', '')`
из unavailable verified body `slim_chat_t885u.py` не измерен. Prefix≤6144B и
новый route будут проверены именно этим QA; точный token count/window не
объявляется доказанным. Ordinary chat не получил новый tokenizer gate.
