# NOX Mind v4.1 — отчёт об изолированной staging-интеграции

**Статус: STAGING. Не сливать.** Это не установка в runtime и не допуск в production.

- Ветка: `cursor/nox-mind-v41-staging-4bce` (суффикс `-4bce` обязателен для ветки агента; пример из задания был короче).
- База: `origin/main` на момент отчёта, коммит `347b2221940ba519e8b494698f35736e5727c295`.
- Коммит интеграции (пакет, адаптеры, планировщик, тесты): `2d25a4b6c9a24b18533a2909a4d074dfbb948bf6`.
- Журнал ниже ссылается на этот SHA. Коммит с отчётом и CSV идёт следом и не может содержать собственный SHA внутри себя.
- Ветка не основана на PR #162 и не меняет его ветку. В `main` ничего не влито.
- Production-модули, workflows, выходы EXE и эталонный EXE `93a329ba1ece9cfd66951b377e04e9c1166ec6ba3ce13a5911ba8e36de99dfb8` не изменялись.

## Что положено в репозиторий

Архив `NOX_MIND_V41_STAGING_20261117` распакован без правок исходников пакета в `staging/nox_mind_v41/`. Версия пакета: `0.1.0-staging-20261117`. Зависимостей вне стандартной библиотеки нет.

| Путь пакета | Содержимое |
| --- | --- |
| `nox_mind_v41/bitemporal.py` | Факты с 4 метками времени (`valid_at`, `invalid_at`, `created_at`, `expired_at`), supersession, мягкий retire, UCB-ранжирование |
| `nox_mind_v41/warm_cache.py` | `WarmS03Cache` (LRU+TTL) поверх `ScopedFTS` (FTS5), инвалидация по PersonaID через счётчик поколения |
| `nox_mind_v41/graph_memory.py` | Узлы episodic/semantic/procedural/working, рёбра, эмоции, consolidate, checkpoint/resume |
| `nox_mind_v41/decision_context.py` | Правила из поправок владельца в bi-temporal store |
| `nox_mind_v41/persona.py` | Persona, EmotionState, validation, ConsistencyChecker |
| `nox_mind_v41/reflection.py` | self-refine, Reflexion, plan-then-execute, ReAct, self-consistency, ToT-lite, CoT monitor, budget→effort |
| `nox_mind_v41/control.py` | Пресеты V4.1 и hysteresis hot/cold |
| `nox_mind_v41/idle_consolidate.py` | Idle-консолидация; по умолчанию dry-run; STOP-флаги дают `HOLD_STOP_FLAG` |
| `tests/test_mind.py` | Исходные тесты пакета, файлы не редактировались |

Рядом, отдельным слоем, добавлен `staging/nox_mind_v41_adapters/`. Production-код этот каталог не импортирует.

Флаг `NOX_MIND_V41_STAGING` по умолчанию выключен. Включёнными считаются только значения `1`, `true`, `yes`, `on` (после trim, без учёта регистра), и только если конструктор адаптера вызван с `enabled=None`. Явный `enabled=False` остаётся выключенным даже при переменной `=1`. Явный `enabled=True` включает адаптер без переменной. Ни один существующий модуль этот флаг не читает.

## Чего в репозитории нет

Поиск по дереву до добавления staging (и повторно по `origin/main`) не нашёл вызываемого API памяти S03, API постановки задач диспетчера и типов `CoreID` / `PersonaID`.

Что есть на самом деле:

- **S03 как путь и запрет, не как API.** `nox_runpod/stage0/a40_full_parameter_distill_cycle.py` и `nox_runpod/control/nox_master_poller.py` ссылаются на хостовый файл `memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3`. Единственное чтение схемы в репозитории — `SELECT content, teacher, content_sha FROM knowledge` в режиме read-only. Файла sqlite в git нет. `nox_cold_drive.py` отвергает пути, в частях которых есть `s03`. `nox_dispatcher_advisor.py` при `s03.readback_verified != true` выдаёт совет `S03_NOT_VERIFIED` и не пишет в базу.
- **Диспетчер как внешний OneHost.** В репозитории есть имя юнита `nox-dispatcher.service`, read-only `nox_dispatcher_advisor.assess` и хостовые пути `dispatcher/` в скриптах Runpod. README self-heal прямо говорит, что единственный scheduler — существующий OneHost dispatcher. Метода постановки задачи нет.
- **CoreID и PersonaID.** В коде репозитория вне этого staging-слоя совпадений нет. `PersonaID` существует только внутри распакованного пакета. `CoreID` в пакете тоже нет: это поле staging-привязки, введённое здесь, потому что типа в репозитории нет.

Поэтому адаптеры реализуют минимальные `Protocol` (`S03MemoryPort`, `DispatcherPort`, `IdentityPort`) и in-memory фейки (`InMemoryS03`, `InMemoryDispatcher`, `InMemoryIdentity`). Фейк диспетчера всегда пишет `submitted: false`. Это не интеграция с кодом, которого нет.

`open_staging_memory` по умолчанию открывает `:memory:`. Путь, в котором есть `NOX_UNIFIED_S03` или `unified_nox_knowledge`, отвергается (`StagingRefused`). Хостовая база не открывается.

## Карта адаптеров

| Запрошенное отображение | Staging-объект | Куда идёт вызов | Что не делается |
| --- | --- | --- | --- |
| S03 read/write | `S03MindAdapter.read` / `write` | `BiTemporalStore.assert_fact` / `current` / `rank`; `WarmS03Cache.write` / `recall`; `GraphMemory.write` / `recall`. Повтор той же тройки (persona, subject, predicate, object) остаётся идемпотентным, как `assert_fact`: новый эпизод и инвалидация кэша не добавляются. Необязательный `port` — зеркало во `InMemoryS03`, не вторая база. | Нет записи в `knowledge`. Нет открытия host sqlite. |
| dispatcher | `DispatcherPlanAdapter.submit` / `submit_goal` | Единственный цикл пакета, который вызывается: `reflection.plan_then_execute`. Тело запроса собирает `control.request_body(preset)` (по умолчанию пресет `tool_agent`). Если передан snapshot, читается существующий `nox_dispatcher_advisor.assess` через `importlib` (файл не правится). `urgency` `safety` или `hold`, а также коды `STOP_ACTIVE` и `S03_NOT_VERIFIED`, дают статус `HOLD`: llm и tools не вызываются. Если переданы `graph` и `task_id`, шаги пишутся в `GraphMemory.checkpoint` этой staging-памяти. Запись остаётся в списке `admissions` с `submitted_to_host: false`. | Нет контакта с `nox-dispatcher.service`. Нет второго scheduler в systemd. Тело запроса никуда не отправляется. |
| CoreID / PersonaID | `PersonaIdentityAdapter`, `IdentityBinding(core_id, persona_id)` | Карточка и system block — `Persona` + `EmotionState`. Смена `persona_id` вызывает `WarmS03Cache.invalidate_persona` у предыдущего id. Смена только `core_id` при том же `persona_id` поколение кэша не увеличивает: пакет кэширует по PersonaID, не по CoreID. `switch_persona(id)` без объекта `Persona` сбрасывает карточку, потому что голый id не несёт черт. | Нет production-типа, от которого можно было бы прочитать текущий CoreID. |

Вызов выключенного адаптера поднимает `StagingDisabled` до любого обращения к store, кэшу, графу, llm или tools.

## Планировщик инструментов

Модуль: `staging/nox_mind_v41_adapters/scheduler.py`, класс `ToolScheduler`. Только stdlib. Потоки и процессы не запускаются: порядок задаёт вызывающий код через `pop_next` / `execute_next`, поэтому тесты детерминированы. Это не замена OneHost.

Классы: `SAFETY = 0`, `USER_FACING = 1`, `BACKGROUND = 2`. Меньший класс выполняется раньше.

Ключ порядка: `(effective_class, sequence, call_id)`.

- `sequence` растёт на каждый `submit`, поэтому внутри одного эффективного класса порядок — FIFO по постановке.
- `call_id` — полный тай-брейк.
- Старение: `steps = floor(ожидание / aging_quantum)`. У вызовов не из `SAFETY` эффективный класс равен `max(USER_FACING, base - steps)`. Состарившийся background доходит до класса user-facing и обгоняет более поздний user-facing, но не обгоняет `SAFETY`. Сам `SAFETY` не стареет.
- Дедлайн — момент старта на переданных часах. Пока вызов в очереди и `now > deadline`, статус `EXPIRED`, функция не вызывается. Равенство `now == deadline` ещё допустимо.
- Таймаут — бюджет от `started_at`. Когда `now > started_at + timeout`, слот освобождается, статус `TIMED_OUT`, опоздавший результат отбрасывается. Принудительно убить callable стандартная библиотека не может; таймаут считается по часам, которые передаёт тест или `time.monotonic`.
- Отмена очереди ставит `CANCELLED`. Отмена уже идущего вызова только поднимает флаг; callable может проверить его и бросить `Cancelled`.
- Лимит конкуренции — максимум вызовов в статусе `RUNNING`. `pop_next` возвращает `None`, пока слоты заняты.
- Часы по умолчанию: `time.monotonic`. Тесты подставляют свой счётчик и явный `now`.

Планировщик нигде не регистрируется и не включается флагом сам по себе: объект создаёт только вызывающий тест или будущий staging-код.

## Результаты тестов

Интерпретатор: Python 3.12.3. Команды запускались с `python3 -B` из корня репозитория. Счётчики ниже сняты с этого прогона после последней правки адаптера и планировщика.

Пакет, файлы не менялись:

```text
python3 -B -m unittest discover -s staging/nox_mind_v41/tests -p 'test_mind.py' -v
Ran 10 tests in 0.013s
OK
```

Десять методов: `test_supersession_asof`, `test_ucb`, `test_presets_hysteresis`, `test_correction_learning`, `test_types_edges_affect_consolidate_checkpoint`, `test_idle_job`, `test_persona_emotion`, `test_loops`, `test_scope_cache_invalidate`, `test_ttl`.

Адаптеры и планировщик одним discover:

```text
python3 -B -m unittest discover -s staging/nox_mind_v41_adapters/tests -p 'test_*.py' -v
Ran 19 tests in 0.007s
OK
```

Из них `test_adapters.py` — 12 тестов (S03: 5, dispatcher: 4, identity: 3), `test_scheduler.py` — 7 тестов (`test_priority_and_fifo_are_deterministic`, `test_aging_avoids_starvation_without_passing_safety`, `test_deadline_expires_before_start`, `test_timeout_releases_slot_and_discards_late_result`, `test_cancel_queued_and_running`, `test_concurrency_limit_and_failure_frees_slot`, `test_rejects_bad_arguments`).

Существующий набор, файлы не менялись:

```text
python3 -B -m unittest discover -s nox-control -p 'test_nox_self_heal.py' -q
Ran 6 tests in 0.012s
OK
```

CI этим прогоном не запускался. Workflow-файлы не редактировались; path-фильтры существующих workflow на каталог `staging/` не завязаны. Это наблюдение по файлам, а не результат GitHub Actions.

## Что не интегрировано / HOLD

- Слой не установлен в supervisor, systemd, OneHost или на хост. Импорт пакета ничего не включает.
- Хостовый `unified_nox_knowledge.sqlite3` не читается и не пишется. Схема `knowledge(content, teacher, content_sha)` адаптером не реализуется.
- `idle_consolidate.run` адаптеры не вызывают. В пакете по умолчанию dry-run; `--apply` из staging не вызывается; в supervisor job не регистрируется.
- Reflexion, ReAct, Tree-of-Thoughts, self-consistency, self-refine и CoT monitor остаются в пакете и покрыты его тестами. Адаптер диспетчера их не вызывает.
- `DecisionContext` не подключён к каналу поправок владельца.
- `Hysteresis` не управляет живым инференсом. `request_body` только кладёт словарь в запись admission.
- Checkpoint в адаптере — sqlite внутри staging `GraphMemory`, не хостовый checkpoint и не эталонный EXE.
- Планировщик не заменяет `nox-dispatcher.service` и не стартует потоки.
- Списки оптимизаций V100 / DeepSeek-V4.1, которые уже есть в `main` (`docs/NOX_Process_Optimizations_V100_V41_20261117.md` и короткое обновление), не относятся к этому слою и не редактировались.
- Нет заявки на runtime-установку, на merge в `main` и на связь с PR #162.

## Журнал

Строка: `docs/staging/JOURNAL_NOX_MIND_V41_20261117.csv`.

`commit_sha` в ней — `2d25a4b6c9a24b18533a2909a4d074dfbb948bf6`, коммит интеграции. SHA коммита документации в файл не записывается: он появляется только после записи этого файла.
