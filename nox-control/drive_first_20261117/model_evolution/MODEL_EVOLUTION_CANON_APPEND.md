## Прокачка самой модели: контекст, точность весов и обучение

**Дополнение 17.11.2026; предложения, не установленные функции.** Дедупликация полного локального канона и текущего JSON-плана дала 17 конкретных уточнений: 9 новых подпредложений и 8 дополнений существующих. Исходные 240 карточек остаются; ME-ID не являются native TaskID, все назначения требуют mapping_needed. Полная карта: `MODEL_EVOLUTION_DEDUP_MAPPING.json`.

Сначала расширить **N21-10** паспортом architecture/tokenizer/GGUF/RoPE/tensor types и фактического per-sequence context. Нельзя выводить поддержку растяжки из названия DeepSeek-V4.1 или одного флага ctx-size. Для любого окна сохраняются бюджет ответа, measured KV/scratch, качество коротких задач и chat-first admission. Drive хранит холодные веса; KV, активации и рабочие тензоры требуют реальной RAM/VRAM. Текущий Engram/chat/core защищены.

| Направление | Конкретное дополнение | Слияние |
|---|---|---|
| Контекст | ME01: реальные ступени допустимого per-sequence окна, memory ledger, запрет скрытой truncation | Новое подпредложение к N21-01/10 |
| Позиции | ME02: YaRN; ME03: LongRoPE/LongRoPE2 с short-context retention; выбирать альтернативу после architecture/converter/runtime gate | Новые альтернативные подпредложения к N21-10/N10-08; не суммировать |
| Навык длинного чтения | ME04: long/short curriculum и отдельные LM/SFT loss masks; ME05: effective context exam по длине/позиции | Дополнить N10-03/05/06/08 и N06-10 |
| Качество IQ2 | ME06: imatrix RU/ES/code; ME07: чувствительные тензоры и 2–3 quant quality profiles; ME08: router/rare-expert fidelity | Новые подпредложения; weight fidelity отличается от KV/expert cache |
| Обучение качества | ME09: quant-aware recovery; ME10: RLVR с детерминированным reward; ME11: epistemic known/unknown training | ME10 новое; остальные дополняют N10/N06-07 и существующую дистилляцию |
| Представление языка и правок | ME12: tokenizer expansion только с совместимыми новыми embeddings/head и обучением; ME13: FIM prefix/suffix/middle skill | Новые student experiments, не замена tokenizer файла live |
| Уже известные идеи | ME14: trained MTP-head contract; ME15: replay/retention; ME16: bounded Titans memory; ME17: latent Coconut | Дополнить OF29, N10-03/08, N24-01/02/04; новых дублей не создавать |

**Очередность:** паспорт/данные → текущий context/quality exam → offline quant candidates → одна совместимая RoPE-ветвь → отдельный student training. Полные веса IQ2 нельзя «улучшить до F16» простым приведением типа. Новое квантование требует original high-precision source; изменение словаря, MTP, neural memory и latent steps требует настоящей model/runtime compatibility. Ни 128K/2M контекст, ни ускорение от статей для данного host не обещаются.

Adaptive reasoning, prefix/slot cache, KV, RAG, LoRA и DPO уже учтены существующим каноном. Полные prerequisites, proposed artifact paths, tests и ресурсные условия каждой идеи приведены в `MODEL_EVOLUTION_DEDUP.md`. Первичные опоры: [YaRN](https://arxiv.org/abs/2309.00071), [LongRoPE2](https://proceedings.mlr.press/v267/shang25a.html), [llama.cpp quantizer](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/quantize.cpp), [imatrix](https://github.com/ggml-org/llama.cpp/blob/master/tools/imatrix/README.md), [RULER](https://github.com/NVIDIA/RULER), [LLM-QAT](https://arxiv.org/abs/2305.17888), [FIM](https://arxiv.org/abs/2207.14255), [tokenizer expansion](https://arxiv.org/abs/2607.15232).
