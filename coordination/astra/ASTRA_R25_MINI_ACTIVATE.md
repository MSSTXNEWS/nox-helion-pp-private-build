# ASTRA HIGH / CODEX — NOX V16 MINI ACTIVATION R25

Работай с существующей приватной веткой `astra/v16-code-complete-source-only-20261029` репозитория `MSSTXNEWS/nox-helion-pp-private-build`. Не меняй PR162/main. Проверь актуальный HEAD и GitHub/Drive доступ. Перед записью кода убедись, что 15 прежних автоматизаций и ручные разработчики действительно остановлены.

**ПРИОРИТЕТ R26 · ОСНОВНАЯ СБОРКА В GITLAB FREE — ЭТО УЖЕ ВЫБРАНО ВЛАДЕЛЬЦЕМ 28.10.2026.** GitHub здесь — репозиторий исходников и ветка Astra, GitLab Free — ОТДЕЛЬНЫЙ Windows CI: приватный `https://gitlab.com/s-grouptwet/nox-helion-pp-private-build`, историческая ветка `migration/nox-v16-gitlab-free-20261028-r01`, успешно стартовавший (но УПАВШИЙ на P02) Pipeline `#3000422727` / Windows Job `#17549234693`, runner `saas-windows-medium-amd64`. Полный проверенный маршрут и реальные файлы: `coordination/astra/ASTRA_R26_GITLAB_FREE_PRIMARY_BUILD_HANDOFF.md`. Ветка GitLab-миграции НЕ является автоматически синхронизированной с Astra, история исходников разошлась; живой HEAD GitLab без аутентифицированного доступа не подтверждён. **Astra не запускает GitLab CI и не переносит сборку обратно в GitHub/Azure/Release1**: только SOURCE_CODE_COMPLETE и SHA/TaskID/SourceLock handoff; позднее независимый интегратор сверит текущие GitLab и GitHub SHA, без force/reimport, подготовит CI, затем одна Windows-сборка по разрешению владельца.

ОБЯЗАТЕЛЬНО ПРОЧТИ ПОЛНОСТЬЮ:
- `coordination/astra/ASTRA_R23_SUPERVISOR_10X10_START_NOW.md`
- `coordination/astra/ASTRA_V16_R23_10_AGENTS_X_10_APPROACHES.json`
- `coordination/astra/ASTRA_V16_R24_ALL_56_V15_RULES_EXACT_SECTION33.md` — 56/56 правил V15
- `coordination/astra/ASTRA_R24_MANDATORY_JOURNAL_RW_EVERY_LAUNCH.md`
- `coordination/astra/ASTRA_V16_SOLO_CODE_COMPLETE_HANDOFF_20261029.md`
- `coordination/astra/ASTRA_V16_R23_FROZEN_968_GIT_BLOBS_20261029.json`

Проверь наличие инструмента реальных субагентов. Если доступен — запусти 10 А01–А10 с реальными ID, независимыми owner-путями, по 10 технических подходов на каждого; учитывай лимит фактической параллельности. Если недоступен — объяви SUBAGENT_SPAWN_UNAVAILABLE и исполняй 10 очередей последовательно, не имитируя агентов.

ПЕРЕД КАЖДЫМ ЗАПУСКОМ: 56 правил; дельта V16 master ошибок, исторический C34, последний E06 отчёт и урок самоулучшения (точные Google Docs URL в R24 инструкции). ПОСЛЕ КАЖДОГО ЗАПУСКА: append RunID и ошибки в master, E06 run report и реальный урок в self-improvement; Google Docs revision/CAS + readback. Неуспех записи = DRIVE_WRITE_HOLD с GitHub fallback, без поддельного PASS.

Каждый реальный подход: исправь код → протестируй конкретную функцию → коммит/SHA → урок → следующая незавершённая TaskID. Не переписывай готовые донорские исправления R21/R22 и PR204/208/209/210/211. Сохрани все V15/V16, 968 Git-файлов, исходные три части/729 файлов, D02/8 CoreID/5 Persona/WOW200, PACK01/02 50+50, voice RU↔ES, Ollama, RAG/GPU/SPACE, безопасность и утверждённую графику. Интернет-библиотеки только с проверкой лицензий и совместимости.

КАЖДЫЙ РЕАЛЬНЫЙ ЗАПУСК: десять полос A01–A10 по выполненным подходам (НЕ готовность продукта), отдельная TaskID-готовность P01–P05 20/25/20/25/10, неизвестный знаменатель => Н/Д.

НИКАКИХ EXE/NSIS, Windows release CI, ранней межпакетной финальной интеграции, чужих merge или удаления прежних DONE. Цель: доказанный CODE_COMPLETE_CANDIDATE исходников для отдельного будущего интегратора. Начинай реальное программирование, не новый план.
