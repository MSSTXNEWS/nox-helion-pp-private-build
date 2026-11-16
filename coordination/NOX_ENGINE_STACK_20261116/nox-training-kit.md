# NOX: профиль обучения и дистилляции v0.1

Проверено 16 ноября 2026 года. Статус: подготовка по первичным источникам; пакеты и веса не устанавливались, обучение и слияние не выполнялись. Совместимость зависимостей проверена по опубликованным метаданным, совместимость исполнения на сервере ещё требует отдельной проверки.

## Решение

**Основная модель остаётся целевой DeepSeek-V4.1-Flash-1017.** Maya обслуживает её квантизованные веса для диалога и генерации обучающих примеров. Отдельный Qwen3.5-9B становится первым кандидатом в обучаемые помощники. Дистилляция передаёт проверяемые навыки через данные; её результат не заменяет DeepSeek автоматически и не означает переноса всех возможностей учителя.

Рабочая последовательность: DeepSeek генерирует задачи и ответы → ответы проверяются → сохраняется размеченный датасет → учитель освобождает вычислительные ресурсы в согласованном окне → студент обучается QLoRA → независимая оценка → только прошедший оценку адаптер допускается к использованию. Одновременная загрузка полного учителя и тренера не является исходной конфигурацией.

## 1. Движки уже скачаны

| Источник | Зафиксированная версия | Локальный путь | Архив |
|---|---|---|---|
| [christ-pher/bnk](https://github.com/christ-pher/bnk/tree/68fa9f3be8501973d05e8f6cc1c387e15f432f66) | master, `68fa9f3be8501973d05e8f6cc1c387e15f432f66` | `/workspace/scratch/f9bc2028661c/nox-inference-sources/bnk` | `bnk-68fa9f3be850.tar.gz`, 1,727,750 байт |
| [mw00/project-maya](https://github.com/mw00/project-maya/tree/c81fab6c9d63cf69b928f92460e0a662b28aa9ec) | main, v1.1.65, `c81fab6c9d63cf69b928f92460e0a662b28aa9ec` | `/workspace/scratch/f9bc2028661c/nox-inference-sources/maya` | `maya-c81fab6c9d63.tar.gz`, 24,776,818 байт |

Оба клона shallow и чистые. AGENTS.md в них не найден. SHA256 и ограничения записаны в соседнем `source-manifest.json`. Репозитории не запускались. Maya содержит небольшой синтетический GGUF для тестов, включённый автором в Git; внешние обученные веса не скачивались.

Приоритет подготовки — **Maya**. В её `tools/ds4/pack_gguf.py` есть IQ1_M, перевод новой структуры `per_layer_token_embd.weight` в слои и поддержка старого Engram sidecar. Документация показывает V100 с Maya-S/XS, а GSQ-RCO IQ2_XXS — отдельно на AMD. Это ещё не подтверждает выбранную квантизацию на NOX. У bnk `docs/DEEPSEEK-NEXT.md` прямо описывает невозможность загрузить IQ2_XXS из-за IQ1_M; shipped config использует старые четыре backbone shard и отдельный Engram.

## 2. Зафиксированный стек для Linux x86_64 и V100

| Компонент | Профиль v0.1 | Причина |
|---|---|---|
| Python | 3.11.x, точный patch фиксируется при создании окружения | Transformers 5.23 и TRL 1.18 требуют Python ≥3.11 |
| PyTorch | **2.14.1, строго wheel cu126** | Последняя ветка готовых CUDA 12.6 wheel с Volta; обычный PyPI wheel этой версии использует CUDA 13 |
| torchvision | 0.29.1/cu126, если нужен загрузчику multimodal-класса | Официальная парная версия PyTorch |
| Transformers | 5.23.0 | Есть реализация Qwen3.5 и dense Qwen3.8, использующего тот же model_type |
| PEFT | 0.21.3 | Адаптеры и подготовка k-bit модели |
| TRL | 1.18.0 | SFT на проверенных офлайн ответах учителя |
| Accelerate | 1.15.0 | Запуск и корректное размещение; многокарточный режим после одиночного smoke test |
| bitsandbytes | 0.50.2 | NF4/FP4 поддерживает CC6.0+, CUDA12.6 Linux wheel включает sm70 |
| datasets / safetensors | 5.2.0 / 0.8.0 | Данные и безопасный формат весов |

Это **кандидатный набор**, а не результат проверенного совместного запуска. Требования опубликованных пакетов друг другу не противоречат: TRL требует torch≥2.6, Transformers≥4.56.2 и Accelerate≥1.11; bitsandbytes требует torch≥2.4,<3. После разрешения зависимостей нужен полный lock с хешами. Не изменять существующее рабочее окружение NOX; использовать отдельное окружение и не позволять resolver заменить cu126 на CUDA13.

V100 — compute capability 7.0. Профиль использует **FP16 для вычислений, FP32 для необходимых состояний/нормализаций и LoRA-параметров**, `bf16=False`, `tf32=False`. BF16 Tensor Cores требуют CC8.0+, а не V100. `LLM.int8()` bitsandbytes требует CC7.5+ и здесь не является заменой NF4. Для первой проверки не включать FlashAttention2, Triton/FLA kernels, torch.compile или ускорения, требующие более новой архитектуры. В Qwen3.5 v5.23.0 есть обычный PyTorch fallback для gated-delta-rule; его фактическую скорость и обратный проход необходимо проверить.

Первичные источники: [PyTorch 2.14.1/cu126](https://pytorch.org/get-started/previous-versions/), [удаление cu126 с 2.15](https://dev-discuss.pytorch.org/t/notice-cuda-12-6-wheels-will-no-longer-be-published-from-pytorch-2-15-drops-maxwell-pascal-volta/3432), [V100 CC7.0](https://developer.nvidia.com/cuda/gpus/legacy), [CUDA: alternate floating point CC8.0+](https://docs.nvidia.com/cuda/archive/12.6.0/cuda-c-programming-guide/index.html#alternate-floating-point), [bitsandbytes hardware matrix](https://huggingface.co/docs/bitsandbytes/main/installation). Метаданные версий: [Transformers](https://pypi.org/project/transformers/5.23.0/), [PEFT](https://pypi.org/project/peft/0.21.3/), [TRL](https://pypi.org/project/trl/1.18.0/), [Accelerate](https://pypi.org/project/accelerate/1.15.0/), [bitsandbytes](https://pypi.org/project/bitsandbytes/0.50.2/).

## 3. Какие полные веса нужны студенту

| Роль | Репозиторий и revision | Формат и примерный объём тензоров | Решение |
|---|---|---|---|
| Первый обучаемый помощник | [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a), `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | HF safetensors, 9.653B параметров; ≈19.31 GB исходных тензоров | NF4 QLoRA; один V100 первым, второй после измерений |
| Более крупный помощник | [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B/tree/37561816e66b5b9153b1b64c10968c18c1e6f4a0), `37561816e66b5b9153b1b64c10968c18c1e6f4a0` | HF BF16, 27.781B; ≈55.56 GB исходных тензоров | Второй этап; сначала короткий 256–512-token backward test, без обещания вместимости |
| Консервативный 7B резерв для узких задач | [Qwen/Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/tree/a09a35458c702b33eeacc393d103063234e8bc28), `a09a35458c702b33eeacc393d103063234e8bc28` | HF BF16, 7.616B; ≈15.23 GB | Зрелая обычная attention-архитектура; не новый основной интеллект |

Все три карточки указывают Apache-2.0. Объёмы — расчёт количества тензоров по HF API, без tokenizer/config/метаданных и служебных файлов. Это не пиковая RAM/VRAM. При 15 GB свободного SSD даже 9B исходные веса не помещаются с рабочим запасом. Нужны выбранное хранилище и измеренный cache budget. Две V100 по 32 GB при DDP хранят две копии; память не превращается автоматически в единый пул 64 GB.

Qwen3.5-9B и Qwen3.8-27B имеют `Qwen3_5ForConditionalGeneration`, `model_type=qwen3_5`, dense MLP и гибрид linear/full attention. Для текстового обучения используется корректный multimodal loader с замороженной vision-частью либо проверенная text-only загрузка с точным сопоставлением ключей. Не переименовывать архитектуру вручную. [Официальный config 9B](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/config.json), [config 27B](https://huggingface.co/Qwen/Qwen3.8-27B/blob/37561816e66b5b9153b1b64c10968c18c1e6f4a0/config.json), [реализация Transformers v5.23.0](https://github.com/huggingface/transformers/blob/v5.23.0/src/transformers/models/qwen3_5/modeling_qwen3_5.py).

## 4. Начальный QLoRA профиль 9B

NF4 4-bit, double quantization, compute dtype FP16; базовые веса заморожены. LoRA `r=16`, `alpha=32`, dropout 0.05; microbatch 1; 512 токенов для пяти проверочных optimizer steps, затем 1024 только после замера пика. Gradient accumulation 8, gradient checkpointing, `use_cache=False`; AdamW по FP32 LoRA-параметрам, начальный learning rate 5e-5 как проверяемая настройка, не утверждённый оптимум. Mixed precision использует loss scaling; любое NaN/Inf или постоянно пропускаемые optimizer steps блокируют продолжение.

Выбирать реальные линейные модули **только текстовой части**: attention `q_proj/k_proj/v_proj/o_proj`, dense MLP `gate_proj/up_proj/down_proj`, и после отдельного покрытия градиентов linear-attention `in_proj_qkv/in_proj_z/in_proj_b/in_proj_a/out_proj`. Полные имена и классы фиксировать из загруженной модели. Сначала проверить ограниченный набор; не предполагать, что `all-linear` означает только язык, и не затрагивать автоматически vision, embeddings или lm_head. Для неизвестных 3D/MoE параметров остановиться на проверке сопоставления; универсальная ручная tensor-surgery недопустима.

Одна карта является стартовым режимом. Оставлять минимум 4 GiB измеренного запаса на каждой занятой карте, ограничить память процесса и размер сохранений. Если 27B не проходит одиночный тест, FSDP/QLoRA — отдельный измеряемый профиль; `device_map=auto` не заменяет корректный distributed training. [PEFT quantization](https://huggingface.co/docs/peft/en/developer_guides/quantization), [PEFT LoRA и target_parameters](https://huggingface.co/docs/peft/v0.21.0/package_reference/lora).

## 5. Почему прямой DeepSeek LoRA пока отдельная задача

Официальный [DeepSeek config](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017/blob/08c8657f02291e11b6f6b63e0e16014f8e748518/config.json) задаёт `DeepseekV41ForCausalLM`, `deepseek_v41`, FP8 с packed-FP4 experts, 384 routed experts и большие Engram-таблицы. В опубликованном [modeling_auto.py v5.23.0](https://github.com/huggingface/transformers/blob/v5.23.0/src/transformers/models/auto/modeling_auto.py) есть DeepSeek-V4, но нет V4.1; [issue интеграции #48755](https://github.com/huggingface/transformers/issues/48755) открыт. Автоматический пример AutoModel на HF не доказывает рабочего загрузчика или обучения.

Квантизованный GGUF для Maya — артефакт вывода. У нас нет подтверждённого пути, который обучает выбранный GSQ-RCO DeepSeek GGUF напрямую через этот PEFT стек с сохранением его маленького размера. Импорт GGUF может деквантизовать тензоры; поддержка архитектуры и обратного прохода должна быть отдельной. [Документация GGUF](https://huggingface.co/docs/transformers/en/quantization/gguf).

Прямая адаптация требует доказанного DeepSeek-V4.1 training implementation, совместимой загрузки FP4/FP8, корректного состояния CSA2/Engram при checkpointing, LoRA target mapping и поддержки этих адаптеров движком вывода. Даже обучение только адаптеров требует хранения/чтения всей базы и backward activations; число активных экспертов не равно объёму всей модели. Не обещать такую тренировку на 2×V100 до замеров. Старые 7B/35B адаптеры не подходят DeepSeek; их полезные навыки можно переносить через проверенные примеры.

**Экспериментальный путь уже существует.** Через GitHub API проверены merged [Unsloth PR17625](https://github.com/unslothai/unsloth/pull/17625) (head `162c7dc3325494bef180576d1604a35ec9e95c0f`) и merged [unsloth-zoo PR2483](https://github.com/unslothai/unsloth-zoo/pull/2483) (head `bcd14da25a1a3252e559aced29ab113f58e77037`). Они работают с community Transformers port `malaiwah/transformers@add-deepseek-v41`, проверенный head `62d7ebd7de4938e072b7aaeb881593b79dc56835`; upstream [PR48721](https://github.com/huggingface/transformers/pull/48721) закрыт без слияния. Это отдельный стек, его нельзя молча смешивать со стабильным стеком студента выше.

Авторы тренировочного пути показали 10 шагов LoRA/QLoRA на **tiny 79 MB модели с конфигурацией семейства**, на Colab L4: 65 из 65 адаптеров получили градиенты и изменились. Их собственные ограничения: реальные released FP4/FP8 веса, multi-GPU и merge/save round-trip не покрыты. Исправления касаются checkpointing общего состояния CSA2, градиентов fake quantization, grouped `o_a_proj`, применения LoRA в compressor и выбора Engram `wkv`; padding-free packing запрещён, compile отключён из-за recompute mismatch. Тестовая модель подтверждает работоспособность механизма, но не вместимость или качество обучения полной 1017 на V100.

## 6. Данные и доказательства результата

Генерация учителем — офлайн SFT-дистилляция по выходному тексту, без требования одинаковых tokenizer и без необходимости держать обе модели в VRAM. Набор включает русский и испанский диалог, логические задачи с проверяемым ответом, программирование с тестами, tool calls с проверяемой схемой и честное описание ошибок/неизвестного состояния. В каждой записи: источник, версия учителя/квантизации, prompt/ответ, критерий проверки и результат. Непроверенные самоутверждения учителя не превращать в метки правильности. Примеры и семейства задач дедуплицировать; held-out выделять до тренировки, включая перефразировки и близкие задачи. [Первичный пример дистилляции между семействами](https://github.com/deepseek-ai/DeepSeek-R1), [TRL distillation](https://huggingface.co/docs/trl/en/gkd_trainer).

Минимальная квитанция успешного обучения:

1. Свежие GPU/driver/CUDA/SM, cgroup/RAM, SSD и VRAM измерения; точный lock, base revision, tokenizer/config/tensor hashes, dataset и split hashes.
2. Не менее пяти **действительно выполненных** optimizer steps: конечные loss/градиенты, изменившиеся значения и SHA адаптера, step counter; warmup/скipped AMP step не считать обновлением.
3. Сохранение и повторная загрузка адаптера; воспроизводимость контрольного ответа/логитов в установленной численной погрешности.
4. До/после — одинаковые held-out задачи, seed, decoding, max tokens и rubric. Отдельно RU, ES, reasoning, code tests, tool validity и отсутствие выдуманных выполненных действий; показаны регрессии и затраты.
5. Кандидат принимается только по заранее заданным требованиям, с сохранённой прежней моделью. Изменившийся tensor hash доказывает обновление весов, но сам по себе не доказывает улучшение качества.

Слияние — только нового адаптера с той же базой/revision и проверенными размерами; затем отдельная квантизация и повторная оценка. Оно не добавляет параметры других архитектур и не делает «сумму интеллектов». Полное дообучение всех параметров и обучение с нуля в этот профиль не входят. [PEFT checkpoint lineage](https://huggingface.co/docs/peft/en/developer_guides/checkpoint), [PEFT merge](https://huggingface.co/docs/peft/en/developer_guides/model_merging).
