# NOX: шесть исполнимых исправлений и самостоятельная задача чата

Дата проверки: 18 ноября 2026 года. Подготовлены шесть закреплённых планов изменения существующего кода для четырёх очередей общего пула NOX. У каждого плана есть точные исходные байты, исправление, неизменяемые тесты, сравнение preimage перед записью и ограниченная приёмка `SOURCE_PATCH_TESTED`. Полная приёмка исходных TaskID в этом пакете не добавлена: `original_task_accepted=false`.

## Что исправлено и чем подтверждено

| TaskID / очередь | Изменение и его причина | Исходная версия | Исправленная версия |
|---|---|---:|---:|
| `3A02` / Q2 | Повторная проверка разрешения после входа в соединение S03 предотвращает SQL-чтение, если разрешение отозвано при открытии соединения. | 13 тестов, 1 failure | 13/13 PASS |
| `3A03` / Q2 | Внешний callback финальной ревизии выполняется вне mutex кеша; отзыв доступа может завершиться, а устаревший read ticket не публикует результат. | 10 тестов, 1 failure | 10/10 PASS |
| `6V14-04` / Q1 | Выбор последней квитанции сравнивает действительные моменты времени с UTC offset. Прежняя строковая сортировка давала неверный порядок и cutoff. | 36 тестов, 3 failures | 36/36 PASS |
| `3B05` / Q2 | Доказательства навыка и маркеры отвергают JSON с повторными ключами и неограниченными числовыми значениями. Такие данные прежде могли подтверждать навык. | 10 тестов, 3 failures | 10/10 PASS |
| `4A02` / Q3 | Каждая train/dev/holdout выборка обязана содержать все требуемые категории задач. Общая совокупность категорий прежде скрывала неполную отдельную выборку. | 35 тестов, 3 failures | 35/35 PASS |
| `0V14-14` / Q4 | Имена overlay manifest проверяются как канонические относительные пути; исходные symlink запрещены. Прежняя реализация позволяла `../` перезаписать файл вне выходного каталога. | 6 тестов, 4 failures, 1 error | 6/6 PASS |

Итого: **110/110 тестов на исправленных версиях**. Все шесть исходных версий воспроизводят регрессии. Точные source/test/log SHA и результаты находятся в [local_fail_pass.json](local_fail_pass.json); исполнимые планы и preimage/postimage SHA — в [plans_index.json](plans_index.json). Существующие тесты включены там, где они доступны. Проверка Q4 не объявляет транзакционность всего merge; проверка Q3 не запускает обучение и не подтверждает получение новых весов.

## Закреплённые источники

Все ссылки ниже указывают на один GitLab commit `78ee41fb4ac1e48128fdce2eb25e52d40c70cc15`, а не на движущуюся ветку:

- [3A02 — s03_existing_readback.py](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/blob/78ee41fb4ac1e48128fdce2eb25e52d40c70cc15/handoff/20261117/nox-v15-kit/execution/pass49/role3/s03_existing_readback.py)
- [3A03 — durable_runtime.py](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/blob/78ee41fb4ac1e48128fdce2eb25e52d40c70cc15/handoff/20261117/nox-v15-kit/execution/automation/A1/cache-race/source/durable_runtime.py)
- [6V14-04 — work_progress.py](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/blob/78ee41fb4ac1e48128fdce2eb25e52d40c70cc15/handoff/20261117/nox-v15-kit/server/work_progress.py)
- [3B05 — owner_dispatcher_mentor.py](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/blob/78ee41fb4ac1e48128fdce2eb25e52d40c70cc15/handoff/20261117/nox-v15-kit/integration/owner_mini_source/owner_dispatcher_mentor.py)
- [4A02 — forge_split_guard.py](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/blob/78ee41fb4ac1e48128fdce2eb25e52d40c70cc15/handoff/20261117/nox-v15-kit/server/forge_split_guard.py)
- [0V14-14 — merge_web_source.py](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/blob/78ee41fb4ac1e48128fdce2eb25e52d40c70cc15/handoff/20261117/nox-v15-kit/execution/pass49/role5/merge_web_source.py)

Зависимость V38 [synaptic_brain.py](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/895c5ed3f5e08b8c473e873aed768ac56e60767f/nox_runpod/teacher_mesh/v38/synaptic_brain.py) закреплена отдельным GitHub commit `895c5ed3f5e08b8c473e873aed768ac56e60767f`. Полные source refs и проверенные Git blob/SHA256 сохранены в [seed_manifest.json](seed_manifest.json).

## Самостоятельное исправление NOX — 1A03

Исходные request ledger и bridge допускают создание/восстановление запроса и запуск inference до отказа по reconnect cursor, который опережает сохранённые события. Контракт требует отклонить такой cursor до этих побочных эффектов. В seed сохранены исходные файлы; NOX должен сам получить исправление через model planner и проверяемый исполнитель.

Защищены **30 тестов: 22 неизменённых исходных и 8 новых**. Baseline даёт четыре failures; отдельная контрольная версия проходит 30/30. Эта контрольная версия исключена из передаваемых исходников и blobs. Это пока доказательство выполнимости контракта, а не результат исполнения NOX. Окончательный model contract принадлежит координатору; точные имена и SHA защищённых тестов перечислены в [protected_test_context_30.json](proof_1a03/protected_test_context_30.json).

После исполнения требуется проверить реальные model postimages и полный diff. Затем `1A02` получит последовательный план по фактическому SHA того же ledger/bridge, без конфликта с исправлением `1A03`.

## Упаковка и границы приёмки

Замороженный seed содержит **27 файлов, 289901 байт**. SHA256 файла `seed_manifest.json`: `6873b8cd5001419cc9fab4fe43c7438eb36481b4d50608682e89bba9f30c79d6`; digest отображения файлов: `337bb0d35d44fcfb8d2e7e4eab36b3141145b371837049ef4438ba22c040cf8d`.

Это отдельная рабочая копия проектных исходников. Fresh native probe обнаружил обслуживающий модуль `/root/nox/scripts/nox_v29_chat_bridge.py` с другим именем и SHA; установка кандидатов в source workspace сама по себе не доказывает изменение работающего backend.

[all295_execution_disposition.json](all295_execution_disposition.json) сохраняет все 295 исходных ID и маршрутизацию 145 / 71 / 34 / 45: шесть готовых scoped plans, один model challenge, одна зависимость `1A02`, 11 сохранённых исторических verified и 276 пунктов без новой исполнительной привязки. Число непривязанных пунктов не является числом дефектов. Прежние claims/receipts этим overlay не переписываются.
