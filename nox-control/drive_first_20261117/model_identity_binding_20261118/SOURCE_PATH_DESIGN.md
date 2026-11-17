# NOX: привязка самоописания к проверенному runtime

Статус: **рабочий source-кандидат подготовлен и локально проверен; на сервере ещё не установлен**.
FD-first audit V2 `44192038242` завершился успешно и принят по lossless raw SHA
`f430bfb1…`. Текущий reference процесса: `DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf`;
это не проверка содержимого весов. Конкретная реализация, границы и transaction
описаны в `README.md`; этот документ сохраняет причину выбора source seams.

## Подтверждённая причина

| Источник | Проверенный факт | Следствие |
|---|---|---|
| `chat_proxy.py`, SHA `b202301a…`, `_build_messages` | Постоянный `NOX VERIFIED SELF-MODEL CONTRACT` требует фактов, но сам не содержит runtime model identity | Общий контракт не заменяет данные о модели |
| Тот же source, `_proxy_completion` | Вопросы о себе обходят ранний `_understanding_http`; простой вопрос «какая модель» отсутствует в явном списке | Нужен отдельный узкий классификатор вопроса о текущей модели |
| `owner_chat_stream.py`, SHA `2c4ae86d…`, `owner_request_query` | Использует status/media/download классификаторы | Это существующая точка обхода раннего legacy ответа без нового endpoint |
| Тот же source, `_run(native, url, payload, user_text)` | Получает уже выбранный completion URL; здесь после `_current.augment_messages` начинается общий model/tool loop | Можно сопоставить факт именно с выбранным маршрутом, включая fallback |
| `chat_proxy.py`, `_trim_ctx` | Удаляет переменный system tail; имеет отдельный real-token trimming | Простое добавление фактов в конец prompt не гарантирует их сохранность и может превысить бюджет |
| `nox_agent_pool_t858u.py`, SHA `53c9b068…`, `prepare_payload` | Добавляет/сохраняет фиксированный префикс и cache flag; сам не ограничивает контекст | Он не заменяет budget gate для новых runtime facts |
| Native V1, raw SHA `32d4a6cc…` | `status.json` старше 390964.594 с, содержит `nox-s1-l05-Q4_K_M.gguf`; backend настроен на alias `deepseek-v41-flash-iq2xxs` и другой GGUF reference | Status label, config alias и runtime argument нужно хранить раздельно |

## Конкретная реализация

1. **Материализовать один проверенный fact snapshot.** Из принятого V2 audit
   local builder создал, а root устанавливает отдельную атомарную owner-only запись
   `/root/nox/state/verified_model_reference.json` со schema/version, временем,
   native run/request/source, PID/start, argv/exe hashes, port/socket inode,
   GGUF basename и evidence scope. Запись не меняет `backend.json`, не
   переименовывает веса и не перезапускает модель. Producer обязан принимать
   только результат с проверенным before/after listener binding. Дисковый
   status и config alias сохраняются отдельными полями provenance.

2. **Добавить `owner_model_reference_binding.py`.** Малый module читает только
   этот фиксированный файл с `O_NOFOLLOW`, проверкой root ownership, mode0600,
   лимитом 8192 байта и точной JSON schema. Отсутствие/неверный snapshot означает
   `UNVERIFIED`, а не подстановку имени из плана. В обычных сообщениях модуль
   не выполняет I/O. На вопросе о модели сверяет свежий PID/start, pinned argv
   hash, конфигурационный route и записанный socket descriptor; перепроверяет
   fingerprint и socket в каждом подходящем вопросе без cache устаревшего имени. Приватные аргументы, ключи и environment не читает.

3. **Использовать настоящий URL хода.** Binding принимает аргумент `url` из
   `owner_chat_stream._run`. Факт для `127.0.0.1:8098` не переносится на
   `127.0.0.1:8085`. При fallback можно сообщить, что используется резервный
   маршрут; имя модели резервного процесса остаётся неподтверждённым до его
   собственной проверки. Это устраняет неоднозначность двухсекундного
   upstream cache и избегает утверждения, что config предсказывает прошлый ход.

4. **Изменены только нужные source seams.** `owner_request_query` получил
   full-match predicate самостоятельного вопроса о модели. В начале `_run`
   добавлен узкий no-tools вызов того же `_model_events` с actual URL. Остальные
   statements existing model/tool loop совпадают по AST. `chat_proxy` пропускает
   старый trim только для этого вопроса; составные команды и общая беседа идут
   прежним путём. Ответ по context формирует модель, готовой реплики нет.

5. **Контекст ограничен явно, без обещания точного token count.** Сохраняются
   fixed prefix до variable tail и исходный вопрос; добавляется bounded fact
   block после всех прежних trimming этапов. Получаются два сообщения без
   history/tool schemas: ≤8192 UTF-8 bytes, ответ ≤256 tokens. До 6144 bytes
   prefix и до1536 bytes runtime block. General tokenizer fallback использует
   configured backend и chars/2; эта отдельная проблема оставлена следующей
   задачей. Для ordinary chat нет нового network tokenizer или обязательного
   HOLD. Narrow standalone question при непригодном snapshot получает
   unverified context без старого имени; если слишком велик fixed prefix,
   helper fail-closed вместо молчаливого удаления факта.

6. **Дать NOX факты, а не ещё один длинный монолог.** Runtime block содержит
   имя reference, scope, время и источник. Контракт запрещает придумывать
   происхождение/обучение; он не должен воспроизводиться целиком в ответе
   «какая модель». Ответ формирует сама модель по текущему вопросу. Архитектура,
   полнота весов, LoRA, обученный контекст и субъективное сознание не выводятся
   из имени GGUF.

7. **Показать provenance в API отдельно от label.** Если потребуется UI,
   добавить read-only `model_reference` объект рядом с нынешним `primary_model`.
   Не превращать непустую строку `primary_model` в доказательство готовности;
   существующий health/native binding gate по-прежнему проверяется независимо.
   Смена PID/start, socket ownership или route немедленно инвалидирует факт.

## Проверки перед установкой

| Сценарий | Требуемое поведение |
|---|---|
| Текущий PID, socket и выбранный URL совпали | В model context доступен точный basename с provenance |
| Старый status и новый config расходятся | Runtime fact имеет отдельный источник; разница не скрывается |
| PID перезапущен или argv hash изменился | `UNVERIFIED`; старое имя не называется текущим |
| Выбран fallback8085 | Факт8098 не применяется |
| Snapshot отсутствует, oversized или symlink | Bounded отказ без чтения посторонних файлов |
| В аргументе credential значение выглядит как `--model=` | Значение не выводится и не становится моделью |
| Длинная история | Для standalone question сохранены fixed prefix + question + fact, UTF-8 byte bound соблюдён; exact token count unknown |
| Обычный разговор без вопроса о модели | Никакого нового файлового/сетевого запроса на горячем пути |

Установка — одна source-pinned транзакция существующего OneHost repair route
с одним stop/start nox-proxy, fresh lease/owner-idle/PID/source gates и симметричным
откатом. Pending O2 само по себе не блокер; prospective O5 source prerequisites
нужно согласовать с фактическим новым postimage до будущего O5 cutover. Создание fact snapshot отдельно и не
означает разрешения на обучение, загрузки весов или сброс shared counter.
V2 audit и завершённый transport witness не повторяются ради проверки этого
плана. Для новой интеграции потребуется только один её собственный целевой
чат после source/fixture проверки и согласования с текущим cutover.
