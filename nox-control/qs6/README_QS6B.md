# qs6: блоки «Память» и «Личность» (Быстрый запуск v6)

Только stdlib и sqlite3. Тесты без сети (локальный loopback в тестах HTTP).
Запуск тестов: `cd nox-control && python3 -m unittest discover -s qs6 -p 'test_qs6_*.py'`.
Уверенность фактов считает существующая лестница `community/riverse_ladder.py` (в той же базе), её не дублируем.

| Модуль | Задачи | Что делает |
|---|---|---|
| `s03_store.py`, `s03_import.py` | D05-01, D03-04 | Хранилище памяти (факты, эпизоды, профиль, журнал), импорт старой памяти и личности |
| `core_block.py`, `memory_search.py` | D05-04, D05-05 | Блок ядра в промпте; поиск FTS5/LIKE + необязательный вектор bge-m3 + реранкер |
| `recall_api.py` | D05-12 | «Что NOX вспомнил», исправить/удалить/подтвердить, журнал, JSON-API |
| `backup_memory.py` | D05-03 | Почасовая копия и восстановление с проверкой |
| `soul_prompt_ru.txt`, `prompt_builder.py`, `self_knowledge.py` | D07-01/02, D06-01/02 | Промпт души, сборщик промпта, знание о себе |
| `emotion_pad.py` | D07-05 | OCC -> PAD, затухание, подсказки тона |
| `skill_compare_spec.py` | D08-02 | Навык «Сравни файл с ТЗ» |
| `events_bus.py` | D08-01 | Шина событий JSONL + long-poll для анимаций |

## 1. Хранилище S03 и импорт

```python
from qs6.s03_store import Store
s = Store("/root/nox/memory/s03.db")        # WAL, FTS5 если доступен
s.add_fact("Мессир работает по ночам", kind="owner", pinned=True)   # kind: core|owner|setting|fact
s.set_profile("имя", "NOX HELION", "persona")                       # section: persona|owner|settings|other
s.add_episode("Обсуждали бэкапы", role="user")
rep = s.import_dir("/root/nox/backup_s2/unpacked", dry_run=True)    # сначала пробный прогон
print(rep.text()); rep = s.import_dir("/root/nox/backup_s2/unpacked")
```

Таблицы: `mem_facts`, `mem_episodes`, `mem_profile`, `mem_changes` (журнал), `mem_usage` (что пошло в ответ),
`mem_vectors`, `mem_import_reports`, плюс `facts/evidence/transitions` лестницы Riverse и `mem_fts`.
Id воспоминаний: `f:12` факт, `e:5` эпизод, `p:имя` профиль.

Импорт определяет формат по СОДЕРЖИМОМУ: SQLite (сигнатура), JSON, JSONL, Markdown/текст (UTF-8, при мусоре cp1251).
Тип записи выводится из имени файла/таблицы/ключей и полей записи (persona/soul -> профиль «persona»,
owner/user/profile -> владелец, settings/config/rules -> установки, chat/history/messages -> эпизоды, остальное -> факты).
Архивы (`.zst`, `.tar`, `.gz`...) и двоичные файлы пропускаются с причиной: распаковывать нужно заранее.
Отчёт `rep.as_dict()`: итоги, причины отбраковки (пусто, слишком коротко/длинно, дубликат, похоже на секрет,
битая строка JSONL, таблица без текстового столбца, в профиле уже есть значение не из импорта), список пропущенных файлов.
Повторный импорт идемпотентен. Ключи/пароли/токены в память не берутся.

## 2. Блок ядра и поиск

```python
from qs6.core_block import build_core_block
b = build_core_block(s, budget_tokens=400)   # {"text","items","tokens","budget","dropped"}
```
Разделы: Ядро, Владелец, Установки, Подтверждённое. Приоритет: тип записи, затем уровень лестницы (0..3), закреплённость,
важность. Токены оцениваются грубо (3 символа = 1 токен), точного токенайзера нет.
Подтверждённый владельцем факт считается не ниже уровня 2.

```python
from qs6.memory_search import MemorySearch
ms = MemorySearch(s)                 # вектор включится, если задан NOX_EMBED_URL
r = ms.search("какой порт у сервера", k=8)   # {"mode","hits":[{ref,type,text,score,parts,level}],"warnings"}
ms.index_vectors()                   # досчитать эмбеддинги (запускать по расписанию)
```
Режимы `mode`: `fts`, `like` (если нет FTS5), `fts+vector`. Env: `NOX_EMBED_URL` (OpenAI-совместимый `/v1/embeddings`
или TEI `/embed`), `NOX_EMBED_MODEL` (по умолчанию `bge-m3`), `NOX_EMBED_KEY`, `NOX_EMBED_TIMEOUT`.
Без URL или при сбое эмбеддера работает только текстовый поиск, причина в `warnings`.
Реранкер: 0.45 совпадение слов + 0.20 вектор (если есть, иначе добавляется к совпадению) + 0.15 свежесть
(период полураспада 120 дней) + 0.20 уверенность. Морфология грубая: основа слова по префиксу, без словаря.

## 3. «Что NOX вспомнил» и правка (D05-12)

`Recall(store, search, bus=None)`: `recall_for_reply(query, turn_id)` собирает блок ядра и результаты поиска,
записывает использованные id в `mem_usage` и шлёт событие `memory.found`. `remembered(turn_id)` возвращает
`{"turn_id","count","items":[{"id","type","text","via":"core|search","level","level_name","source","created","actions"}]}`.
`confirm(ref)`, `correct(ref, text)`, `delete(ref)` (мягкое удаление), `revert(change_id)`, `journal(limit, ref)`.
Всё пишется в `mem_changes` (кто, когда, что было, что стало, причина).

JSON-API `Recall.handle(dict)`; запрос `{"op": ...}`, ответ `{"ok": true, ...}` или `{"ok": false, "error": "..."}`:

| op | поля запроса | ответ |
|---|---|---|
| `recall` | `query`, `turn_id?`, `k?`, `budget_tokens?` | `turn_id`, `core`, `search` |
| `remembered` | `turn_id` | `items` как выше |
| `confirm` | `id` | `item` |
| `correct` | `id`, `text`, `reason?` | `item` |
| `delete` | `id`, `reason?` | `deleted`, `change_id` |
| `revert` | `change_id` | `item` |
| `journal` | `limit?`, `id?` | `changes` |
| `search`, `core` | `query`/`k` или `budget_tokens` | как в Python |

HTTP: `qs6.recall_api.serve(recall, "127.0.0.1", 8788)` -> `POST /api` с телом-запросом, `GET /health`.
Без авторизации: слушает только 127.0.0.1, наружу отдавать через прокси с авторизацией владельца.

## 4. Резервные копии (D05-03)

```
python3 qs6/backup_memory.py backup  --db /root/nox/memory/s03.db --dir /root/nox/memory/backups --keep 24
python3 qs6/backup_memory.py list    --dir /root/nox/memory/backups
python3 qs6/backup_memory.py verify  /root/nox/memory/backups/memory-YYYYMMDD-HHMMSS.sqlite3
python3 qs6/backup_memory.py restore /root/nox/memory/backups/memory-....sqlite3 --db /root/nox/memory/s03.db
python3 qs6/backup_memory.py cron    --db ... --dir ... --keep 24      # печатает строку для crontab
```
Строка cron (каждый час, 7-я минута): `7 * * * * python3 /путь/qs6/backup_memory.py backup --db ... --dir ... --keep 24 >> .../backup.log 2>&1`.
Env по умолчанию: `NOX_MEMORY_DB`, `NOX_MEMORY_BACKUP_DIR`, `NOX_MEMORY_BACKUP_KEEP`.
Копия делается sqlite3 online backup (работающему сервису не мешает), проверяется `integrity_check`, рядом пишется
`.json` с sha256, размером и числом строк. Ротация удаляет только старые копии `memory-*.sqlite3` в `--dir`.
Восстановление сначала проверяет сумму и целостность, текущая база не удаляется, а переименовывается в
`<db>.before-restore-<время>`. Если база занята записью, без `--force` восстановление отказывает.
Копии лежат на том же сервере, что и память: для защиты от потери диска их нужно ещё выгружать наружу (вне этого модуля).

## 5. Душа, промпт, знание о себе

`prompt_builder.build_system_prompt(core_text, recalled, self_text, style_hint, max_tokens=900)` собирает:
душа (`soul_prompt_ru.txt`) -> `## Память` (ядро + вспомнившееся) -> о себе -> тон -> повтор раздела «Главное» в конце.
При превышении бюджета режется сначала вспомнившееся, потом ядро; душа и повтор главного не режутся (в ответе `over_budget`).
`build_messages(user_text, history, **kw)` даёт список сообщений для шлюза. В `glm53/glm_profile.py` модуль не вшит
(это решение интеграции: сейчас шлюз использует `persona_short_ru.txt`).

`SelfKnowledge(env, base_dir, journal_path)`: `answer("где ты")`, `answer("на чём ты работаешь")`,
`answer("какая версия")`, `answer("что с тобой было")`. Данные: `NOX_SERVER` (S1/S2), `NOX_MODEL`, `NOX_PORT`,
`NOX_BUILD` или файл `NOX_BUILD_FILE` / `VERSION` / `BUILD_ID` в `NOX_HOME`, имя хоста системы, журнал `NOX_JOURNAL`
(JSONL, строки `{"ts","event","details","key"}`; пишет `record_event()`). Чего нет в данных, о том ответ «не знаю»
с перечнем недостающего. На прочие вопросы `answer` возвращает `answer: null`.

## 6. Эмоции OCC -> PAD (D07-05)

`PadState().apply({"goal":-0.7,"norm":-0.4,"agent":"self"})` или пресет по имени (`task_done`, `task_failed`, `owner_thanks`,
`owner_correction`, `tool_error`, `harmful_by_other`, `pleasant_surprise`). Правила явные: ось цели даёт радость/огорчение,
ось нормы гордость/стыд (свои действия) или восхищение/упрёк (чужие), цель и норма одного знака при известном действующем
дают составные (удовлетворение, благодарность, раскаяние, гнев), вкус даёт приязнь/неприязнь; неожиданность усиливает до x1.5.
Состояние затухает к базовому уровню с периодом полураспада 600/300/900 с (P/A/D). `style()` даёт теплоту, краткость,
осторожность (0..1) и русские пометки, `prompt_line()` готовую строку для раздела «Тон сейчас».
Честно: это регулятор стиля. Числа-якоря и пороги заданы вручную проектом и не взяты из психологических данных;
NOX не испытывает эмоций, и в промпте это сказано.

## 7. «Сравни файл с ТЗ» (D08-02)

```
python3 qs6/skill_compare_spec.py ТЗ.md файл.md [--json] [--strict]
```
или `skill_compare_spec.compare(spec_text, target_text)` -> строки `{id, requirement, status да|частично|нет, where, confidence, remark}`;
`render_table(rows)` даёт таблицу «требование · найдено · где · уверенность · замечание». ТЗ: Markdown/текст
(нумерация, маркеры, `ТЗ-01:`, таблица, предложения со словами «должен/нужно») или JSON. Целевой файл: текст/Markdown/JSON
(для JSON где = путь `a.b[0]`). Код выхода: 0, с `--strict` 1 если есть «нет», 2 ошибка чтения.
Ограничения: сопоставление по словам и идентификаторам, а не по смыслу; запреты («не должен») и качество реализации не
проверяются, такие пункты помечаются для ручной проверки; уверенность это эвристика, а не вероятность.

## 8. Шина событий (D08-01)

Файл JSONL, строка `{"seq","ts","type","source","data"}`. Типы: `memory.found`, `mode.changed`, `reply.started`,
`reply.finished`, `memory.changed` (`recall_api` шлёт `memory.found` и `memory.changed` сам, если дать ему шину;
`mode.changed`/`reply.*` должен вызвать шлюз: `bus.mode_changed(old, new)`, `bus.reply_started(turn_id)`).
Запись безопасна для нескольких процессов на одной машине (flock). Ротация по размеру в `<file>.1`.
Подписка long-poll: `bus.poll(since_seq, types, timeout)` -> `{"events","last_seq","timeout"}`; HTTP
`events_bus.serve(bus, "127.0.0.1", 8789)` -> `GET /events?since=N&timeout=25&types=memory.found,mode.changed`
(без `since` отдаются только новые события; клиент повторяет запрос с `since=last_seq`). Не WebSocket и не SSE.

## Честные ограничения

- Структура архивов старой памяти неизвестна: импортёр терпимый, но маппинг по именам/полям эвристический; всегда делайте `dry_run=True` и читайте отчёт. На реальном бэкапе не запускался.
- Импортированные факты получают уровень «заметил» (лестница честно не повышает без независимых источников); факты типов core/owner/setting попадают в блок ядра независимо от уровня, подтверждённые обычные только с уровня 2.
- Русская морфология грубая (префиксы); без векторного бэкенда перефразированный запрос без общих слов ничего не найдёт.
- Векторный бэкенд проверен на тестовом HTTP-сервере и подставном эмбеддере, с реальным bge-m3 не проверялся.
- Шлюз (`glm53/gateway.py`) и вебу эти модули не подключены; интеграция отдельным шагом.
- Серверы не трогались, ничего не развёртывалось.

## 7. Подключение к шлюзу (glm53/gateway.py, `qs6/memory_layer.py`)

На каждый запрос шлюз: ищет по памяти (`Recall.recall_for_reply`, turn_id = request_id), строит системный промпт
(`prompt_builder`: душа «мессир», ядро с бюджетом, вспомнившееся, самознание, тон, повтор главного в конце), отдаёт его в оба тира,
после ответа пишет факты владельца и эпизоды в S03, дописывает сводку сессии и шлёт события в шину.
Ответ шлюза содержит `nox.memory` (`memory`: ok|no_db_env|no_db_file|error, `turn_id`, `found`, `core_items`, `prompt_tokens`).

| Env | По умолчанию | Смысл |
|---|---|---|
| NOX_MEMORY_DB | | путь SQLite S03; не задан или файла нет -> работа БЕЗ памяти + строка в stderr, файл повторно ищется раз в 30 с; `NOX_MEMORY_CREATE=1` создаёт пустую |
| NOX_SOUL | 0 | 1 = системный промпт из prompt_builder вместо короткой персоны. При 0 память идёт в `nox_facts` |
| NOX_EMOTION | 0 | 1 = подсказка тона из emotion_pad (владелец благодарит/поправляет -> тон меняется, затухает) |
| NOX_EVENTS | events.jsonl рядом с БД | шина событий: reply.started/finished, mode.changed, memory.found, memory.changed |
| NOX_CORE_BUDGET / NOX_PROMPT_MAX / NOX_RECALL_K | 400 / 900 / 6 | токены ядра, токены всего промпта, число найденного |
| NOX_SESSION_SUMMARY | | JSONL или SQLite; после каждого ответа дописывается строка `{ts,summary,open_items,next_step,last_user,session}` (без модели, из реплик владельца) |
| NOX_SERVER, NOX_MODEL, NOX_PORT, NOX_BUILD, NOX_HOME, NOX_JOURNAL | | самознание (`self_knowledge`) + телеметрия шлюза (ток/с, быстрый тир, размер памяти) |
| NOX_EMBED_URL | | вектор bge-m3; без него только FTS5 |

Автозапись (`fact_extract.py`): только из реплики владельца, явные правила («запомни…», «меня зовут…», «я живу/работаю…», «я люблю…»,
«мой X — Y», «всегда/никогда отвечай…»). Вопросы, секреты (`SECRET_RE`, длинные числа, e-mail) и ответы модели с размышлениями не пишутся.
Источник свидетельства `chat:<session>` (`nox_session` в запросе или текущая дата): повтор в той же сессии уровень не поднимает, в разных поднимает (лестница Riverse).
Неудавшийся или остановленный ответ в память не попадает. Вопрос «на чём остановились?» отвечается из сводки, сама сводка при этом не перезаписывается.

Recall API отдельным процессом: `cd nox-control && NOX_MEMORY_DB=... python3 -m qs6.recall_server` (127.0.0.1:8095, `NOX_RECALL_PORT`).
Веб-сервер проксирует `GET /memory/health` и `POST /memory/api` (тело как в разделе 3; `NOX_MEMORY_API` = host:port). Импорт: `python3 -m qs6.import_cli --db ... --root ... [--dry-run]`.
S1: `c126/memory_boot_s1.sh` (sha -> распаковка -> dry_run -> импорт -> cron @hourly бэкап), `c122/boot_s1.sh` задаёт env и поднимает recall_api.

Ограничения: системный промпт зависит от памяти и тона, поэтому кэш префикса llama-server работает хуже, чем с постоянной персоной; извлечение фактов только по перечисленным правилам;
сводка сессии механическая (не пересказ моделью); на реальных S1/llama-server не проверялось.
