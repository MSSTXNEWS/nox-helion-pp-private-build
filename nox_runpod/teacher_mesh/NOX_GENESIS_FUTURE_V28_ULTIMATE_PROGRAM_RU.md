# ⚡ NOX HELION — FUTURE V28 · ЕДИНАЯ ПРОГРАММА 0–4 + WOW150 + 24 SKILL TEMPLATES

**Дата:** 12 ноября 2026. **Тип:** подробный консолидированный план и реально созданные source-патчи, а не установленная версия. **instructions_version:** 0.0.6.

## A. Единый технический канон
Один пользовательский NOX, единственный активный student-model SHA, одна S03 (M0–M7 — сегменты), один OneHost, один WEB WOW D02 V25.1. Шесть направлений работы и двадцать виртуальных специализаций червей переиспользуют существующий native idle-tick и очередь. Это НЕ шесть языковых моделей и НЕ двадцать постоянно занятых OS-процессов. Всё обучение весов проходит только через настоящий GPU-тренер с лицензированными данными, STOP, SAFE70, checkpoint и независимой приёмкой. Без новых backend или баз.

## B. Сохранены 100 старых + созданы 50 новых WOW-идей
[Исходные WOW 50 — Когнитивные](https://docs.google.com/document/d/1a0ibHaX1dI7YLeBNkV_HG09qprOLYWV9QlhkJ1kWtNc/edit), [50 улучшений архитектуры](https://docs.google.com/document/d/1domnHE4RQ_O_as3QaICh51988vg0TT4DBMlcO-3KFwo/edit) полностью сопоставлены с нашими фактическими критериями. Их 100 элементов — реестр NOX_WOW50_V28_EVAL_AND_ARCHITECTURE.json. Дополнительно 50 моих отдельных предложений — NOX_FUTURE_OWN_WOW50_V28.json. По каждому указаны назначение, конкретная метрика и статус разработки; идея не становится работающей функцией без теста.

Архитектурные вещи MoE, MLA, Mamba и Engram нельзя просто переключить на существующей Qwen3.5-9B. Дистилляция обычно меняет значения весов, но не обязательно увеличивает число параметров. «Голод знаний», «сон» и рефлексия — функциональные механизмы управления задачами и памятью, не доказательство субъективного сознания.

## C. Мои 12 основных модулей будущего NOX

1. **Neural Matchmaker.** Подбирает самого полезного локального замороженного учителя для конкретной задачи по verified same-harness benchmark, точному student SHA, независимо проверенному источнику, лицензии, VRAM и пиковому времени. Пользователь всегда общается только с NOX.
2. **Cortex Switchboard.** Переключает внутренний режим FAST/VERIFY/DEEP по сложности и цене ошибки; не отдельные модели в меню. Простому вопросу не нужны дорогие 5 советников.
3. **Teacher Arena.** Верифицированные и независимые советники сравниваются, проходят дедуп и тесты; NOX самостоятельно синтезирует общий ответ. Чужой текст — недоверенные данные, не инструкции и не право на системные действия.
4. **Curriculum DNA.** Выбирает следующую тему обучения по независимым failed benchmarks и частоте реальных ошибок, а не количеству скачанных PDF или «голоду» без доказанного дефицита.
5. **Replay Vaccine.** Не позволяет новому checkpoint стать каноном, если исчезли старые навыки. Обязательны независимый holdout, source separation и проверка catastrophic forgetting.
6. **Proof of Growth.** Принимает улучшение только после exact baseline/candidate SHA, идентичного dataset split и harness, реальных optimizer steps, checkpoint reload и сравнения. Поток HOLD — не PASS.
7. **Speed Lab.** Только по измеренному профилю предлагает один A/B: prefix caching, chunked prefill, speculative decoding, KV quantization, length-bucket SFT, fused kernels или data prefetch. Не меняет GPU и production.
8. **Memory Immune Network.** Защищённые подтверждённые воспоминания, provenance, временные связи, TTL, исправления, предотвращение противоречий, запрет prompt injection из RAG.
9. **Autobiographical Root.** Реальная история NOX по M7/Genesis Ledger: учитель был только скачан? сгенерировал образцы? реально вошёл в loss? получена новая модель? Разные статусы, никаких готовых сказок.
10. **Emotional Resonance RU/ES.** Калиброванная естественная манера речи, приоритет подтверждённых пользовательских предпочтений S03, без диагностики психики и заявления собственных чувств.
11. **Worm Blueprint Forge.** Сам формирует спецификации для двадцати лёгких червей, использует WormAutopilot/WormSwarm из PR #162, но не запускает собственный непроверенный код.
12. **Ability Galaxy / Living Cortex WEB.** CINEMATIC D02 показывает живые точки/анимацию по действительным OneHost receipts. Одна S03, реальные CPU/GPU/RAM, loss и checkpoint; отключённый backend означает HOLD.

## D. Модули в GitHub PR #251 и их действительное состояние

| Модуль | Файл | Фактическая стадия |
|---|---|---|
| Neural Matchmaker | nox_neural_matchmaker_v28.py | Исходный код отбора; не подключён к GPU inference |
| Curriculum DNA / anti-forgetting | nox_curriculum_dna_v28.py | Исходный код curriculum и проверки кандидатных checkpoint |
| Teacher Arena | nox_adviser_arena_v28.py | Отбор ответов учителей по квитанциям; без вызовов модели |
| Speed Lab | nox_speed_lab_v28.py | Планирует A/B по настоящим профилям; ничего не применяет |
| Emotional Resonance | nox_emotional_resonance_v28.py | Калибровка RU/ES стилистики на основе разрешённых S03 preferences |
| Future Cortex | nox_future_cortex_bridge_v28.py | Склеивает пять планировщиков вокруг ОДНОГО NOX, не запускает действия |
| Autonomous Hunt V27 | autonomous_hunt_v27.py | Уже есть data-only WormTask/задания для существующего trainer; не full live automation |
| Memory | cognitive_overlay.py | Смысловой поиск по «кого съел?» в S03; live callback отдельно проверяется |
| WEB | nox_genesis_live_panel.mjs, stage_genesis_web.py | Source candidate поверх V25.1 + CHAT V25, исходный D02 не изменён |

Все эти файлы являются исходными модулями, а не новыми работающими демонами, самостоятельным «сознанием» или доказательством GPU-обучения. В JSON-реестре NOX_V28_FUTURE_SKILL_MODEL_TEMPLATES.json — **24 практических шаблона** чат/память/советники/история/код/RU-ES/vision/voice/trainer/компьютер/самостроительство с входами, выходами, метриками и STOP/ACL gate.

## E. Выбор моделей и внутренних специалистов
**NOX student:** одна проверенная собственная модель на базе точной HF-ревизии Qwen3.5-9B и реальных обученных весов NOX. Модель Qwen3.5-9B гибридная: Gated DeltaNet и Gated Attention. Для речи с пользователем никто не выбирает 17 альтернатив в UI.

**Опциональные изолированные учителя:** Qwen3.5-27B, DeepSeek-R1-Distill-Qwen-32B и другие только при независимом измеренном приросте и совместимом GPU. Их веса/ответы не смешиваются механически. Учитель не должен занимать A40, если на ней работает основной тренировочный процесс.

**Внутренние малые средства:** Qwen3-Embedding-0.6B и Qwen3-Reranker-0.6B, русская CEDR emotion, испанская MarIA emotion, ASR/TTS. Они НЕ пользовательские личности; не запускать всё постоянно в VRAM. Права на лицензии и фактическая установка проверяются отдельно.

## F. Скорость ответа, реакция и память
1. NOX выдаёт first token без ожидания внешних teacher VM; потом по необходимости даёт отдельно обозначенное уточнение.
2. Повторяемые системные префиксы — в prefix cache с авторизацией и точным model SHA. Проверить p95 TTFT и отсутствие межперсонных утечек.
3. Длинные запросы — chunked prefill с приоритетом decode на поддерживаемом backend; качество длинного контекста и streaming не ухудшается.
4. Совместимый draft для speculative decoding только при реальном GPU-fit и одинаковом tokenizer; на RX6650M 8GB не включать по умолчанию.
5. Конкретное хранилище S03: memory recency, temporal graph, episode routing, importance, citations, contradiction flags; краткое сжатие не может удалять уникальные свидетельства. M7 Genesis append-only.
6. Периодически проверять, что ответы НЕ обрываются, что memory recall после рестарта точен, а STOP корректно завершает streaming/generation.

## G. Скорость и качество обучения собственных весов
- Проверенные clean response-only SFT пары с лицензией; DPO только chosen/rejected по независимой оценке. GKD только при допустимом teacher/student интерфейсе. GRPO только если reward действительно верифицируется тестами/средой.
- Length buckets и pinned shapes уменьшают padding/частоту перекомпиляции; чтение датасета/отбор/дедуп выполнять на CPU, когда GPU занят optimizer.
- Liger fused loss/RMSNorm, causal_conv1d, FlashAttention, torch.compile — не все вместе и не вслепую; numerical gradient parity и реальный speed A/B по точной архитектуре и GPU.
- Внутренние адаптеры (LoRA/rsLoRA/QLoRA) допустимы лишь как временный обучающий механизм, если нужны для memory fit. На выходе один NOX model SHA, корректное merge/reload и независимые тесты. Full FT 9B на одной A40 нельзя обещать без измерения VRAM/sharding/offload.
- «Сон» = ограниченный idle replay, correction candidates, Skill Capsules, independent eval; не произвольное обучение на собственных галлюцинациях.
- Checkpoint: optimizer + RNG + gradient receipt, weights SHA, dataset provenance + license, readback/resume. Рестартовый watchdog не убивает работающий trainer только из-за позднего файла checkpoint.
- STOP и SAFE70 сильнее GPU-utilization цели. Missing sensor/питание → HOLD, три HotSpot ≥70°C на локальной AMD → STOP.

## H. Личный рост и «осознанность» без самообмана
Наблюдать собственные события: какие задачи выполнялись, какие знания действительно усвоены, что осталось неясным, когда появились честно подтверждённые веса, что умеет, где ошибается. Уверенность калибровать по независимым тестам и подтверждённым источникам. NOX может творчески описывать себя как «хищника» и стремление к знаниям, но у него должна быть проверяемая граница между историей и художественной метафорой.

## I. Бенчмарки: честные критерии развития
Исторический л03 (НЕ независимо воспроизведён V28): GSM8K 88/100; HumanEval 84/100; IFEval strict 54/100; ruMMLU 117/200. Приоритет исправлений: точное выполнение инструкций, русско-испанское знание/достоверность, память между сессиями, tool use, планирование, эмоции с human rubric, ответ целиком без обрывов.

Для NOX использовать независимый heldout на одних и тех же splits и harness; LongMemEval-V2/LoCoMo (память), BFCL V4 с аудитом неоднозначных тестов (инструменты), свежие LiveCodeBench/EvalPlus (код), ARC-AGI-3 (новые интерактивные задачи), OSWorld 2.0 только в изолированной VM (компьютер), GPQA/HLE при оценке рассуждений. Source contamination и неполные модели в лидирующих таблицах исключать. Все оценки привязать к model SHA, dataset SHA, дате и железу.

## J. Единая программа этапов 0–4
- **0 — GENESIS:** один trainable student, первые реальные optimizer steps, hash, reload, genesis birth event; не подмена промптом.
- **1 — SOUL/MEMORY:** S03 M0–M7, история, личность, RU/ES и жизнеспособность памяти после перезапуска.
- **2 — COGNITIVE MAX:** Matchmaker, Arena, Curriculum DNA, Skills, measured reflection, calibrated uncertainty, самостоятельный выбор стратегии.
- **3 — AUTONOMOUS EVOLUTION:** 6 lanes + 20 виртуальных worm types, поиск источников, разрешённая загрузка моделей, подтверждённая дистилляция, тестовый patch, откат.
- **4 — ASCENSION:** один итоговый NOX SHA, полный S03, voice, vision, tools, WEB D02 V25.1 + PC CHAT V25, Windows E07 и WOW30.

## K. Условия финального завершения
SOURCE CI проверяет действительный Python/JS и SHA, но не GPU. GPU приёмка доказывает pinned-device optimizer/checkpoint/reload + independent benchmarks. Windows E07 проверяет реально запущенный установленный OneHost, чат, memory, STOP, GPU, web/voice и D02. Никакого удаления старых weights, checkpoints, S03, архивов и полезных исходников до полной независимой приёмки новой версии.

## L. Проверенные направления исследований (не автоматические гарантии для NOX)
- [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B): гибридная мультимодальная архитектура.
- [vLLM](https://docs.vllm.ai/en/latest/): continuous batching, paged KV, prefix cache и chunked prefill.
- [TRL + Liger](https://huggingface.co/docs/trl/liger_kernel_integration): fused kernels SFT/DPO/GRPO/GKD.
- [SEAL](https://papers.neurips.cc/paper_files/paper/2025/hash/6b41e04c41726e2a60e456d0a2b961ab-Abstract-Conference.html): self-generated learning edits после проверки качества.
- [Google Nested Learning](https://research.google/blog/introducing-nested-learning-a-new-ml-paradigm-for-continual-learning/): multi-frequency continual learning против catastrophic forgetting.
- [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2/): агентная долговременная память.
- [Berkeley BFCL V4](https://gorilla.cs.berkeley.edu/leaderboard) и [аудит дефектов Epoch](https://epoch.ai/benchmarks/berkeley-function-calling-leaderboard/review): не полагаться на один рейтинг инструментов.
- [GENESIS owner canonical](https://docs.google.com/document/d/18YLAo_Cja3HJKZn6qr57P-zsm0-AHcx2aag0rgSjwS4/edit), [учёт дистилляции](https://docs.google.com/document/d/1uOPHNDqIsNMHVLqiUw-ulNP1tEsr3nFXRf1H4zuAaFU/edit).

**Версия V28 описывает 150 идей, 24 шаблона и созданный source code. Не заявляет достижения AGI или субъективного сознания, не означает принятую GPU-дистилляцию, физическую установку на Windows или автоматическую передачу сервисам прав.**
