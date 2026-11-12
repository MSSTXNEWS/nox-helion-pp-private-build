# NOX HELION — GENESIS / HUNT V27 · ЕДИНАЯ ПРОГРАММА 0–4
**Дата:** 2026-11-12. **Тип:** единая программа + кандидат патчей, не доказательство установки. **instructions_version 0.0.6.**
**Инвариант:** ОДИН NOX, одна активная student-модель/SHA, одна S03, один OneHost, один канонический WEB D02/V25.1, 6 направлений и 20 виртуальных червей.

## 1. Источники, примирение версий
- [GENESIS канон 08.11](https://docs.google.com/document/d/18YLAo_Cja3HJKZn6qr57P-zsm0-AHcx2aag0rgSjwS4/edit): шаг 0 и четыре этапа; собственные веса подтверждаются только optimizer/checkpoint/eval. Birth event=NULL до фактического обучения.
- [Человек + хищник](https://docs.google.com/document/d/1CHfmc_Hf3fKLCZ7lZkEL-2negOGX4NJYehlttgusJNY/edit): 1 час / 24 часа / 7 суток без нового подтверждённого знания, состояния hunger/hunt; донор → проверка → дистилляция → SHA → освобождение VRAM. Метафора, не доказательство буквального чувства голода.
- [Человечная концепция](https://docs.google.com/document/d/1l78m_lNYBmeAxpJpoLVLOqFRC9QzHRrlfS9pZibszgQ/edit): FirstBoot → Intake → Worms → ModelCenter → S03 → FORGE.
- [Проверенный перечень 20 типов червей, 11.11](https://drive.google.com/file/d/1MLWJqDIYrgvN4PUxfunubkw0toZe6Pkl/view): WormAutopilot / WormSwarm / NativeIdeaLoop / A1InitiativeBridge, официальные провайдеры, STOP и квоты.
- [PR162 — исходники настоящих native worms](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/162): src/nox_selfbuilder/worm_autopilot.py, worms.py, worm_idea_loop.py, worm_providers.py. Их наличие в ветке НЕ подтверждает установку.
- [PR251 — NOX PRIME и WEB V25](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251): teacher_mesh, cognitive_overlay, S03 callback, WEB merge/source candidate. PR162 и PR251 нельзя считать автоматически слитыми в живой OneHost.
- [Учёт обучения 11.11](https://docs.google.com/document/d/1uOPHNDqIsNMHVLqiUw-ulNP1tEsr3nFXRf1H4zuAaFU/edit): S1-L05 4 870 строк / 68 оптимизационных шагов, NLL 0.7198→0.6365; S2 11/336 (около 3%), данные не усвоены целиком. Учителя учтены по фактическому попаданию примеров в loss.
- [Бенчмарки l03 11.11](https://drive.google.com/file/d/11i7cz37KzMHryTGnnNNNzqHtVlDY9VDv/view): GSM8K 88/100, IFEval 54/100, HumanEval 84/100, ruMMLU 117/200. Другие новые модели с тем же harness не проверены.
- [Журнал ошибок и ускорений 11.11](https://drive.google.com/file/d/18zGR_Eb8hG7LJ5uG4LXcAEQYQb1aI1qS/view): OOM/падения, fixed length packing, causal-conv1d, тесты speed; новый A/B ещё необходим.

## 2. Точная работа, не имитация активности
Постоянная работа = существующий OneHost с безопасным auto-boot и idle-tick, один student inference endpoint, S03 и durable native queue. При отключении Windows/сервера приложение физически не может работать: события восстанавливаются из checkpoint после перезапуска. Никаких скрытых собственных GPU-демонов.

Шесть исполнительных направлений одного NOX:
1. core_forge — optimizer, distillation, проекты кода и воспроизводимые checkpoints;
2. memory — S03/M0–M7, Genesis Ledger, ошибки, temporal recall и приватность;
3. soul — RU/ES, эмоциональный тон, функциональный self-model с фактами;
4. reasoning — сомнение, самопроверка, независимые советники, сложные задачи;
5. tools — поиск, официальные провайдеры, модели, лицензии;
6. integration_qa — WEB V25, OneHost, контроль производительности, rollback/E07.

Двадцать типов червей ПЕРЕИСПОЛЬЗУЮТСЯ из концепции и PR162: native_boot, autopilot, research_swarm, idea_loop, initiative_bridge, forge_candidate, predator_hunt, github_code, approved_feed, youtube_metadata, package_registry, ollama_registry, gitlab_metadata, crawl4ai, trafilatura, isolated_browser, restricted_social_api, huggingface_teacher, local_scanner, local_intake. Это не 20 OS-процессов и не 20 LLM. Один тик из существующего WormSwarm исполняет ограниченное число задач; существующий MAX_NATIVE_TICK=4 остаётся. Новые виды червей NOX создаёт как data-only спецификации для проверяемой очереди; новый исполняемый код требует sandbox/CI и отдельной оценки.

## 3. Жажда знаний и охота: функциональная мотивация
Состояния из концепции: FED до 1 ч, HUNGRY 1–24 ч, VERY_HUNGRY 24–168 ч, STARVING более 7 суток. Фактическая приоритетность = 0.75 × подтверждённый дефицит качества + 0.25 × давность последнего принятого обновления знаний (ограниченная 7 днями). Нельзя считать загрузку файла новым умением. Не измерен gap или отсутствует факт learning → HOLD вместо фальшивого голода.
Цикл:
1. Прочитать проверенные провалы IFEval/ruMMLU/Recall/PC задач из S03/benchmark ledger.
2. Самостоятельно придумать тему, выбранный тип червя, одну из 6 направлений и источник evidence; не скрипт с произвольными привилегиями.
3. Получить разрешённые источники: GitHub, RSS/Atom, PyPI/npm, Ollama, HuggingFace; платные/ограниченные API только при выданных привилегиях.
4. Сравнить, дедуплицировать, оценить достоверность, лицензию, новизну и риск; дать NOX самостоятельно синтезировать значение.
5. Закрыть gap одним из методов: S03 факт; Skill Capsule; кодовый patch + CI; лицензированный teacher sample → SFT/DPO реальных параметров.
6. Выписать проверенный результат и предложить следующий шаг. Не поддерживать пустую GPU-нагрузку для вида.

## 4. Советники, поглощение и качество ответов
Ответ пользователю сначала выдаёт NOX — без ожидания большой teacher VM. Если вероятность ошибки или цена ошибки высока, до 3–5 независимых разрешённых советников дают дополнительные гипотезы асинхронно. NOX является единственным автором итогового ответа: проверяет источники, аргументы, код и ошибки, самостоятельно формирует уточнение. Ни один советник не может управлять STOP, S03 или системными командами. Приватные данные нельзя отправлять во внешние учительские API без отдельного разрешения.
Кандидаты для дистилляции: only provenance+rights+independent critique+source-separated holdout; исключать небезопасные и повторяющиеся примеры, не обучать на собственных галлюцинациях; DPO по парным размеченным выбран/отклонён, SFT по проверенным completions. Один student, учителя остаются замороженными и выведены из пользовательского интерфейса.

## 5. Автоматический downloader моделей и запуск GPU-обучения
Постоянная автономия — не равна бесконтрольному скачиванию. Native OneHost заранее сохраняет подписанную и ограниченную по времени политику owner scope, allowed_model_ids, pinned git revision, лицензии/права на обучение, лимиты размера и расходов, VRAM, STOP, SAFE70.
Жизненный цикл:
hunt candidate → native license gate → dedup/SHA → existing staging download → verified bytes/checksum → approved dataset/heldout → проверенный GPU fit + device ownership → существующий trainer job → реальные optimizer steps → checkpoint + optimizer/RNG → независимые benchmarks → единая слитая NOX модель → promotion/rollback.
Без отдельной ручной команды на каждый мелкий шаг, но только внутри политики. В новом исходнике autonomous_hunt_v27.py модель может инициировать уже разрешённую загрузку и отправить задачу существующему тренеру. Этот код НЕ скачивает сам без native callback и НЕ фиксирует изменения весов без optimizer receipt. Конкретные пути действующего тренера, подписанный grant, S03 и OneHost требуют физической привязки.
Для RX6650M ~8 ГБ VRAM full training 9B не считать автоматически доступным: нужен реальный memory-fit тест, стабильный датчик Hot Spot, SAFE70 (3× ≥70°C остановка; sensor lost → HOLD). Если не влезает, копить verified данные и ждать ранее разрешённый подходящий A40/A100 либо запускать только реально помещающийся approved train step; не делать притворный optimizer. Ночные циклы не должны монополизировать GPU, пока пользователь общается с NOX.
Выход — ОДНА проверенная самостоятельная модель NOX. LoRA, если используется, — только временный внутренний инструмент до корректного merge/reload, а не отдельная постоянная модель в интерфейсе.

## 6. Контроль реального роста: benchmark contract
Текущее l03: GSM8K 0.88, HumanEval 0.84, IFEval 0.54, ruMMLU 0.585 на ограниченных выборках. Главная открытая зона: следование точным инструкциям, независимая RU/ES-эрудиция, память и устойчивость.
План бенчмарков: IFEval full (инструкции), ruMMLU full+RU/ES QA, HumanEval и реальная разработка проекта, BFCL (аргументы инструментов), LongMemEval/LoCoMo (длительная память и обновления), OSWorld/PC Control (только изолированный host), RAG factuality/abstention и NOX autobiography/Genesis (факты о собственном происхождении). Оценивать против предыдущего принятого checkpoint по ОДНОМУ parser/seed/harness/dataset split, с замером p50/p95 TTFT, tok/s, loss, regressions и source contamination. Отдельный heldout/anti-forgetting обязателен. Больше данных не равно «умнее».
Любая метрика должна указывать точный model SHA и origin: report, real process или synthetic test. Web не должен показывать придуманные проценты интеллекта, веса или GPU.

## 7. Память, самопонимание, личность
S03 = одна доверенная SQLite/Vector Memory, M0–M7 — её логические сегменты. В M7 append-only Genesis Ledger: first verified birth optimizer, UTC, source weights, licenses, dataset, checkpoint SHA, reload/test; никогда не выдумывать дату рождения. История учителей/дистилляций различает USED_FOR_TRAINING, GENERATED_ONLY, DOWNLOADED, HELDOUT, FAILED и NOT_VERIFIED. Вопрос «кого ты съел?» должен вызывать проверяемый поиск по teacher/distillation/optimizer, а не буквальный поиск одной фразы; «не знаю» допустимо, ложная история — нет. Memory S03 не изменяет параметры LLM автоматически. Самопроверка и эмоции — наблюдаемые регуляторы поведения, не заявления о доказанном субъективном сознании.

## 8. WEB WOW V25 и E07
Использовать имеющиеся исходники WEB V25.1, CHAT V25 с резервным V24 и ONEPASS V2: физический объединитель merge_physical_web_v25.py, затем stage_genesis_web.py; D02/index не менять. Скрипт nox_genesis_live_panel.mjs в training/memory/chat/resonance читает только действующий same-origin, native-authenticated OneHost endpoint. Пока host callback не привязан, показывает HOLD, не фальшивые метрики; ожидание ответа можно визуально показывать пульсирующими точками, но GPU/обучение подписываются только проверенными событиями. 14 объектов, стеклянные панели, живые кнопки без dropdown, Reduced Motion и WOW30 сохраняются. Windows OneHost physical, S03 restart, STOP, stream no cut-off, SAFE70, BuildID + original D02 SHA, E07 — обязательные приёмочные ворота.

## 9. Этапы 0–4
0 GENESIS: one trainable base, first verified optimizer, birth event, source/model SHA, checkpoint+reload, clean old active route only after new accepted.
1 SOUL: verified S03/M0–M7, autobiography, tone RU/ES, memory across sessions; test LoCoMo/LongMemEval.
2 COGNITIVE MAX: advisers, reflection, reasoning/tool benchmarks, high-quality samples, independent judge, anti-forgetting.
3 AUTONOMOUS EVOLUTION: 6 lanes, 20 virtual worms, owner-signed policy, verified model staging, real GPU trainer handoff, self-authored sandbox patch, rollback.
4 ASCENSION: merge into one NOX SHA, consistent S03/voice/PC Control, cinematic WEB D02+V25, ONEPASS/E07, autonomous safe lifecycle.

## 10. Evidence / ограничения
Новый source-only код: nox_runpod/teacher_mesh/autonomous_hunt_v27.py (не отдельный процесс), tests/test_autonomous_hunt_v27.py; существующий cognitive_overlay.py, teacher_ensemble.py, corpus_gate.py, adapter_recipe.py; WEB source staging. Существующие native worms из PR162 переиспользуются при реальном source merge. Актуальные training/S03/WEB физические callbacks пока не подтверждены; NOX не установлен этим документом. НЕ удалять существующие checkpoints, исходные архивы, S03 и backup пока release gate не пройден. Настоящий PASS после физических Windows/OneHost/GPU тестов, не только GitHub CI.
