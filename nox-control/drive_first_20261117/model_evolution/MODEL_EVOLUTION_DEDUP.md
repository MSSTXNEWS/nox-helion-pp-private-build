# NOX: развитие самой модели и расширение контекста — проверка повторов

**17.11.2026 · Design only · native deployment=false.** Проверены целиком текущие локальные `NOX_Unique_Concept_20261117.md` и `NOX_FAST_CHAT_SIX_IMPLEMENTATION_20261117.json` revision 4. SHA и границы проверки — в `INPUTS_RECEIPT.json`. Это не заявление о повторном чтении всех документов Drive.

**Итог: 17 предметных направлений — 9 новых подпредложений и 8 уточнений уже существующего.** Исходные 240 карточек и их ID сохранены. ME01–ME17 — идентификаторы этого документа, не native TaskID. Во всех связях с очередью остаётся `mapping_needed`; задачи и модели этим документом не запускаются. YaRN и LongRoPE — альтернативные кандидаты одного семейства, а не суммируемые множители.

## Что не добавляем повторно

Adaptive reasoning и sampling → **N21-09**; prefix/slot reuse → **N21-02**; quantized KV → **N21-07 / OF23**; RAG и S03 → существующий **N08**; LoRA → **N10-06 / OF43**; DPO → **N10-07**; teacher distillation → **§5.3 Teacher Distillation with Provenance** и N10; MTP → **OF29**; Titans/HOPE/SEAL/Coconut → **N24-01/02/03/04**. Они получают уточнения только там, где ниже указан новый конкретный механизм или критерий.

## G0: обязательный паспорт модели перед изменением её математики

Расширить **N21-10**, не создавать второй registry: model/shard SHA, tokenizer и chat_template SHA, GGUF general.architecture, trained context, block/head/KV dimensions, RoPE type/base/scaling/original length, MLA/SWA/hybrid признаки, tensor names/types и точный binary/commit/flags. Значения берутся из доверенного файла/конфига/runtime, неизвестные поля остаются неизвестными. **Название «DeepSeek-V4.1» и наличие IQ2_XXS не доказывают поддержку YaRN, LongRoPE, MLA cache, MTP или специального quant export.** GGUF описывает поля RoPE; их наличие в спецификации не означает поддержку всей цепочкой конкретного converter/loader/kernel. [S01], [S02].

Master документация llama.cpp показывает текущие возможности upstream; установленный fork/commit NOX может отличаться. Перед реализацией требуется pin source→installed. Новые flags из документации не вставляются в native launcher этим отчётом.

## Готовое read-only средство для G0

В этом пакете **реализован**, а не только предложен, `gguf_metadata_probe.py`: stdlib parser GGUF v2/v3, metadata span максимум 64MiB, выбранные scalar values, vocabulary/numeric arrays пропускаются seek без загрузки. Чтение прекращается сразу после KV metadata; tensor table и weights не читаются. Два fixture-теста проходят. Native выполнение в этой сессии не проводилось.

Default path: `/root/nox/models/deepseek_v41_flash_iq2xxs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf`. API: `inspect_gguf(path)`; CLI печатает `NOX_GGUF_METADATA=<JSON>`. В выводе architecture/name, GGUF version, file_type/quantization_version, declared context, head/KV dimensions и RoPE scalar metadata. Runtime total/per-sequence context остаются null: их нужно объединять с отдельным доверенным runtime evidence. Первый shard не объявляется проверкой всех весов, trained/effective context не выводятся автоматически из одного metadata поля.

## Реальный бюджет контекста и весов

В запросе должно выполняться `input_tokens + reserved_output_tokens + template/tool_overhead <= observed_per_sequence_limit`. Отдельно проверяются итоговая длина обученного/валидированного окна и число слотов. Из одного `-c8192 -np2` нельзя объявить ни 8K, ни гарантированные 4K на любой версии runtime: нужна фактическая per-sequence конфигурация. [S02].

Для обычного dense/GQA внимания инженерная оценка KV: `sum_layers(allocated_tokens × KV_heads × (K_dim × K_bytes + V_dim × V_bytes))`, плюс padding/allocator/scratch. Для MLA, SWA и гибридов формула другая; использовать reported allocation и измеренный рост, а не подставлять GQA автоматически. IQ2 относится к весам и не делает текущий F16 KV двухбитным. При увеличении окна фиксируются KV, prefill peak, задержка и реальная полезная длина. У большого контекста есть стоимость даже при всех холодных файлах на Drive.

Предоставленный native snapshot показывает примерно memory.current 193.36GB, file 190.12GB, shmem 75.40GB и inactive_file 92.65GB при PSI0. `shmem` входит в `file`; их нельзя складывать как отдельные потребления. `inactive_file` — верхняя оценка кандидата на reclaim, не гарантированный свободный бюджет. Это прежнее наблюдение, не live headroom: перед запуском требуется свежий cgroup `max-current`, host-wide reservation и измеренный пик. Chat/core/Engram защищены; пауза процесса не равна освобождению памяти.

Две или три версии quant хранятся как артефакты, а не как постоянно загруженные копии. Восстановить потерянную точность простым IQ2→F16 преобразованием нельзя: для нового качественного quant нужен original higher-precision checkpoint либо отдельно обученный кандидат. [S10].

## 17 конкретных направлений

Все пути ниже — **предлагаемые артефакты реализации, пока не созданные скрипты**. Код установщика UI в соседнем пакете реален; этот документ — исследовательский план модели, а не комплект обученных весов. L/M/H/R обозначают относительную стоимость, указанную в каждом пункте; точный RAM/VRAM бюджет без manifest/measurement не обещается.

### ME01. Реальное расширение доступного окна с бюджетом на последовательность

**Слияние:** NEW_SUBPROPOSAL → N21-01, N21-10, OF23. **Фаза:** P1_AFTER_CHAT_AND_G0.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/context_capacity.py`.

**Реализация:** Создать кандидатные профили длины на основе фактического n_ctx_per_seq/слотов и metadata. Сначала использовать уже обученное и поддержанное окно, затем переходить к ME02/03. Профиль содержит вход, резерв ответа, template overhead, измеренные KV/scratch и maximum allowed peak; ошибка бюджета даёт HOLD, не тихое обрезание поручения.

**Допуск:** G0; подтверждённые per-sequence limits установленного бинаря, оценка пика и maintenance/admission. -c8192 -np2 сам по себе не доказывает 8192 токена каждому диалогу.

**Приёмка:** На следующей допустимой ступени помещается цельный документ и полный ответ; нет скрытой truncation; measured peak <= reservation; фиксируются TTFA и effective context ME05.

**Цена:** L для паспорта; M/H для прогона. Дополнительные KV и scratch остаются в RAM/VRAM. Архив на Drive этого не устраняет. Число гигабайтов вычисляется по конкретной архитектуре.

**Почему это не дубль:** Канон описывает экономию контекста/prefix, но не содержит отдельного контракта увеличения действительного per-sequence окна. Источники: [S01] [S02].

### ME02. YaRN как проверяемая конфигурация позиционного расширения

**Слияние:** NEW_SUBPROPOSAL → N21-10, N10-08, OF50. **Фаза:** R_AFTER_ARCH_COMPATIBILITY.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/rope_candidates/yarn.json`.

**Реализация:** Построить отдельный кандидат с exact architecture, original_context_length, scaling factor и параметрами YaRN, подтверждёнными checkpoint и runtime. Сравнить с исходной RoPE на равном quant и задачах. Если нужна доадаптация весов, она проходит ME04.

**Допуск:** G0 подтверждает RoPE, размеры и исходное обучение; converter и установленный runtime понимают нужные metadata/вычисление. Существующая scaling не умножается повторно. DeepSeek-V4.1 по имени не получает автоматически поддержку YaRN.

**Приёмка:** ME05 на старом и расширенном окне; короткие задачи, русский/испанский и числа не деградируют; near-boundary позиции проверяются отдельно; совместимость подтверждается GGUF roundtrip.

**Цена:** M для совместимого inference-кандидата; H при дообучении. Рост контекста оплачивается KV/scratch. Метаданные сами по себе почти ничего не весят.

**Почему это не дубль:** YaRN не найден в проверенных двух канонических документах; это новая ветвь, не повтор prefix cache. Источники: [S01] [S03].

### ME03. LongRoPE/LongRoPE2 с сохранением короткого контекста

**Слияние:** NEW_SUBPROPOSAL → N21-10, N10-03, N10-08, OF50. **Фаза:** R_OFFLINE_STUDENT.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/rope_candidates/longrope_trial.json`.

**Реализация:** Отдельная альтернатива YaRN: искать коэффициенты позиционного преобразования на малом совместимом студенте, затем смешивать короткое/длинное обучение и экспортировать отдельный checkpoint. LongRoPE2 использовать только по воспроизводимой опубликованной реализации; отсутствие кода/операций GGUF оставляет research status.

**Допуск:** Trainable source weights, разрешённые длинные данные, поддержанный архитектурный класс, точный conversion contract и отдельный GPU-бюджет. Результаты LLaMA/Phi/Mistral не являются характеристиками текущего NOX.

**Приёмка:** Эффективная длина и короткое качество оцениваются вместе; поиск коэффициентов не видит закрытый тест; замер conversion/inference совпадает с тренируемым позиционным преобразованием.

**Цена:** H/R. Search и continued training могут требовать значительного compute; 128K/2M не обещаются для V100 или текущего GGUF. Production профиль не меняется.

**Почему это не дубль:** LongRoPE отсутствует; это альтернативная реализация семейства rope_extension, не второй суммируемый множитель длины. Источники: [S04] [S05] [S06].

### ME04. Дообучение настоящему использованию длинного документа

**Слияние:** AUGMENT_EXISTING → N10-03, N10-05, N10-06, N10-08, OF42, OF43. **Фаза:** P2_TRAINING_ADMISSION.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/long_context_curriculum.py`.

**Реализация:** Расширить существующий curriculum_mixer корзинами коротких, средних и длинных документов: дальняя зависимость, поздняя поправка факта, связка двух удалённых разделов. Сначала continued language-model objective на разрешённых документах, затем assistant-only SFT для задач; маски этих двух этапов различаются.

**Допуск:** G0, N10-01/02, baseline того же trainable студента, подтверждённый trainer/attention на SM70. Исходный DeepSeek GGUF не становится trainable checkpoint; Qwen-студент остаётся отдельной моделью.

**Приёмка:** Дальние задачи улучшаются на новых документах; короткий holdout и исходные навыки удержаны; каждая последовательность прошла token/mask audit и отсутствие утечки.

**Цена:** H. Активации и optimizer/RNG checkpoint учитываются отдельно; длинный sequence может стоить существенно дороже короткого. Отдельное окно обучения.

**Почему это не дубль:** Не новая карточка LoRA: новый objective/curriculum внутри N10-03/05/06 с экзаменом N10-08. Источники: [S03] [S05].

### ME05. Сертификат эффективного, а не только допустимого контекста

**Слияние:** AUGMENT_EXISTING → N06-10, N10-08. **Фаза:** P1_AFTER_CLEAN_BASELINE.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/effective_context_eval.py`.

**Реализация:** Добавить к существующему экзамену RULER/LongBench-подобные наборы: несколько искомых фактов, порядок/время, далёкая зависимость, проверка середины документа и противоречащий distractor. Объявлять длину лишь там, где решение действительно сохраняется.

**Допуск:** Фиксированные tokenizer/template/model/quant SHA, длины измерены в токенах данного токенизатора; наборы без train overlap. Перед каждым запросом существующий chat-first admission.

**Приёмка:** Отчёт accuracy-by-length-and-position, factual consistency, short-retention, TTFA, p95 end-to-end и peak memory; single-needle PASS не выдаётся за общее понимание.

**Цена:** L для генерации маленького набора; M/H для inference по длинам. Одно последовательное оценочное окно, не benchmark в двух слотах владельца.

**Почему это не дубль:** Расширение действующего N06-10/N10-08, а не новый общий benchmark или повтор памяти RAG. Источники: [S07] [S08].

### ME06. Калибровка IQ-квантования на реальных языках и задачах

**Слияние:** NEW_SUBPROPOSAL → N21-10, N10-01, N10-02, N10-08. **Фаза:** P2_OFFLINE_QUANT_ADMISSION.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/imatrix_manifest.py`.

**Реализация:** Подготовить отдельный calibration corpus RU/ES/code и bounded llama-imatrix job; зафиксировать model/tokenizer SHA, corpus hash, длины и покрытие тензоров. Пересобрать candidate quant из законного high-precision source, не из уже потерявшего информацию IQ2. Holdout в calibration не включается.

**Допуск:** Поддержка нужной архитектуры в точном imatrix/quantizer бинаре; исходные веса и ресурсный допуск. Текущий Engram не переквантовывается. Если high-precision source отсутствует — подготовка corpus/manifest, без ложного quality gain.

**Приёмка:** A/B при одном размере/типе quant: perplexity, кодовые тесты, RU/ES factual tasks и MOE coverage. Выигрыш подтверждается задачами, а не только imatrix file existence.

**Цена:** L для corpus manifest; M/H для прохода модели и сборки. Нужны исходные/новые веса, scratch и лимит временных буферов; холодное хранение возможно на Drive.

**Почему это не дубль:** imatrix отсутствует в проверенных документах; это качество весов при квантовании, не KV cache или обучение LoRA. Источники: [S09] [S10].

### ME07. Два-три уровня качества весов и выборочная точность тензоров

**Слияние:** NEW_SUBPROPOSAL → N21-10, N10-08, N22-06, OF50. **Фаза:** P2_AFTER_ME06.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/tensor_precision_plan.py`.

**Реализация:** Составить по настоящим tensor names три кандидата: текущий baseline, экономный mixed-precision и quality profile. Проверять чувствительность attention projections/router/output/embeddings; повышать точность только доказанно чувствительных групп. Экспорт через поддержанные --tensor-type/--output-tensor-type/--token-embedding-type, после dry-run.

**Допуск:** G0 и higher-precision original weights, совместимость quant types/ops установленного бинаря. Превращение IQ2 в F16/Q4 не восстанавливает исходные потерянные значения. Три профиля — три артефакта, не три одновременно загруженные модели.

**Приёмка:** Pareto-таблица quality/bytes/TTFA; фиксированные задачи, same template. Дополнительные весовые bytes и пик смены профиля измерены; нет утверждения, что большая точность всегда даёт полезный выигрыш.

**Цена:** M/H. Δbytes оценивается по tensor numel и реальным типам/блокам, затем проверяется размером GGUF. Смена профиля только через существующий admission/rollback; без reload на каждую реплику.

**Почему это не дубль:** Новая конкретная процедура улучшения weight fidelity; OF50 содержит только общий research risk, а N21-07 относится к KV. Источники: [S10].

### ME08. Сохранение точности маршрутизатора и важных MoE-экспертов

**Слияние:** NEW_SUBPROPOSAL → N21-10, N10-08, OF50. **Фаза:** R_OFFLINE_MODEL_DIAGNOSTIC.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/moe_quality_probe.py`.

**Реализация:** На совместимом исследовательском runtime сравнить выбор top-k и output drift у quant и high-precision reference по фиксированным токенам. Исправлять gate/router precision или чувствительные expert tensors, оставляя learned top-k неизменным. Если эксперты упакованы в один fused tensor, per-expert quant без нового формата/loader не обещать.

**Допуск:** Подтверждённая MoE архитектура и доступ к диагностике routing; точные tensor layouts. Статистика popularity не доказывает бесполезность редкого эксперта; изменение маршрутизации требует отдельного обучения.

**Приёмка:** Routing agreement, rare-task quality, perplexity и общий набор. Кандидат не проходит только потому, что стал вызывать меньше экспертов.

**Цена:** M/H offline; instrumentation добавляет overhead. Повышение router precision иногда мало по объёму, expert-group precision может быть дорогим: считать по tensor manifest.

**Почему это не дубль:** Не N21-05: там CPU/cache placement. Здесь сохраняется численная функция самой MoE, без нового expert cache. Источники: [S10] [S11].

### ME09. Восстановление качества после квантования отдельным обучаемым кандидатом

**Слияние:** AUGMENT_EXISTING → N10-06, N10-08, OF42, OF43. **Фаза:** R_STUDENT_TRAINING.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/quant_recovery_trial.py`.

**Реализация:** Добавить в уже существующий training trial контролируемую QAT/quantization-aware distillation ветвь малого студента: teacher targets разрешённого источника, симуляция целевых ошибок quant, затем фактический export и повторный экзамен. Сначала выяснить, совпадают ли используемые группы/rounding с экспортом GGUF.

**Допуск:** Совместимый trainable source и quant simulator, лицензированные данные/teacher use, отдельный training budget. LLM-QAT не является готовым патчем IQ2_XXS текущей DeepSeek; без эквивалентности форматов — RESEARCH_ONLY.

**Приёмка:** Исходный student, обычный quant и восстановленный quant сравниваются на одном holdout; улучшение должно пережить фактический GGUF export, а не только fake-quant PyTorch.

**Цена:** H/R. Teacher/offline labels и optimizer могут доминировать. Не держать второй огромный backbone постоянно; никакого live самообучения от ответа советника.

**Почему это не дубль:** Дистилляция уже есть в §5.3 Teacher Distillation with Provenance и N10; это её quant-specific objective, не новая копия training engine. Источники: [S12].

### ME10. Обучение рассуждению по проверяемому результату — RLVR

**Слияние:** NEW_SUBPROPOSAL → N10-04, N10-06, N10-08, N24-06. **Фаза:** R_OFFLINE_STUDENT.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/verified_reward_trial.py`.

**Реализация:** Определить маленький набор математических задач/изолированных code edits с детерминированным проверяющим. После SFT сравнить bounded RLVR/GRPO кандидата с SFT-only при одинаковом inference budget. Reward — корректность результата и выполнения constraints, не самопохвала модели и не длина рассуждения.

**Допуск:** N10 dataset/holdout/teacher policy; рабочий reward sandbox, совместимый TRL/student, лимиты rollout и остановка по ресурсам. Число rollout не связано с числом постоянных NOX workers.

**Приёмка:** Unseen problems, pass@1 на равном budget, adversarial reward-hacking cases, regression RU/ES/tool use. Положительный reward без внешнего PASS не принимается.

**Цена:** H/R. Много последовательных rollout и training updates; для основного большого checkpoint на заполненном host не допускается.

**Почему это не дубль:** В текстах найдены DPO и verifier, но нет самостоятельного verifiable-reward weight objective. Оно использует существующий trial, не создаёт ещё одну очередь. Источники: [S13] [S14].

### ME11. Обучить точному различению знания и неопределённости

**Слияние:** AUGMENT_EXISTING → N06-07, N10-04, N10-07, N10-08. **Фаза:** P2_EXISTING_TRAINING_TRIAL.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/epistemic_training_pairs.py`.

**Реализация:** Расширить существующие пары/калибровку: известный факт, неизвестный факт, ложная предпосылка, доступное внешнее подтверждение. Учить короткому честному ответу/проверке источника, а не универсальным философским оговоркам. Пары размечаются по проверенной истине и доступному контексту, не по уверенности учителя.

**Допуск:** Раздельные known/unknown labels, текущий trusted runtime envelope и provenance. Известная конфигурация модели не должна превращаться в неизвестность из-за отсутствующего пользовательского порта.

**Приёмка:** Accuracy-coverage, calibration, false-abstention на известных вопросах и hallucination rate на новых; «стало чаще отказываться» не является качеством.

**Цена:** L для разметки; H для уже допущенного SFT/DPO кандидата. Повторно использовать N10-07 infrastructure.

**Почему это не дубль:** N06-07 уже отвечает за calibration, N10-07 за preference weights: добавляется weight-level objective, карточки не дублируются. Источники: [S15].

### ME12. Больше смысла на токен: осторожная RU/ES адаптация словаря

**Слияние:** NEW_SUBPROPOSAL → N21-10, N10-03, N10-05, N10-08. **Фаза:** R_CONTROLLED_STUDENT.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/tokenizer_expansion_trial.py`.

**Реализация:** Сначала измерить токены на слово/символ для реального RU/ES/code набора. При доказанной фрагментации на отдельном контролируемом студенте расширить BPE, сохранить старые token IDs, инициализировать новые embedding/output rows из исходных subtoken rows, обучить новые строки и затем адаптировать модель.

**Допуск:** Полный контроль tokenizer/embeddings/head/training и export; новые tokenizer/template hashes инвалидируют prefix/slot caches. Нельзя заменить tokenizer JSON у работающего GGUF без согласованных весов.

**Приёмка:** Chars-per-second и end-to-end quality вместе; token-count сам по себе недостаточен. Старые special tokens, tool-call grammar, code spacing и старые языки проходят regression. Результаты LFM на иных языках не обещаются для RU/ES.

**Цена:** H/R. Увеличение словаря раздувает embedding/head и стоимость каждого decode шага; экономия токенов может быть перекрыта этим ростом.

**Почему это не дубль:** Расширение словаря не найдено; экономия возникает в обученном представлении, не через сжатие RAG prompt. Источники: [S16].

### ME13. Нативный навык точечного редактирования — FIM

**Слияние:** NEW_SUBPROPOSAL → N10-03, N10-05, N10-06, N10-08. **Фаза:** P2_EXISTING_TRAINING_TRIAL.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/fim_dataset_transform.py`.

**Реализация:** Готовить prefix/suffix/middle примеры из разрешённых code/doc источников и обучать восстанавливать только пропущенный участок. Сохранить отдельную долю обычного autoregressive/chat обучения. Для готового FIM checkpoint сначала проверить его существующий формат, не переучивать без причины.

**Допуск:** Поддержанные FIM delimiters/token IDs, exact template и trainable student; group split по проекту/файлу, не по соседним строкам.

**Приёмка:** Applyable edit, unit/AST checks, untouched surrounding context, обычный чат и left-to-right perplexity. Удалённый suffix не становится скрытой подсказкой в тесте.

**Цена:** L для streaming dataset transform; H для training. Узкий student эксперимент; основной сервис не заменяется.

**Почему это не дубль:** FIM отсутствует в каноне. Это навык весов для правок с левым и правым контекстом, не новая кнопка редактора. Источники: [S17].

### ME14. MTP-головы как обучаемая способность, отдельно от декодирования

**Слияние:** AUGMENT_EXISTING → N21-03, N21-10, N06-10, OF29. **Фаза:** R_EXISTING_OF29.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/mtp_head_contract.json`.

**Реализация:** Уточнить существующий OF29: есть ли trained next-token heads в checkpoint, сохранены ли они конвертером, совместим ли verification path. Если heads нет, добавление обучения MTP — отдельный student research trial; имя DSpark не создаёт готовые веса.

**Допуск:** G0 и head/architecture metadata, подтверждённый pinned runtime. Не смешивать MTP, n-gram lookup и отдельный draft как один эффект.

**Приёмка:** Acceptance rate, полное wall time с verification, short/long quality и peak memory. Обещанные чужие множители ускорения не переносятся.

**Цена:** M при уже обученных совместимых heads; H/R при их обучении; дополнительные activations и параметры включаются в цену.

**Почему это не дубль:** MTP/DSpark уже OF29. Только дополняется contract trained-head → conversion → runtime, новая функция не учитывается. Источники: [S11] [S09].

### ME15. Сохранение прежних навыков при изменении весов

**Слияние:** AUGMENT_EXISTING → N10-03, N10-08, OF42, OF43. **Фаза:** P2_EXISTING_TRAINING_TRIAL.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/retention_constraints.json`.

**Реализация:** Расширить существующий replay mixer ограничением на дрейф baseline: проверить текущую квоту replay, добавить old-task anchors и вариант reference KL на фиксированном permitted subset. Сохранять origin model, optimizer/RNG/data cursor; не считать саму запись нового adapter доказательством развития.

**Допуск:** Отдельный закрытый retention set, reference identity, разрешение на данные и воспроизводимый trial. Полные reference logits не сохранять без бюджета; либо ограниченный subset, либо последовательная оценка.

**Приёмка:** Матрица acquired/retained/lost по RU/ES, кодовым задачам, memory behavior и тону; promotion блокируется критической потерей при улучшении одной узкой темы.

**Цена:** L для отчёта; H для training regularization. Reference увеличивает память/compute, поэтому выбирается только по измеренному бюджету.

**Почему это не дубль:** Replay/anti-forgetting уже N10-03/08. Новый вариант контроля в том же trial, не отдельная вечная self-learning петля. Источники: [S05] [S12].

### ME16. Обучаемая нейронная память: ограниченный Titans-прототип

**Слияние:** AUGMENT_EXISTING → N24-01, N24-02, N10-08. **Фаза:** R_ARCHITECTURE_LAB.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/neural_memory_contract.json`.

**Реализация:** Конкретизировать существующий эксперимент: неизменяемый короткий backbone и ограниченный trainable memory module, контрольная fixed-buffer версия, reset/checkpoint/readback, изоляция эпизодов. Измерять update time и забывание после последовательности новых фактов; HOPE остаётся отдельной гипотезой расписания обновления, не вторым готовым модулем.

**Допуск:** Архитектура с доступом к hidden states/обновлению memory parameters, изолированный маленький стенд, разрешённые данные; native GGUF backend сейчас не объявляется поддерживающим test-time gradient updates.

**Приёмка:** Длинное recall против matched-budget baseline, interference/forgetting, replay checkpoint consistency и bounded state bytes; общий S03 не заменяется этим опытом.

**Цена:** H/R. Состояние, gradients/optimizer и update compute реальны. Никакой «бесконечной памяти за несколько килобайт» не обещается.

**Почему это не дубль:** Titans/HOPE уже N24-01/02; добавить измеримый state contract и остановку, не создавать новую карточку под новым названием. Источники: [S18].

### ME17. Латентные шаги мысли с измерением реального compute

**Слияние:** AUGMENT_EXISTING → N24-04, N10-08. **Фаза:** R_ARCHITECTURE_LAB.

**Предлагаемый артефакт:** `/root/nox/proposals/model_evolution/latent_step_trial.json`.

**Реализация:** Детализировать Coconut: фиксированное число скрытых шагов между текстовыми boundary tokens, обучение compatible student и сравнительный режим обычного text reasoning. Представление hidden state подаётся обратно в embedding path только там, где модель этому обучена.

**Допуск:** Рабочий training/inference path hidden states; conversion/native export поддерживает новые операции либо эксперимент остаётся вне production. Это не флаг adaptive reasoning и не выключение reasoning output.

**Приёмка:** Правильность на новых logic/search задачах при равном FLOPs/time budget, latency/peak memory и стабильность выхода в текст; меньше напечатанных токенов не объявляется ускорением.

**Цена:** H/R. Дополнительные скрытые forward steps могут стоить дороже обычного ответа; совместимость текущего GGUF не подтверждена.

**Почему это не дубль:** Coconut уже N24-04. Расширение критериев и execution contract в существующей лабораторной карточке. Источники: [S19].

## Порядок реализации без конкуренции с быстрым чатом

1. **Сейчас — подготовка без вызовов модели:** G0 schema, dedup mapping, маленькие разрешённые corpus/eval manifests, расчёт бюджетов, source/runtime compatibility checks. Не запускать benchmarking из этого документа во время native canary владельца.
2. **После чистого быстрого чата:** ME01 и ME05; сначала доказать фактическое доступное окно и качество текущего quant. Эти результаты определяют, нужна ли вообще растяжка.
3. **При отдельном offline budget:** ME06 → ME07; ME08 только если есть diagnostic support. Один кандидат за раз. Порог качества и memory ceiling фиксируются до прогона; вместе с baseline хранятся конфиг, data SHA и результаты.
4. **При подтверждённой архитектуре и обучаемом source:** выбрать ME02 **или** ME03, при необходимости ME04. Candidate проходит повторно short+long exam и conversion parity. Не менять одновременно scaling, quant и sampling: причина результата иначе теряется.
5. **Учебный контур:** новые objectives ME09–ME13 проходят существующие N10 dataset/trainer/checkpoint gates; ME15 задаёт retention. ME14/ME16/ME17 остаются исследовательскими, пока нет совместимого checkpoint/runtime и положительного баланса качества/стоимости.

Любое продвижение: manifest → отдельный кандидат → reproducible eval → owner-authorized maintenance/admission → canary → promotion либо rollback. Обновление весов не означает перезапись S03; raw советы облачных моделей не становятся автоматически train data. Исходный чат не ждёт экспериментов, шесть descriptors не означают шесть одновременно обучающихся моделей.

## Первичные источники

Ссылки просмотрены 17.11.2026. Публикации подтверждают методы, а не native поддержку конкретного NOX. Собственные схемы, пути, этапы и приёмочные условия выше — инженерные предложения, а не цитаты из статей.

[S01]: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md "GGUF metadata specification"
- **S01** — [GGUF metadata specification](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md).

[S02]: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp server: context and runtime flags"
- **S02** — [llama.cpp server: context and runtime flags](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

[S03]: https://arxiv.org/abs/2309.00071 "YaRN, original paper"
- **S03** — [YaRN, original paper](https://arxiv.org/abs/2309.00071).

[S04]: https://proceedings.mlr.press/v235/ding24i.html "LongRoPE, ICML 2024"
- **S04** — [LongRoPE, ICML 2024](https://proceedings.mlr.press/v235/ding24i.html).

[S05]: https://proceedings.mlr.press/v267/shang25a.html "LongRoPE2, ICML 2025"
- **S05** — [LongRoPE2, ICML 2025](https://proceedings.mlr.press/v267/shang25a.html).

[S06]: https://github.com/microsoft/LongRoPE "Microsoft LongRoPE repository"
- **S06** — [Microsoft LongRoPE repository](https://github.com/microsoft/LongRoPE).

[S07]: https://github.com/NVIDIA/RULER "NVIDIA RULER"
- **S07** — [NVIDIA RULER](https://github.com/NVIDIA/RULER).

[S08]: https://github.com/THUDM/LongBench "LongBench / LongBench v2"
- **S08** — [LongBench / LongBench v2](https://github.com/THUDM/LongBench).

[S09]: https://github.com/ggml-org/llama.cpp/blob/master/tools/imatrix/README.md "llama.cpp importance matrix"
- **S09** — [llama.cpp importance matrix](https://github.com/ggml-org/llama.cpp/blob/master/tools/imatrix/README.md).

[S10]: https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/quantize.cpp "llama.cpp actual quantizer options"
- **S10** — [llama.cpp actual quantizer options](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/quantize.cpp).

[S11]: https://arxiv.org/abs/2412.19437 "DeepSeek-V3: MoE and MTP methods"
- **S11** — [DeepSeek-V3: MoE and MTP methods](https://arxiv.org/abs/2412.19437).

[S12]: https://arxiv.org/abs/2305.17888 "LLM-QAT"
- **S12** — [LLM-QAT](https://arxiv.org/abs/2305.17888).

[S13]: https://arxiv.org/abs/2501.12948 "DeepSeek-R1 technical report"
- **S13** — [DeepSeek-R1 technical report](https://arxiv.org/abs/2501.12948).

[S14]: https://huggingface.co/docs/trl/grpo_trainer "TRL GRPOTrainer"
- **S14** — [TRL GRPOTrainer](https://huggingface.co/docs/trl/grpo_trainer).

[S15]: https://arxiv.org/abs/2311.09677 "R-Tuning"
- **S15** — [R-Tuning](https://arxiv.org/abs/2311.09677).

[S16]: https://arxiv.org/abs/2607.15232 "In-Place Tokenizer Expansion, July 2026"
- **S16** — [In-Place Tokenizer Expansion, July 2026](https://arxiv.org/abs/2607.15232).

[S17]: https://arxiv.org/abs/2207.14255 "Fill-in-the-Middle training"
- **S17** — [Fill-in-the-Middle training](https://arxiv.org/abs/2207.14255).

[S18]: https://arxiv.org/abs/2501.00663 "Titans neural memory"
- **S18** — [Titans neural memory](https://arxiv.org/abs/2501.00663).

[S19]: https://arxiv.org/abs/2412.06769 "Coconut continuous latent reasoning"
- **S19** — [Coconut continuous latent reasoning](https://arxiv.org/abs/2412.06769).
