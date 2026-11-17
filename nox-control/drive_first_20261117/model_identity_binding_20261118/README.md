# NOX: текущая модель в живом Резонансе

**Готовый source-кандидат; на сервере ещё не установлен.** Native audit
`44192038242` завершился успешно. Его lossless result принят отдельно:
`NATIVE_SEMANTIC_ACCEPTANCE_44192038242.json`.

## Что меняется

Короткие самостоятельные вопросы «какая модель в твоей основе?», «какая у тебя
модель?», «какой GGUF у тебя сейчас?» и английские эквиваленты попадают в
существующий owner model SSE, минуя legacy early-answer и ненужный inventory.
Ответ генерирует выбранная модель. Готовой ответной реплики в коде нет.

Для этого узкого вопроса отправляются два сообщения: постоянный system prefix
с существующим self-model contract, проверенные runtime данные и исходный
user question. История, variable status/memory tail и tool schemas не нужны
для самостоятельного вопроса о текущей модели. Составные команды, сравнения,
примеры в кавычках и обычный диалог остаются в прежнем loop; все его statements
сверены по AST без изменений. Общие подтверждения, cancel, S03 postflight,
stream parsing и удержание owner activity не переписаны.

## Доказательство текущего reference

`verified_model_reference.json` — 1204-байтный snapshot, полученный только из
точного принятого raw audit SHA `f430bfb1…`, без полного argv, секретов и весов.
В нём зафиксирован basename:

`DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf`

Каждый подходящий вопрос сверяет actual selected completion URL, PID/start,
argv hash, exe/cwd hash, UID, namespace, FD/inode и принадлежащую этому процессу
строку LISTEN:8098. TCP читается до собственной строки с ограничениями,
а не целиком. Fingerprint и socket проверяются повторно. Никаких health,
tokenizer, model, внешних HTTP-запросов в helper нет.

Старое время audit остаётся provenance. Свежесть даёт повторный fingerprint,
а не переименование старого статуса. На fallback:8085 факт :8098 не переносится.
При смене процесса/сокета, отсутствии или некорректности snapshot в контекст
идёт `unverified` без старого basename. Новый процесс требует нового проверенного
snapshot. Прежний health не выдаётся за повторно проверенный.

Это **reference файла из argv принадлежащего процессу слушающего socket**.
Содержимое весов, архитектура, обучение, глобальная уникальность listener,
атомарность наблюдения и backend прошлого ответа остаются неподтверждёнными.

## Бюджет и скорость

Обычные сообщения выполняют только bounded full-match классификатор. Для
подходящего standalone вопроса отключён старый предварительный `_trim_ctx`,
который иначе считал бы сообщения через configured backend и мог отрезать
facts. Новый helper сохраняет постоянный prefix до variable tail и добавляет
малый block в самом конце; после него trimming не вызывается.

Пределы: вопрос ≤240 символов/640 UTF-8 байт, prefix ≤6144 байт, fact block
≤1536 байт, сумма двух сообщений ≤8192 байт, ответ ≤256 токенов, tools отсутствуют.
**Это byte bounds, не доказанный точный token budget.** Токенизация и вместимость
конкретного runtime window не переобъявлены. Общая проблема `_count_msg_tokens`
(configured URL, chars/2 fallback, tool reserve) вынесена в следующую отдельную
задачу; новый обязательный network tokenizer для обычного чата не добавлен.

Runtime snapshot читается mode0600/root owner/no-follow, ≤8192 байт. Локальная
проверка ограничена 700000 прочитанных file/proc bytes, 262144 bytes/4096 rows
на TCP scan и cooperative 0.25s. Это не жёсткая гарантия wall time системного
вызова. Установка snapshot и source не вызывает модель и не скачивает веса.

## Файлы и source pins

| Файл | Назначение |
|---|---|
| `owner_model_reference_binding.py` | Narrow question, bounded readback, two-message model request |
| `verified_model_reference.json` | Snapshot только принятого audit V2 |
| `build_model_reference_snapshot.py` | Детерминированная local materialization по exact raw SHA |
| `source_transform.py` | Exact-source transform + AST scope + exact reverse |
| `IDENTITY_ROUTE.patch` | Дельта двух установленных файлов |
| `SOURCE_TRANSFORM_RECEIPT.json` | Pre/post SHA и размеры |
| `test_model_reference_binding.py` | TempFS, race, source inverse и mocked SSE проверки |

`chat_proxy.py`: `b202301a…` → `30207a85…`, 103637 →103831 B.
`owner_chat_stream.py`: `2c4ae86d…` → `38f4dc29…`, 26210 →26955 B.
Source source transform fail-closed при любом расхождении исходных SHA.

## Установка одной согласованной транзакцией OneHost

Координатор использует уже успешный OneHost owner repair route из `be4750…`
(installer `dff6a384…`). Перед остановкой только `nox-proxy` проверяются existing
maintenance lease, fresh owner idle + model slots, proxy PID/start/config и
source CAS. Общая незавершённость O2 сама по себе не блокирует этот отдельный
краткий proxy update. Этот source-пакет native-команд не отправляет.

1. Записать helper как `/root/nox/scripts/owner_model_reference_binding.py` и
   snapshot как `/root/nox/state/verified_model_reference.json` с root:root0600,
   через existing pinned installer, metadata/byte verification и atomic rename.
2. Применить exact transform к двум pinned источникам; сохранить оригинальные
   bytes/metadata и проверить post-SHA. Source helper и snapshot должны быть
   доступны до loading patched imports.
3. Установить identity + выбранный menu fix в одном owner repair batch с одним
   stop/start только `nox-proxy`. Модель, очередь и S03 не сбрасывать. Новые
   source pins согласовать с prospective O5 пакетом до его будущей установки;
   не запускать конкурирующие source transactions.
4. После source gate проверить один вопрос именно этой новой интеграции через
   новый Резонанс. Завершённые canary `44177251374`, cancel witness `44187317953`
   и audit `44192038242` повторять не требуется.

Откат: exact inverse двух source postimages при совпадении post-SHA; восстановить
предыдущие helper/snapshot, если они существовали, либо убрать только созданные
этой транзакцией файлы по их exact installed SHA. STOP, shared counter, чужие
processes и веса не затрагиваются. Установка ещё не выполнена.

## Проверка кандидата

Первые 10 уникальных тестов: 9 PASS; один test harness ошибочно применял TempFS
UID к root audit producer. Исправлена только изоляция fixture. Повторён этот
тест и добавлен один regression о исчезающем namespace/закрытии FD: оба PASS.
Затем точный вопрос QA «Какая модель в твоей основе сейчас?» получил один
optional matcher suffix и один адресный тест с тремя cases. Всего 12 уникальных
проверок успешно завершены; full suite повторно не гонялся.
Включены реальная TempFS подмена FD после match, большой unrelated TCP tail,
fallback без I/O, неизменность generic owner loop и одно mocked SSE generation.

Независимый review frozen base и единственного matcher delta: PASS. Следующая
READY — source publish и минимальный существующий OneHost install route,
согласованный с координатором. Следующая отдельная инженерная задача — exact
token accounting для actual selected URL и tools без silent chars/2 fallback.
