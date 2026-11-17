# Дельта v2.4: runtime 0.2 и native v4

**Подготовлена, не применена.** Пять frozen release-файлов остаются побайтно прежними. Новые полные копии этих документов не создаются: здесь только программа, facts, outcome slots, unified patch и receipts. Версия2.4 / plan_revision5 сохраняется.

## Что меняется

Новый current block добавляется перед прежним снимком; прежний заголовок получает явную historical-пометку. Весь прежний Markdown остаётся обратимо сохранённым, включая каталог. В JSON заменённые текущие status/evidence сохраняются в historical snapshot. Карточки, workpackages, dependencies, source pins, source baseline, V3 policy и readback15/15 сравниваются побайтно/структурно и не меняются.

Дельта фиксирует **48 PASS = 26 integration + 20 controller + 2 независимые проверки**; два lifecycle-блокера исправлены в source 0.2. Старый staging `0c405…` не разрешается активировать. Последний собственный source-stage run **44154217772 / job 134290449539**, comment `6957935205`, source `c49ee68d34fc9e0890a234fbff48d0c0e4132fe5` успешно установил **12 файлов / 98 385 B**, все 12 `created=true`, pins bundle `ee142…` совпали. Статус **SOURCE_INSTALLED_NOT_BOUND**: runtime не импортирован и не связан с host; запросов/загрузок модели, новых сервисов и workers — 0.

Исходный `HOLD_DIRECTORY_OWNER_OR_MODE` сохранён в истории. Наш более ранний read-only probe run **44153563662 / job 134288122505** завершился за **20.63 мс**: тогда destination отсутствовал, файлов 0/12, priority `0775`, CHAT_ACTIVE `1 → 1`, без записей/сети/locks. Следующий **отдельный run O1 44153572961 / job 134288583621** изменил права priority/root на `0755`, proxy и 9 supervisor configs на `0644`, сохранив bytes. Chat-установка O1 осталась на `HOLD_FILENOTFOUNDERROR`, `installed=false`, заменённых файлов 0. Это разные действия разных исполнителей. Старый диагностический снимок не описывает состояние после успешного source staging.

Native v4 run `44147786817` создал один QA-диалог и отправил один model request, затем завершился HOLD. Последний read-only run **44153064827 / job 134286323528** подтвердил авторизацию и точную доставку HTML/CSS/JS, но чтение истории вернуло **HTTP 422 / INVALID_LIMIT**, итог `HOLD_HISTORY_HTTP_OR_JSON`. Вторая команда O0 воспроизвела ошибку передачи query: wrapper включает bytes `url.query` в f-string, лишняя пунктуация доходит до parser limit. O0 готовит ASCII-decode исправление; нативная установка этого исправления и успешное чтение истории пока не подтверждены. Ответ диагностики — `application/json`, 25 B, SHA `c72ee0295be63b2e06c1de1ec0b5c22e9dd197c48172348d9a6317799dc73a61`; raw contents не сохраняются. Запросов модели, создания диалогов и STOP в read-only запуске — 0. Это UI asset PASS; visual, history и native canary PASS не заявляются.

Предыдущий run `44150997251` с `HOLD_MAINTENANCE_BUSY` сохранён в `NATIVE_OUTCOMES.history` и попадёт в `runtime02_delta.native_outcome_history` и `native_release.read_only_reconciliation.previous_outcomes`. Новый результат не стирает прежнюю попытку.

## Два места для фактических native outcomes

В `NATIVE_OUTCOMES.json` находятся `source_stage` и `readonly_reconcile`. Каждый содержит `state`, `run_id`, `job_id`, `source_commit`, `receipt`. Сейчас оба слота имеют `state=OBSERVED`: source staging установлен без binding, read-only история остаётся HOLD. Два прежних HOLD сохранены в history. Root может записать следующий фактический sanitized receipt этой командой (JSON-файл содержит непосредственно data или `{kind,data}`):

```text
python delta.py record --kind source_stage --receipt /ABS/ACTUAL_STAGE_RECEIPT.json --run-id ACTUAL_RUN --job-id ACTUAL_JOB --source-commit ACTUAL_40_HEX
python delta.py record --kind readonly_reconcile --receipt /ABS/ACTUAL_RECONCILE_RECEIPT.json --run-id ACTUAL_RUN --job-id ACTUAL_JOB --source-commit ACTUAL_40_HEX
```

`record` сохраняет только допустимые поля/метаданные и обновляет preview; сетевых/native вызовов не делает. Перед заменой наблюдавшегося результата сохраняет его в history; повтор той же квитанции не создаёт дубль. Для успешного staging проверяет точный bundle/directory, 12 file pins и отсутствие activation/model effects. Для reconciliation проверяет `mode=reconcile`, 0 dialogs, 0 model requests, отсутствие STOP и `native_canary_pass=false`. Unknown/early receipt с недостаточным scope не дополняется выдуманными нулями — его нужно передать как отдельную историю для разбора. Успешный history readback не восстанавливает потерянные terminal flags/timings.

Обычный `python delta.py preview` также обновляет `DELTA_PREVIEW.patch`, `DELTA_CURRENT_SECTION.md` и `PREVIEW_RECEIPT.json`. Результат детерминирован при одинаковых inputs/outcomes. SHA в receipt — кандидаты; это не опубликованные SHA.

## Применение после root fresh Drive guard

Сначала root делает свежий raw download/readback **всех пяти прежних Drive ID**. Guard должен содержать `same_drive_ids=true`, `all_five_verified=true`, `verified_utc`, пять records `{file,drive_id,bytes,sha256,byte_exact:true,matches_frozen:true}`. Timestamp должен быть не раньше подготовки `BASE_SHA256.json` и не старше15минут; прежний18:20 readback не подходит. Если Drive или локальные bytes изменились, apply HOLD: требуется отдельное согласование/merge, а не перезапись.

```text
python delta.py apply --drive-guard /ABS/FRESH_DRIVE_READBACK.json
```

`apply` — только локальная операция root после свежего guard. Создаёт проверенную backup-папку, проверяет исходные SHA всех пяти файлов до записи, пишет через временные файлы/fsync/replace и сверяет результат. Публикация Drive/Library выполняется root отдельно, в прежние ID. Root должен удерживать свой общий write claim на эти документы: атомарность всей пятёрки против несогласованного внешнего writer не заявляется. При прерывании root сначала сверяет `LOCAL_APPLY_RECEIPT.json`, backup и реальные SHA, не выполняет слепой повтор.

## Проверка

Предыдущая ревизия прошла три targeted tests: детерминизм/no-loss/payload checksum; stale guard не меняет bytes, fresh guard работает только на временных копиях с точным backup; ложная activation и повторный model request отклоняются, история HOLD сохраняется без дублей. При последней factual delta дополнительные suite не запускались: штатный preview заново проверяет исходные SHA, сохранность Markdown/структур, 240/54/9/15 и payload hash, а `record` проверяет точные 12 pins и отсутствие activation/model effects. Пять настоящих release-файлов не изменены. Внешних записей/native calls — 0.

**NEXT_READY:** подготовка исправления query в существующем wrapper и read-only проверка того же диалога остаются у O0. Не повторять генерацию и не объявлять исправление нативно установленным без нового receipt. Установленный source runtime остаётся без binding; дальнейшая интеграция и приёмка принадлежат существующим O1/O5. Root выполняет fresh Drive guard и затем применяет и публикует дельту в прежние ID, сохраняя все предыдущие попытки.
