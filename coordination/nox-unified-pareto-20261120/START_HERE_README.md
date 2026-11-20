# NOX HELION · УНИВЕРСАЛЬНАЯ ЭСТАФЕТА / WEB WOW / САМООБУЧЕНИЕ

**Источник:** эталон V29.3 → WEB V13 → V14 R6.1 + FASTWOW; 20 ноября 2026; instructions_version 0.0.6.

## Главное

- 295 исходных уникальных TaskID (сохранены по исходной таблице Google Drive).
- 240 WOW-карточек, 89 предложений пользователя, 80 улучшений WEB, 14 инструментальных guardrail-карточек.
- 718 source/proposal записей с точными ID и источниками. Они не являются 718 отдельными, принятыми native jobs.
- Историческая очередь 1492 известна как агрегат, но полный идентифицированный snapshot всех 1492 здесь недоступен. Не генерировать фиктивные TaskID; использовать `tools/nox_self_improve/ingest_native_queue.py` после получения фактического JSON.
- Все original295 сохранены. Первая волна Парето = 59 из 295, отдельный быстрый список 20.
- Нет новой native acceptance; исходники/скрипты проверены локально, но это НЕ включение на Vast.

## Порядок работы для NOX

1. Открыть `NOX_MASTER_PARETO_3_QUEUES_20261120.md` и `NOX_TASK_MANIFEST.json`.
2. Работать **только** по оригинальным 295 TaskID через существующий native dispatcher; `WOW240/*`, `IDEA89/*`, `WEBWOW/*`, `SYS-SI/*` — связанные предложения/подзадачи, а не отдельные claims для основного реестра.
3. До native admission получить реальный установленный HEAD, текущий STOP, owner CAS lease, resource/heartbeat, доступные native worker slots. Из подтвержденного latest handoff physical cap = 3; UI может показывать 6 логических слотов, но не выдумывать PID.
4. Реализация одного среза → одна проверка → интеграция → checkpoint и один отчёт → независимый verifier → ACCEPTED. Ошибки и уроки фиксировать в SQLite-журнале.
5. Restart: только при фактическом сбое сервиса, owner-verified supervisor и отсутствующем STOP. Повторять попытку с ограниченным backoff до terminal result/HOLD, сохраняя idempotency key и исходный TaskID. Принудительное снятие STOP, удаление checkpoints и запуск параллельных writer запрещены.
6. Все предложенные пути — **candidate**, пока не найдены в exact HEAD. 240 новых Python-файлов из каталога — проектные, не подтверждённые как установленные.
7. Для WEB защищать исходную D02, проверять 10+10+10 и связывать все новые UI-действия с реальными API; новые vendor-библиотеки нельзя считать скачанными без SHA/license.

## Файлы

- `NOX_ALL_TASK_CARDS.json` — все 718 карточек со шагами, критериями и зависимостями.
- `NOX_ALL_TASK_CARDS.csv` и `NOX_UNIFIED_TASKS_3_QUEUES.xlsx` — просмотр/фильтрация.
- `NOX_QUEUE1_ORIGINAL295.json` — 295 корневых задач, отсортированы по эвристическому воздействию.
- `NOX_QUEUE1_PARETO59.json` и `NOX_TOP20_PARETO.json` — 20% и первые 20.
- `NOX_QUEUE2_WOW_PROPOSALS.json`, `NOX_QUEUE3_RESEARCH.json` — очереди расширений.
- `NOX_SELF_IMPROVEMENT_14_CARDS.json` — self-improvement/восстановление.
- `tools/nox_self_improve/` — журнал ошибок, поиск повторов, безопасный watchdog, сопоставление реального native queue snapshot, выбиралка следующего кандидата, gated auto-patch.
- `source_documents/` — исходные таблицы и списки для независимой сверки.

## Не подменять факты

Статусы `DONE` в старой общей очереди, CI SUCCESS и наличие скачанного ZIP **не означают** original295 ACCEPTED или живой WEB deployment. Для реальной приёмки нужен независимый native E2E и exact SHA.
