# O5: подключение опубликованного adviser worker

## Готовый источник и реальная граница

Root опубликовал commit `0443eb4270d7072d8241fdb16ed5eb9316e81a51` в существующем GitLab-репозитории `s-grouptwet/nox-helion-pp-private-build`, ветка `source/nox-web-v15-onehost-execution-kit-20261117`. Target: `handoff/20261117/nox-v15-kit/execution/optimization/O5/host.py`. SHA-256: `ad51ad815ac680c07f5eed7799939e0045c04df89c1ca190c2fdcdfb4aa50ecf`. По подтверждению root, host, focused test, исходная source-квитанция и независимый review перечитаны 4/4 byte-exact. Это публикация исходника; работающий native adviser ещё не подтверждён.

Используется существующая функция `existing_worker_handler(...)` и существующий kind `nox.online_advice.v1`. Конкретный native module/function, который регистрирует этот kind и принимает его результат, в доступном shared source cache не установлен. Файл `owner_subagent_dispatcher.py` относится к **другому** kind `owner_native_subagent_review` и содержит неполный cached source; подменять им adviser binding нельзя. Имена `existing_untrusted_artifact_receipt` и `existing_queue_submit` из README базового пакета явно обозначают контракт, а не наблюдённые native symbols.

## Куда передать результат

| Граница существующего host | Точная форма из опубликованного кода | Что должен сделать O5 |
|---|---|---|
| `host_submit(kind, payload, idempotency_key)` | `kind='nox.online_advice.v1'`, key=`Consultation.request_id` | Связать с реальным native TaskID и прежней очередью; chat path только enqueue. Не считать произвольный WP/relay ID native TaskID. |
| `host_result_sink(advice_dict)` | Только словарь `Advice`; внешний envelope сюда не передаётся | Сохранить непроверенный совет в существующее хранилище артефактов, вернуть ACK после подтверждённой записи/readback. В callback нет `provider_advice` или внешнего `reconcile_required`. |
| Completion adapter вызова `existing_worker_handler` | `advice`, `native_result_receipt`, `host_lease`; при persistence failure также `provider_advice`, `persistence_state`, `reconcile_required` | Именно здесь, до обычного task ACK/requeue, сохранить и обработать весь envelope. Нельзя свести результат к `advice.status` или считать отсутствие Python exception успехом задачи. |
| `host_release_remote_lease(lease_id, fencing_token)` и существующий arbiter | `host_lease.release_uncertain=True` при отрицательном ACK/exception | Сверить конкретный lease/fence с authoritative arbiter. Не возвращать permit в пул по TTL или одному callback return. |

`reconcile_required` создаётся после завершения либо ошибки `host_result_sink`. Поэтому попытка исправить только сам sink не закрывает повторный запуск provider через общий retry диспетчера.

## Узкая последовательность интеграции

1. Владелец O5 получает действующий admission/claim и называет точный native registry/completion adapter для `nox.online_advice.v1`. Показать действующий task envelope и receipt-readback callback; нового API или таблицы этот handoff не предлагает.
2. Привязать опубликованный worker с сохранёнными аргументами `host_result_sink`, `host_acquire_remote_lease`, `host_release_remote_lease` и настоящим `CancelToken`. Фактический loaded source должен соответствовать SHA выше. Source-staging сам по себе не подтверждает import/registration.
3. До вызова worker существующая очередь фиксирует прежний operation/request key и native TaskID. После возврата completion adapter принимает **весь** envelope. При `reconcile_required=True` сохраняет доступный `provider_advice` и marker UNCONFIRMED в уже существующем pending/result журнале, оставляя задачу на сверке. Если сам журнал недоступен, исход остаётся UNKNOWN с удержанием владения; повторный provider POST этим не разрешается.
4. При ошибке sink сначала выполнить readback прежней записи по native TaskID/request ID. Сопоставить существующие поля `request_id`, `provider`, `requested_model`, `brief_sha256` и конкретный артефакт/его digest по правилам receipt store. Совпавшая запись закрывает lost-ACK; конфликт остаётся HOLD. Отсутствие ответа от хранилища не доказывает отсутствие записи.
5. Если запись подтверждённо отсутствует, повторить только сохранение уже полученного `provider_advice`, и только через доказанно идемпотентный существующий sink с тем же key. Не повторять `existing_worker_handler` или `client.consult`. Когда exact native sink не предоставляет такой гарантии, остаётся HOLD до решения владельца.
6. Независимо от внешнего `reconcile_required`, проверить `advice.outcome_uncertain`. Provider exception/cancel может дать `outcome_uncertain=True` при успешном sink ACK, без внешнего marker. Такой task нельзя автоматически отправлять провайдеру заново. `retry_after_seconds` не отменяет неопределённость уже отправленного запроса.
7. Отдельно обработать `host_lease.release_uncertain`, даже при `advice.status='OK'` и подтверждённом sink. Сверить exact `lease_id` + integer `fencing_token`; исход release не выводится из результата сохранения совета. Legacy `None` release ABI сохранён worker ради совместимости, но не является самостоятельным доказательством освобождения в native gate.
8. После подтверждённых readback и lease reconciliation завершить исходную task через существующий lifecycle. При следующей доставке того же key вернуть сохранённый receipt; provider вызов не повторять. Сохранить `authority='UNTRUSTED_ADVICE_NO_TOOL_AUTHORITY'`, `requires_host_verification=True`, `native_execution=False`: получение совета не делает его фактом S03 или разрешённым исполнением.

## Единственная нужная приёмка binding

Сначала синтетический сценарий на фактическом completion adapter без облачных ключей и внешнего HTTP. Fake provider возвращает один ответ; sink фиксирует его и теряет ACK. Затем очередь повторно доставляет тот же request key. Критерий: консультация ровно одна **на обе доставки**, readback находит первый артефакт, provider advice не потерян, task не получает ложный DONE до сверки.

В том же focused gate отдельно проверить успешный sink при `advice.outcome_uncertain=True`, явный sink `status='UNKNOWN'` и release uncertainty. Во всех ветках неопределённость блокирует опасный replay; это проверка конкретного host binding, не повтор 10 уже пройденных unit tests worker. Live provider запрос — отдельный следующий gate после binding, admission и актуальных условий аккаунта; этот handoff его не выполнял.

## Состояние владения

Опубликованный host, его source receipt и независимый review не менялись в этой эстафете. Native/O5 claims не прочитывались заново и не изменялись; cached RELEASED source claim не считается release вложенного native binding. Все действия автора здесь — локальная актуализация publication metadata и этого handoff. Точное native имя callback остаётся входом O5, а не выдуманной готовностью.
