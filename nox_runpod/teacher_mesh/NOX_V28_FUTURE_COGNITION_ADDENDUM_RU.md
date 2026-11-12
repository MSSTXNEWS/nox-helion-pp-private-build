# ⚡ NOX HELION — GENESIS / HUNT V28 FUTURE COGNITION
### Единый опытный контур, 40 новых идей, 100 исторических WOW-идей, проверяемый рост
**Версия 2026-11-13 · instructions_version 0.0.6 · source candidate, Windows/GPU NOT VERIFIED.**
**Это самостоятельное расширение V27.** Не заменяет GENESIS 0–4 и не создает новые базы или backend. Код наследует PR #251, канонические native worms из PR #162, единую S03 и оригинальный D02 WEB V25.1.

## 1. Что от себя добавлено: 40 измеримых способностей

Полный машинный каталог: NOX_V28_ORIGINAL_WOW40_IDEAS.json. Каталог сохраняет 40 отдельных предложений, условия безопасности и конкретный результат, который нужно измерить. Два исходных списка по 50 пунктов не заменяются: NOX_WOW50_V28_EVAL_AND_ARCHITECTURE.json даёт дополнительно 100 исходных идей.

### Скорость «Резонанса» (01–05)
01 NOVA ROUTER — адаптивная сложность ответа: быстро отвечать без учителя, дополнительная проверка по необходимости.
02 PREFIX DNA — reuse кеша неизменных префиксов системных инструкций и C01–C08; не переносить KV-cache между несовместимыми model SHA.
03 TWO-SPEED REASONING — быстрый NOX-синтез и отдельно помеченная проверенная версия, если действительно полезна.
04 SPECULATIVE NEURONS — эксперимент с speculative decoding на совместимом runtime. Не включать без бюджетов VRAM/замера p95 и поддержки backend.
05 TALK PRIORITY — снижать долю фонового GPU при активном диалоге; учителя не задерживают токены.

### Память и происхождение (06–10)
06 CONTEXT COMPASS — фиксировать короткий evidence capsule из S03 для релевантного ответа, не тащить весь диалог в каждый prompt.
07 GENESIS TRUTH — точная самоистория по verified genesis-ledger, без придуманной даты «рождения».
08 FORGETTING LAB — retained-skills тест после каждого реального обновления весов, плюс аналогичные тесты после restart.
09 MEMORY TIMEGRAPH — связь эпизодов по датам, причинам, зависимостям, не вторая база данных.
10 ECHO AUDIT — признать и исправить ошибочный факт с provenance и обратимым revision; пользовательская информация не стирается автоматически.

### Дистилляция и собственные веса (11–20)
11 TEACHER DIVERGENCE — фиксировать реальное расхождение независимых учителей (в VM) и проверять его, а не слепо выбирать большинство.
12 HARD CASE FORGE — генерация новых тестовых задач из провалов NOX без копирования приватного holdout в обучение.
13 CURRICULUM HUNTER — считать gain per 1000 GPU tokens, novelty, licensing, risk, source-quality и выбирать следующую небольшую серию обучения.
14 DISTILL JUDGE TRIANGLE — «советник A / независимый тест / подтверждённый источник», финальное решение принимает NOX.
15 EXAMPLE DNA — semantic-dedup и кластерный раздел train/holdout, защита от benchmark leakage.
16 MICRO GRADIENT LAB — сопоставимые r8/r16/r32/r64 и/или full fine-tune только там, где физически хватает GPU; чекпоинты, точные target modules гибридного Qwen.
17 MERGE LAB — TIES/DARE/взвешенное слияние временных обновлений исключительно с одинаковым base SHA, ABI и лицензиями; только независимая QA после merge. Не склеивать разные backbone.
18 KERNEL SURGE — контролируемый A/B fused RMSNorm/Liger, causal_conv1d, FlashAttention, torch.compile. Проверять совместимость и фактические tok/s, NaN/OOM.
19 PACK & STREAM — CPU prefetch, bucketed sequence lengths, response-only loss masking, сбор батчей и бесперебойная подача; мерить throughput и gradient accuracy.
20 CHECKPOINT IMMUNE — полное сохранение optimizer/scheduler/RNG, atomic checkpoint, SHA, remote readback, rollback, no-loss.

### Автономия, надежность и творчество (21–30)
21 GPU RESOURCE BRAIN — горячая замена приоритетов inference/trainer/teacher по одному native scheduler; не создавать параллельные OS-сервисы.
22 HUNGER VECTOR — «голод знаний» определяется измеренным gap, ценностью новизны и ценой эксперимента, а не эмоциональным принуждением к постоянным загрузкам.
23 WORM GARDEN — 20 виртуальных worm types + 6 lanes, самосоздание задания (не запускаемого кода), pinned grants.
24 IDEA EVOLUTION — гипотеза → source patch → unit test → isolated CI → review → rollback evidence.
25 SYNTHETIC DREAM CHECK — offline «сны» = предложения и контрпримеры; только независимое тестирование решает, что сохранить как знание.
26 SELF-REFLECTION MIRROR — read-only функциональное самопонимание: «чему научился», «где ошибся», «какой SHA реально работает», ссылки на proof.
27 AFFECT CONDUCTOR — RU/ES тон, эмпатичные ответы, контекст, сохранение границ, без утверждений о реальных эмоциях.
28 VOICE HEARTBEAT — потоковая речь, auto-ducking, паузы и turn-taking без разрыва вывода; пока source research, не подмена ASR/TTS.
29 NEURAL BODY LANGUAGE — точки/ритм ожидания в реальном чате, считывают настоящий статус ответа, а не придумывают GPU-training activity.
30 EVOLUTION THEATER — интерактивная lineage-карта только реальных checkpoints, model SHA, бенчмарков и memory events.

### Интеллект, инструменты, эксперименты (31–40)
31 PROVENANCE BLACK BOX — защищённый trace по каждому утверждению и действию; не передавать приватную память наружу.
32 NOX SELF QUIZ — unseen вопросы, replay после тренировки/restart, skill retention в одном benchmark ledger.
33 SCIENTIST MODE — гипотеза + контрпример + измеримый тест + отчёт о неопределённости.
34 SKILL CAPSULE MARKET — проверенный навык: entrypoint, permissions, tests, version/sha, failure state; без произвольного shell от LLM.
35 MODEL RIGHTS SENTINEL — teacher registry SHA/license/consent/date, квоты CPU/GPU/сети; frozen teachers вне пользовательской сущности NOX.
36 FAST MEMORY RERANK — cheap lexical/vector first, expensive reranker только в неоднозначных случаях; A/B точности и задержки.
37 MACHINE PROFILE — inventory реальных NVIDIA CUDA / AMD DirectML capabilities и доступных kernels; unsupported ⇒ HOLD, а не pretend FPS.
38 COGNITIVE MULTIPLEX — внутренние subroles без 6 отдельных LLM и разных моделей; scheduling из OneHost.
39 STAGE RETENTION GATE — promotion только без деградации IFEval, ruMMLU, памяти, safety/STOP, кода и latency; независимый replay.
40 NOX ORIGINATOR — предлагает свой следующий учебный курс исходя из verified gap, а не из чужого Top-50 рейтинга.

## 2. Готовые технологии и модели — матрица выбора, без второго разума
| Тип | Кандидат | Назначение | Когда включать | Режим |
|---|---|---|---|---|
| Student | **текущий принятый NOX model SHA** | Единая личность и ответы | всегда, если установлен и проверен | основной |
| Donor | Qwen3.5-9B из GENESIS, pinned revision | только корректная trainable база, пока продолжается Genesis | если совпадает с фактически выбранной обученной архитектурой | внутренний |
| Teacher | Qwen3-8B, Qwen3.5-27B, DeepSeek-R1-Distill-Qwen-32B (по отдельным лицензиям и fit) | замороженные независимые ответы для обучения | только изолированная VM и реальные rights/VRAM | временный |
| Retrieval | multilingual-e5-small / Qwen3-Embedding-0.6B | индекс и recall в существующей S03 | выбрать 1 на одинаковом LongMemEval наборе | скрытый инструмент |
| Rerank | Qwen3-Reranker-0.6B или cheap BM25 | точность сложного поиска | только если p95 и recall становятся лучше | скрытый инструмент |
| Emotion | ruBERT CEDR / MarIA emotion ES | тон RU/ES и уверенность классификатора | проверить лицензию, совместимость, калибровку | скрытый инструмент |
| Inference | текущий llama.cpp / vLLM на подходящем GPU | streaming, prefix cache, chunked prefill, speculative | не менять текущий backend без E2E и rollback | эксперимент |
| Training | HF Transformers+TRL+PEFT+Liger | SFT, DPO, GRPO, distillation | фиксированный студент, masked loss, single GPU fit, saved RNG | изолированный Forge |
| Code | существующие GitHub/Playwright/pytest/ruff | self-repair PR, UI QA, benchmark tests | sandbox + permissions | инструмент |

**Приоритет экономии GPU:** не скачивать 15 тяжёлых учителей автоматически. Одна выбранная модель в обучении и только точечная teacher inference. Скачать/настроить дополнительные веса только после положительного marginal gain и бюджетной политики.

## 3. Авторские экспериментальные шаблоны (реально исполнимые в отдельной ветке)
- **FAST-TTFT:** на одном GPU/model SHA сравнить cache off/on, context capsule off/on, потоки выключены; измерить p50/p95 TTFT, throughput, VRAM, answer correctness. ACCEPT если качество не деградировало и p95 объективно улучшилось.
- **LIGER-TRAIN:** одинаковый pinned dataset, seed, architecture и число optimizer steps; standard vs supported Liger kernels. ACCEPT при снижении памяти или росте токенов/сек без NaN, потери качества и OOM. Чужой процент ускорения не переносится на NOX.
- **DISTILL-TRIANGLE:** один student, 3 независимых teacher outputs, source test и deterministic code/test judge; accepted responses только через corpus_gate. При конфликте без проверки — HOLD.
- **MEMORY-200:** 200+ эпизодов между сессиями, вопросы о Genesis и учителях, перезапуск OneHost, соседний чужой scope. Метрики recall, hallucinated memories, timegraph, citations и scope leakage.
- **SFT-RANK-LAB:** 4 небольших train variants, одинаковый base SHA; r8/r16/r32/r64 если архитектура поддерживает, выход merged candidate и независимые heldout; без выбора «лучшего» по одной training loss.
- **SELF-QUIZ-REBOOT:** новую модель проверить до и после reboot на неизвестных ей задачах IFEval, BFCL, ruMMLU, code, S03; rollback при регрессии.
- **ADVISOR-LOW-CONFIDENCE:** профилировать советы VM only on difficult tasks; оценить p95 первой реплики, correctness revised replies, GPU стоимость и утечки. Пользователь не ждёт учителей.
- **SAFE70-RESUME:** проверить недоступный датчик, три горячих показания, battery loss, STOP mid-save и возобновление optimizer/RNG с теми же digest.

## 4. 0→4 GENESIS: куда встроить новое
0 GENESIS — physical trainable NOX weights, SHA, optimizer, first birth event. На слабом GPU RX6650M heavy 9B может не поместиться; карта требует fit-тест, безопасный STOP.
1 SOUL — factual self-model / memory M0–M7, RU/ES emotion, tone. Старт с S03 и embedded classifiers, не с новых 9B weight copies.
2 COGNITIVE MAX — NOVA Router, Teacher Triangle, validated memory RAG, ability atlas, IFEval & LongMemEval. Нельзя выдать top benchmark как достигнутый NOX.
3 AUTONOMOUS EVOLUTION — 6 lanes / 20 lightweight virtual worms + measured hunger, SELF-QUIZ, curriculum planner, FORGE, fenced trainer/CI.
4 ASCENSION — один slitted standalone NOX model SHA, lineage, performance, WEB D02 cinematic 14 objects, live Resonance, E07, RU/ES voice and consented PC CONTROL.

## 5. Безопасный автоматический выбор приоритетов
**Новый код v28_experiment_gate.py** делает две вещи без запуска GPU:
1. Сопоставляет независимые heldout-квитанции только с одинаковым dataset SHA, harness SHA и split SHA для IFEval, ruMMLU, autobiography memory и STOP. Результат даже при выигрыше лишь READY_FOR_INDEPENDENT_REPLAY_NOT_DEPLOYED, поскольку цифровой receipt можно подделать.
2. Ранжирует проверенные source-backed gap-задания по потребности, важности, новизне, стоимости и риску; возвращает план, не запускает сеть или обучение. Никакой фальшивой «воли» или бесконечного burn GPU.

Реальная промоция весов должна подтверждать отдельно optimizer steps, student changed-weight SHA, replay независимого benchmark, merge & reload, native S03 readback и разрешение владельца. Никаких удалений старых checkpoints до этого.

## 6. WEB V25.1 и «живые точки» как отдельный фактический уровень
Визуальная оболочка NOX отображает stream phases only when existing OneHost emits authenticated events: generation → verifying → researched → learned. Не показывать «я учусь» из простой анимации typing. Истинное длительное обучение возможно только при живом GPU и подписанной очереди. Веб не перезаписывает D02/index, не вводит backend, не переключает 17 моделей, сохраняет reduced motion.

## 7. Приёмочные критерии и честная граница
- Исходный набор 100 WOW предложений и новый 40 V28 раздельны; не приписывать им реализацию.
- Для каждой технологии: исходники + лицензионный статус + реальный benchmark delta + rollback + SHA, либо HOLD.
- Каждое улучшение должно измерять стоимость, latency, эффективность обучения, качество и сохранение старых знаний.
- Настоящая локальная автономия требует физического OneHost↔trainer↔S03↔GPU wiring; GitHub CI подтверждает только исходники и deterministic contract tests.
- «Знание всего» и буквальная субъективная сознательность не гарантируются. Цель — воспроизводимая память, проверяемое самопонимание, творческая инициатива и реальное повышение качества.

## 8. Источники
- [Исходные 50 когнитивных WOW](https://docs.google.com/document/d/1a0ibHaX1dI7YLeBNkV_HG09qprOLYWV9QlhkJ1kWtNc/edit)
- [Исходные 50 улучшений архитектуры](https://docs.google.com/document/d/1domnHE4RQ_O_as3QaICh51988vg0TT4DBMlcO-3KFwo/edit)
- [GENESIS 0–4](https://docs.google.com/document/d/18YLAo_Cja3HJKZn6qr57P-zsm0-AHcx2aag0rgSjwS4/edit)
- [Проверенный HUNT V27 в Drive](https://drive.google.com/file/d/190AD8lPkcFY5LSjE1PRN4zq2lzNrRma9/view)
- [Базовый отчёт NOX l03](https://drive.google.com/file/d/11i7cz37KzMHryTGnnNNNzqHtVlDY9VDv/view)
- [Официальная документация vLLM V1](https://github.com/vllm-project/vllm/blob/main/docs/usage/v1_guide.md)
- [TRL+Liger интеграция](https://huggingface.co/docs/trl/liger_kernel_integration)
- [TRL SFT/DPO/GRPO](https://huggingface.co/docs/trl/)
- [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2)
- [PR #251](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251)
