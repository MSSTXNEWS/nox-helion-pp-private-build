# NOX V16 · REPORT GATE R1 · 111111111 · ONE RULE FOR EXECUTORS 1–7

**Authority:** NOX V16 sections 26–32, inherited V15 56 rules; main spec https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit. This is an additive coordinator contract, **NOT a finished EXE, not a background automation and not an authorization to delete/overwrite any original**.

## Unambiguous short trigger
- **ЕДИНОЕ ПРАВИЛО:** любая строка, состоящая только из символов `1`, означает ровно столько последовательных циклов, сколько в ней единиц. `1` = 1 цикл; `11` = 2; `111` = 3; `111111111` = 9; `1111111111` = 10. Никаких исключений для коротких команд и никаких альтернативных интерпретаций. Каждая единица запускает один цикл, в котором нужно попытаться выполнить 10 различных физических TaskID своего блока. HOLD-задачи не считаются DONE. Количество единиц не создаёт реальных автономных субагентов и не позволяет обещать фоновую работу.
- Явная текстовая команда владельца определяет содержание цикла; число единиц определяет **количество циклов**, если владелец не указал иного явного требования. Команды с буквами/пробелами — не этот сокращённый протокол.
- The "nine" cycle count is a request to work in the **current explicitly active session**. No claim that nine separate AI agents or scheduled jobs have been created. Do not promise unattended execution or future delivery without actual automation.

## Each launch/cycle has an obligatory five-stage proof chain
1. **PRESTART:** Read current V16 (latest authoritative sections including WOW 10+10+10 and all approved functions), fresh delta from master errors, E06 unified report, E06 self-improvement lessons, latest own receipt, Git HEAD/tree and current owner/SourceLock. Record the document revision/hash and the exact lesson ID **before code changes**. If master integrity cannot be proven, read it but use `MASTER_HOLD`; never rewrite its historical contents.
2. **LEARN:** Choose a specific prior error/lesson from a prior RunID, state how today's method differs, which redundant work it prevents and what measurable check will establish improvement. A new run with no changed method requires `NO_NEW_LESSON` justification and source delta, not invented "self-learning". No claim of training neural weights from reading a journal.
3. **EXECUTE:** Aim at ten genuine tasks in one uninterrupted cycle, with exact paths, owner, RunID, TaskID, verified pre/post SHA-256, patch SHA-256, receipt and focused tests. No intermediate user-facing status texts, report spam, cosmetic snapshots or repeated network lookups. **Actual code commits, atomic backups, rights checks and necessary safety tests are not optional.** On conflict: HOLD conflicting file, preserve both and perform another independent safe task.
4. **POSTSTART:** Exactly one result report for each actual cycle and exactly one concrete improvement/error→cause→change→regression lesson. Append to the executor's own report, **E06 central report** and **E06 lessons journal** using revision-guarded non-destructive writes; optional master delta append only with verified integrity, otherwise report `MASTER_HOLD`. E06 must accept cross-owner reports; for inaccessible tool/accounts mark `REPORT_HOLD` with exact reason, do not claim success.
5. **READBACK:** Read each written report and lesson to find the **same** RunID/TaskIDs/commit/receipt and verify expected content, separately check GitHub changed paths and observed CI conclusion. A completed GitHub Actions CI is an execution event, **not** automatically an executor RunID or an accepted report. A report without matching lesson or readback = `REPORT_GATE=HOLD`, cannot be counted as complete, even when source CI passes.

## Seven fixed process quality gates (legacy weight schedule; NOT product progress)
| Gate | Weight | Passing evidence |
|---|---:|---|
| G1 PRESTART verified | 15% | Current V16/master/E06/lessons revisions and own last receipt |
| G2 Ten true physical tasks | 20% | Ten distinct TaskID deltas or explicit independently grounded HOLD |
| G3 No-loss/SourceLock | 20% | Owner/pre/post/patch SHA and rollback, unique approved WOW/assets preserved |
| G4 Isolation/ownership | 10% | One owner/path, no cross-worker stale RunID, no fake agents |
| G5 Focused component checks | 20% | Actual test names+CI exact source sha and meaningful result |
| G6 Unified report/journal+readback | 10% | Own+E06 report and E06 lesson saved/readback at same RunID |
| G7 Measured improvement | 5% | Root cause, applied change, regression result and saved lesson |

These are **cycle-discipline gate weights 15/20/20/10/20/10/5**, not the **V16 product weighted readiness 20/25/20/25/10 for owners #1–#5**. Both have separate denominators. Do not use missing evidence to invent product percentages. A green source test != native EXE acceptance.

## Seven reporting rows and owner accountability
- 1: original D02 HOME/MENU/CORE, original approved art+Personas, WebView2/NSIS and WOW 10+10+10; no app functions sacrificed for visuals.
- 2: one local Ollama/SQLite/chat+RAG, attachments, RU↔ES/MAESTRO/SIP, STOP, native authorization.
- 3: original ModelCenter 15–20+ one-click pinned weights, queue/Pull/Import/STOP/retry, licenses and Python/GPU prerequisites; never fake downloaded models.
- 4: existing RAG+real Nvidia LoRA/QLoRA, evidence of licensed dataset, true loss/checkpoints, STOP/resume/eval/merge.
- 5: single events.v3, honest GPU/CPU sensors, news/weather/FX/BTC/Brent, reporting and progress.
- 6: ONLY owner of common MainWindow/host bridge/serial merge, all-owner SourceLock and final installer. Early diagnostic builds allowed; no "final EXE" before #1–#5 proven component ready.
- 7: independent same BuildID+EXE SHA acceptance; RAG/LLM/GPU/voice/calls and all agreed WOW checked on actual Windows runtime, not by source tests alone.

## Strict evidence/status output
For each executor and for overall: show `CODE_SOURCE`, `COMPONENT_CI`, `NATIVE_HOST_INTEGRATED`, `WINDOWS_ACCEPTED`, `REPORT_GATE`, `LEARN_GATE`, `MASTER_GATE`. Seven progress bars from frozen criterion ledgers only; `Н/Д` if denominator or approvals absent. Show `0 new accepted` only for *new* tasks that lack acceptance, never claim the historic app has zero functions. Error log updates and generic text reports count as **0 technical integration tasks**. All agreed cinematic WOW 1–200 and original D02, and 45 optional OSS candidates remain in scope without fake proof of EXE integration.

## Verified baseline from sampled audit 2026-10-28
Seven sampled GitHub Actions IDs E01 40603471612, E02 40612432034, E03 40613929611, E04 40614259216, E05 40602737082, E06 40614192835, E07 40613433967:
- Own report or E06 contained matching exact ID **4/7**.
- Central E06 lessons contained matching exact ID **2/7**.
- Historical master journal contained matching exact ID **0/7**.
**This is a sample of CI runs, not seven unique executor sessions**; absence of an ID is an evidence gap and does not prove no work was done. Never backfill missing evidence from a different RunID. Historical master integrity remains unverified and must not be destructively rewritten.


## VERBATIM LEGACY CANON — V13/V15 FIN ZAGR, ALL 56 CONSOLIDATED RULES (READ-ONLY REFERENCE)
The following exact historical source is retained to prevent rule loss. The historical file itself explicitly says its 56 points are a consolidated reconstruction, not a verified verbatim original 56-rule document. In any contradiction, the owner's explicit 2026-10-28 trigger clarification (every `1` is one cycle) and latest V16 safety/no-loss gates take priority; the original historical wording is deliberately NOT deleted or silently edited.

```text
# FIN ZAGR — NOX HELION EXPRESS INTEGRATOR · ЕДИНОЕ ТЗ V13
Область: один Windows EXE-установщик, НЕ WEB RELEASE/540.
Статус: канон разработки, не готовый EXE.

## Пять пакетов
P01 (20%): WPF/WebView2, оригинальные HOME/MENU/CORE, 8 MENU и 8 CoreID, 5 кнопок, DPI 100–200%, F11/Escape, киноэффекты, паспорта Persona.
P02 (25%): Ollama /api/tags /api/chat, streaming/STOP/TIMEOUT, модели, история, вложения, квоты, SQLite ACL, поддерживаемый официальный Codex login/status (подписка не равна API).
P03 (20%): 24+ моделей, Ollama Pull, каталог лицензий/размеров/VRAM, очередь/отмена/повтор, winget, Python/Ollama/Git, диагностика ПК, безопасный импорт, backup/rollback.
P04 (25%): RAG, embeddings, разрешённые датасеты, PEFT LoRA/QLoRA, обучение в фоне, ECO/BALANCED/INTENSIVE, GPU/VRAM/температура, checkpoints, validation, совместимый merge и STOP.
P05 (10%): датчики 8 CoreID, 5 Persona, CPU/GPU, прогресс моделей/RAG/LoRA, отчёты, 5+1 полос готовности, V7 циклы, Google Drive readback, независимая приёмка.
E06 интегрирует без веса; E07 независимо проверяет без веса.

## Оптимизация
Один WPF/WebView2 host и events.v3, адаптеры вместо дублей, готовые официальные WebView2, Ollama, winget, PEFT, Transformers, Accelerate, PyTorch, psutil, NVML, SQLite, Playwright. Все версии, лицензии и тесты уточнять по реестру V12. Быстрые вертикальные Windows smoke-сборки, инкрементальные тесты плюс обязательная сквозная QA. Не снижать WOW, функции и безопасность.

## 56 правил — консолидированная редакция
**Оговорка:** при поиске Google Drive не найден однозначный исходный документ с именно 56 пронумерованными правилами. Этот список составлен из подтверждённых требований и НЕ выдаётся за дословную копию исходника. После обнаружения оригинала нужна сверка.
01. Единый Windows EXE, не WEB/540
02. Не сокращать функции ради ускорения
03. P01–P05 веса 20/25/20/25/10
04. E06 интегратор без веса
05. E07 независимый QA без веса
06. Семь непересекающихся ролей
07. Десять последовательных циклов
08. Не имитировать параллельных агентов
09. Сначала читать FIN ZAGR
10. Читать новые строки общего журнала
11. Самоулучшение перед запуском
12. Использовать успешные решения прошлого
13. Устранять первопричины ошибок
14. Фиксировать Drive ID и SHA
15. Один владелец каждого файла
16. Не дублировать чужие задачи
17. Не копировать весь архив без нужды
18. Не повторять готовое
19. При блокере перейти к независимой задаче
20. Оригинальные HOME/MENU/CORE
21. Восемь MENU не равны восьми CoreID
22. Персонажи строго по паспортам
23. DESIGN LOCK и лицензии
24. Один WPF/WebView2 host
25. Без WinForms и Edge app-mode
26. Пять рабочих кнопок
27. F11/Escape, DPI и Reduced Motion
28. Только реальные датчики
29. Один контракт events.v3
30. Живой Ollama streaming/STOP
31. Различать TIMEOUT и STOP
32. История, вложения и SQLite ACL
33. Не подменять подпиской ChatGPT API
34. 24+ моделей
35. Проверять права и требования моделей
36. Очередь, отмена, повтор и прогресс
37. Установка с согласием и rollback
38. Проверка формата импортируемых весов
39. RAG отдельно от обучения весов
40. Права на датасет и holdout
41. Реальная LoRA/QLoRA
42. Checkpoints, eval, совместимый merge
43. GPU ECO/BALANCED/INTENSIVE
44. Без ложного лимита мощности GPU
45. Реестр интеграций с версиями и лицензиями
46. Готовые официальные библиотеки
47. Инкрементальные и сквозные тесты
48. Нативная Windows-приёмка
49. Разделять циклы и готовность
50. Пять цветных полос и общий прогресс
51. VERIFIED/HOLD/FAILED, delta, RunID
52. Не выдумывать проценты
53. Общий журнал ошибок и улучшений
54. Google Drive readback
55. REPORT_GATE BLOCKED без readback
56. RELEASE BLOCKED без независимого same-SHA QA

## 7×10
C1 журнал/самоулучшение; C2 источники/SHA; C3 критический путь; C4 P01/P02; C5 P03; C6 P04; C7 P05; C8 end-to-end; C9 исправления/регрессия; C10 E07 QA и журнал. Выполненные циклы подтверждать фактами, не имитировать 70 операций.

## Релиз
Исходный код и отчёты не равны EXE. Проверить права/графику, Windows build, кнопки/DPI, живой Ollama/STOP, загрузки, реальное обучение, безопасность/rollback, независимый same-SHA EXE. До этого RELEASE BLOCKED, готовность Н/Д.

## Источники
CANON V11: https://drive.google.com/file/d/1tErkSWxNiMzCveHCJsrKwfhZqwhUiJqp/view
R6 P04: https://drive.google.com/file/d/1HyoyDohe20lghlXIKvw4bwwBhkyAmMch/view
R6 P03: https://drive.google.com/file/d/1M2qEE_0NlKOtgmOFFVomn1m6vdF85aQL/view
Registry V12: https://drive.google.com/file/d/1nsdP_3tmMCVTZx2E6gKOjGXcaJU0yD4v/view
Growth: https://docs.google.com/document/d/1evk2XhCAT_zY97MmMunTCCHXViSlnTshf2EzfKYWR98/edit

## Очистка
Считать FIN ZAGR единственным активным ТЗ. Устаревшие документы не использовать для назначения задач. Физически удалять только после file-ID/SHA инвентаризации, проверки замещения и сохранения уникальных исходников/журналов.


## V15 — ИСПРАВЛЕНИЕ ФОРМУЛЫ ПРОГРЕССА БЕЗ СМЕНЫ ВЕРСИИ
Вести отдельный TASK PROGRESS по фиксированному реестру задач. Каждая задача имеет TaskID, пакет, вес внутри пакета, evidence_path, статус и критерий завершения. Пакетный процент = 100 × сумма весов задач с доказанным выполнением / сумма весов всех задач пакета. Общий TASK PROGRESS = 0.20×P01 + 0.25×P02 + 0.20×P03 + 0.25×P04 + 0.10×P05. Пересчёт знаменателя допускается только при явно зафиксированном изменении объёма, без удаления обязательных функций. SOURCE_PRESENT не равен VERIFIED функциональности. Параллельно показывать SOURCE TASK PROGRESS и ACCEPTED RELEASE PROGRESS, последний Н/Д без актов. Нельзя ставить 100% по числу циклов, тестов или файлов без привязки к TaskID. Для текущего источника 50 задач по 10 на пакет, 27 подтверждений наличия артефактов, взвешенный показатель 52.5% SOURCE TASK COVERAGE; это не готовность EXE. Состояния и список задач см. FIN_ZAGR_V15_TASK_LEDGER.csv. Каждый запуск сверять новые фактические изменения и обновлять CSV/отчёт, сохранять в общий журнал Drive и проверять readback. Действующая версия остаётся V15.
```
