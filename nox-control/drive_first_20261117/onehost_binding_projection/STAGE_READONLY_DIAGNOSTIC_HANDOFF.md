# Один read-only probe: partial runtime stage, права каталогов, maintenance holder

**READY_SOURCE_ONLY.** Entry: `owner_runtime_stage_readonly_diagnostic.py`, **19 240 B**, SHA-256 **`0fb3d5e341058ba55f88a62b5976f15afc1c0afba5344cfc478d3a94536f1036`**. Native-вызовов автором не выполнялось; root публикует и запускает один раз через существующий trusted owner-канал. Не запускает stage, не импортирует runtime, не получает maintenance flock и не изменяет права.

## Точная область чтения

Семь фиксированных каталогов: `/root/nox/state/priority`, `/root/nox/state`, `/root/nox/extensions`, `/root/nox/extensions/drive_first_20261117_ee142b97c813` и его `runtime`, `runtime/nox_integrations`, `runtime/nox_warm`.

Все предки и leaf проверяются без следования симлинкам. Выводятся тип, UID/GID, mode, device/inode, размер и признаки владельца/групповой записи. При чтении **12 ожидаемых runtime-файлов** проверяются размер/SHA и стабильная идентичность до/после чтения. Pins взяты из `STAGING_MANIFEST.json` SHA `61433567b16a2bd5433104146fad458a7f1427b6a7159a948211227b349a1d9d`, bundle SHA `ee142b97c81327edf0130e2aba46c431e1d1334396581b11922507310553aa2b`. Всего ожидается **98 385 B** исходников, верхняя граница чтения — **98 397 B**; файлы неправильного размера не читаются. Содержимое не выводится.

`CHAT_ACTIVE` читается до и после, максимум 33 B за попытку. Возвращаются только **0/1**; другое содержимое — UNKNOWN без значения. Это не owner lease и не атомарный snapshot.

Дополнительная узкая ветка: metadata существующего `state/owner_maintenance.lock`; `/proc/locks` до 256 KiB за чтение, до 4096 строк, два снимка. Сопоставляются **major/minor + inode**, ожидающие `->` отделены от держателей. Только для положительного PID совпавшего holder, максимум восемь PID, читаются bounded `/proc/<PID>/stat` и `/proc/<PID>/status`: start ticks проверяются до/после, выводятся только PID, start ticks, Name, UID/GID. `cmdline`, environment и чужие файлы не читаются. OFD/PID −1, усечение, неизвестный формат, исчезновение процесса или смена идентичности дают **UNKNOWN**.

## Как запускать и читать результат

Единственный штатный вход — `main()`/`run()` в существующем owner-context: `NOX_OWNER_REQUEST_ID` и `NOX_OWNER_SOURCE_SHA`. Произвольных путей/аргументов, команд модели и нового scheduler нет. Контекст проверяется до файлового чтения. Parent runner сохраняет собственные проверки authority/source pin; этот модуль их не заменяет.

Вывод: `NOX_MAINT_REPAIR` с kind **`drive_first_runtime_readonly_reconcile`**. Маркер `NOX_MAINT_REPAIR_COMPLETE=true` означает **завершённую диагностику**, а не успешную установку или runtime binding. `native_staging_accepted=false`, `runtime_bound=false`, `free_lock_proven=false`, `retry_authorized=false` сохраняются всегда.

- `observed_original_directory_guard_failure_candidates` перечисляет только фактически наблюдённые неподходящие **конечные** каталоги `directory()`: priority, state и два package directory. `/root/nox` с mode 0775 не выдаётся за причину по одному ancestor mode.
- `all_expected_source_files_match=true` означает совпадение 12 исходников в момент ограниченного чтения. Это не подтверждает отсутствия дополнительных файлов, установки manifest или загрузки кода работающим процессом.
- `maintenance_lock_snapshot.state=NO_MATCH_OBSERVED` означает отсутствие совпадений в двух полных ограниченных снимках. Повтор операции всё равно проходит существующий lease/admission gate; диагностика не получает/снимает блокировку.

## Новые факты и владение исправлением

Первый stage: run **44149977429**, job **134275278537**, source **c49ee68d34fc9e0890a234fbff48d0c0e4132fe5** — `HOLD_DIRECTORY_OWNER_OR_MODE`, partial state неизвестен. RO reconcile run **44150997251** — `HOLD_MAINTENANCE_BUSY` до HTTP/model/dialog.

Root затем передал отдельные свежие native-факты другой команды: run **44150637673** наблюдал `/root/nox/state/priority` root/root **0775**, device 36, inode 2157348507; `CHAT_ACTIVE` 0644. **O1V3 уже владеет hardening этого каталога.** Наша работа не меняет mode и не присваивает repair claim. Run **44151821575**, job **134281917471**, по сообщению root получил ноль совпавших kernel lock rows и immediate acquire/release PASS; старый BUSY был временным. Эти квитанции автор этого probe повторно не запускал. Lock-ветка probe остаётся read-only; основная оставшаяся задача — partial stage.

Никакой blind chmod/retry не предлагается. После результата probe и точной квитанции O1 root сопоставляет свежую metadata с владельцем исправления. При всех 12 совпадающих файлах не перезаписывать их ради активности; при partial или collision сохранить имеющиеся bytes и использовать только уже согласованный stage/admission путь после устранения конкретного blocker.

## Проверки и следующий шаг

**8/8 author fixtures PASS**: exact pins/no mutation, final-vs-ancestor mode, leaf/ancestor symlinks, partial/hash/size mismatch, неизвестный CHAT_ACTIVE без утечки, отсутствие context до чтений, holder/waiter/no-match, OFD/truncation/PID reuse. Независимая late regular→FIFO подмена: **1/1 PASS**, `CHANGED_BEFORE_READ`, bytes 0, SHA null; независимый review новых lock guards — без конкретных блокеров. Это локальные проверки, не native acceptance.

**CHECKPOINT:** source frozen, manifest pins verified, no changes to stage guard; готов один ограниченный owner probe. **NEXT_READY:** root читает одну фактическую квитанцию, сопоставляет 12 source pins и O1 hardening receipt, затем разрешает только следующий доказанно необходимый stage/binding шаг. Автор освобождает слот; повторных native probes, lock polling и nested agents не создаёт.
