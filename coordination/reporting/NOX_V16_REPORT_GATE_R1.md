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
