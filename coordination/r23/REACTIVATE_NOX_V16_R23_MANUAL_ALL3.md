# REACTIVATE_NOX_V16_R23_MANUAL_ALL3 · 2026-10-29 · EXECUTE NOW
ПРИОРИТЕТ P0: ФИЗИЧЕСКИЕ DONE, НЕ ОТЧЁТЫ. Отправляется отдельно в СУЩЕСТВУЮЩИЕ ручные чаты №1, №2, №3; каждый действует по СВОЕМУ актуальному полному ролевому промпту. Не создавать четвёртую роль, новый проект, TaskID, автономную ветку продукта. Не терять предыдущие DONE.

1. СНАЧАЛА РЕАЛЬНО ОТКРОЙ И ПРОЧИТАЙ через Google Drive/GitHub:
- полный свой действующий ролевой промпт;
- актуальный канон V16: https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit (все 56 правил §33, §§54–56/R29, R18–R23);
- ПОЛНЫЙ текущий компактный общий ERROR REGISTER: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/coordination/v16-shared-error-ledger-20261029-r01/coordination/ops/NOX_V16_ACTIVE_ERROR_REGISTER.json ;
- Master/E06/Lessons/C34 и только новые owner receipts после checkpoint;
- текущий PR162 HEAD/tree и изолированные owner branches/commits: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/162 ;
- полную R23 recovery-policy: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/coordination/nox-v16-r18-controls-20261029/coordination/r23/R23_RECOVERY_ACCEPTANCE.md .
Запиши PRESTART_READ_PROOF: RunID, canon revision, register blob, текущий HEAD/tree и нужные ERROR_ID. Если реально не прочитал — READ_BLOCKED, никакого ложного PASS.

2. ВОССТАНОВЛЕНИЕ БЕЗ ПОВТОРНОЙ РАБОТЫ:
- Ранее интегрированный T08 QA gate (head/source_head конфликт) уже в PR162 commit 5a335a3db05e3cf31685fb708065ba96adf50449. ПРОВЕРЬ живой HEAD; НЕ пересоздавай и НЕ мержи его повторно.
- T06/№1: последняя автоматизация FAILED из-за отказа Git CAS, не из-за отсутствия P01 патча. Готовый isolated P01 path-safety патч: commit 7bf335dd8f0c90223c93958a25be41daf02c612e, source PRE 12bc43ca210022fba418ca7345876e598edc33e3 → POST bd61bc61f66314d5f4840ef6ad516e72f6314995, test PRE c36e6ed5fb0659c07539d7482169cfe363b67336 → POST bea76d1ef9080ae7eea78178a23f8aa0701b1e04. ONLY if current live PRE matches, test and authorized CAS/readback. При блокировке инструмента: не повторять запрещённую запись, сохранить точный checkpoint и делать другой READY TaskID.
- №3 P04: model_snapshot уже подготовлен в PR221 HEAD 74fca01fd1dab883f87ffdf07a9f1dd47dde0300; source Packages/P04/model_snapshot_probe.py blob 9a837f86c40d71124f47f340229ca2f8814bd99e, test tests/P04/test_model_snapshot_probe.py blob b0244acdfbb4dc173fc4e48d1bcae40d89ed20ec; isolated RED/GREEN ещё НЕ full unittest/QA. Проверить полный Python unittest независимо от отсутствия .NET SDK для P05; передать точный PRE/POST для T06.
- T02 Master CAS/readback PASS, но E06 FAILED_PRECONDITION, Lessons и общий Git register пока не синхронизированы. Только T02 обновляет их после свежего чтения ревизий/журнала и CAS; при ошибке сохраняет доказательства и не объявляет ложное DONE.
- Host50: 13 historical SOURCE HOLD ≠ 11 current SOURCE UNBOUND ≠ 14 NATIVE PENDING; сверять route IDs и тип доказательства, не подгонять число.

3. СТРОГО СОХРАНИ РОЛИ:
№1/T06 — единственный source writer PR162; P01–P03 и owner-safe принятие готовых P04/P05, 13/11/14 Host50 без смешения стадий, Voice/IPC/STOP/ACL/consent, один HEAD, пакетный CAS, Git readback, then T08.
№3 — готовит source P04/P05, RAG/GPU/QLoRA, events/SPACE на существующих владельческих путях; без второго backend/host/db/queue/event bus, без PR162 write.
№2/T08 — независимая исходная QA на живом точном HEAD; реальные функциональные + обязательные security tests, per-TaskID disposition с PASS/FAIL и owner receipt. Не объявлять native/Windows PASS по mock/static source. Не править production-код.
T02 — единственный writer Error/Master/E06/Lessons. T09 freeze после T06+T08; T10 SOURCE_READY после freeze; T11 GitLab Free GET-only authenticated HEAD/permissions (без токенов в журнале). T12–T15, EXE/NSIS/CI/E07/релиз запрещены до CODE_COMPLETE/SOURCE_READY и отдельного разрешения.

4. УСКОРЕНИЕ: выбирать один или пакет совместимых существующих READY TaskID из пяти P01–P05, не создавать новых. Переиспользовать готовый код/проверенные официальные библиотеки с лицензией и SHA; не повторять старые DONE и неизменённые тесты. Получить реальное PRE→POST, выполнить нужные targeted + STOP/ACL/consent/privacy/NO-LOSS регрессии, атомарно сохранить Git с readback, передать следующему owner и T02. Если изменение невозможно по независимым условиям — сделать другой безопасный TaskID, не заменять работу объяснением HOLD.

5. КОНТРОЛЬ: A READ, B PHYSICAL, C OWN RECEIPT+T02 HANDOFF, D RELEVANT LESSONS+RECURRENCE. Один короткий ОТЧ-1: RunID, факт start/end, задача, стадия SOURCE_PREPARED→SOURCE_VERIFIED→INTEGRATED→QA_ACCEPTED, новый DONE и остаток, PRE/POST SHA, тесты, Git readback, ERROR_ID, next checkpoint. Продукт P01–P05 веса 20/25/20/25/10; общий процент N/D до полного frozen TaskID ledger, никакого ложного 100%.
НИЧЕГО НЕ ПОТЕРЯТЬ: V15/V16, все 56 правил §33, 729 оригинальных файлов/3 ZIP, D02/WOW200, 8 CoreID, 5 Persona, PACK01/02, STOP, ACL, native consent, NO-LOSS, безопасность данных и все исторические DONE.
НАЧНИ СЕЙЧАС: РЕАЛЬНЫЕ ИСТОЧНИКИ → ФИЗИЧЕСКИЙ TaskID → ТЕСТ → GIT READBACK → ПЕРЕДАЧА → СЛЕДУЮЩИЙ ДОСТУПНЫЙ БЛОК. Нельзя объявлять DONE без независимой приёмки; при объективных ограничениях точный checkpoint.
