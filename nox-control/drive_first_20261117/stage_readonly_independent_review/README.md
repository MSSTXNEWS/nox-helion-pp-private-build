# Независимая проверка read-only stage diagnostic

**Вердикт: PASS_SOURCE_REVIEW_NO_BLOCKERS.** Проверен замороженный исходник `owner_runtime_stage_readonly_diagnostic.py`, 19 240 B, SHA `0fb3d5e341058ba55f88a62b5976f15afc1c0afba5344cfc478d3a94536f1036`. Нативная диагностика этим review не запускалась.

## Что подтверждено

Все 12 source pins точно совпадают с `STAGING_MANIFEST.json` SHA `61433567b16a2bd5433104146fad458a7f1427b6a7159a948211227b349a1d9d`, суммарно 98 385 B. Семь каталогов фиксированы. Список возможных причин отказа учитывает именно конечные каталоги, которые проверяет установщик: `state/priority`, `state` и два package dirs. Права `0775` у родительского `/root/nox` сами по себе причиной не объявляются. `original_failure_path_proven=false` сохраняется.

Для каждого родителя используются directory FD и `O_NOFOLLOW`; для конечного source-файла — nonblocking open и сравнение inode/type/owner/mode/size/mtime/ctime до и после чтения. Несовпадение не превращается в подтверждённый SHA.

Lock snapshot читает только metadata фиксированного lock-файла и ограниченный `/proc/locks`. Сопоставляются device major/minor и inode. Строки waiters (`->`) не считаются владельцами. Только для положительных PID совпавших holders читаются ограниченные `stat`/`status`; startticks сравниваются дважды. OFD PID -1, усечение, изменение snapshot и повторное использование PID дают UNKNOWN. Содержимое `cmdline` и `environ` не читается. Даже NO_MATCH_OBSERVED оставляет `free_lock_proven=false` и `retry_authorized=false`.

## Дополнительная проверка

Одна независимая fixture заменяет обычный файл на FIFO между lstat и open. Проверка выполнялась в дочернем процессе с пределом ожидания 2 секунды: **1/1 PASS, 0.011 s**. Результат — `CHANGED_BEFORE_READ`, 0 прочитанных bytes, `sha256=null`; подтверждены `O_NONBLOCK` и `O_NOFOLLOW`. Восемь авторских fixtures прочитаны, весь suite повторно не запускался.

Probe не выполняет chmod/chown, не захватывает или снимает lock, не завершает процессы, не импортирует staged runtime и не делает сеть/записи. Его десятисекундный deadline кооперативный; это не обещание прерывания зависшего kernel syscall. Byte/row/PID bounds заданы отдельно. Snapshot явно неатомарный и не разрешает staging retry или изменение прав.

## Checkpoint и NEXT_READY

`runtime_bound=false`, `native_staging_accepted=false`, `native_canary_pass=false`. Чужой source, два outcome slots и пять frozen документов не изменены. Root переиспользует более новое O1 lock evidence и при необходимости запускает только оставшуюся диагностику неизвестного partial stage. После фактического результата — сохранить историю HOLD, обновить итоговую дельту, провести fresh Drive guard и публикацию. Этот review не содержит нового chmod proposal.
