# NOX: совместимость обучения на 2 × V100-SXM2 32 GB

Проверено 16 ноября 2026. Статус: **COMPATIBILITY_CANDIDATE_NOT_NATIVE_TESTED**.

Полный набор из 72 wheel-файлов скачан, хеши сверены с официальными источниками, зависимости и extras проверены для CPython 3.11/Linux x86_64. Контрольный pip download с отключёнными индексами и обязательными хешами завершился с кодом 0. Это подтверждает полноту набора зависимостей, но не работу каждого CUDA-ядра на V100. Установка, импорт скачанного PyTorch, загрузка модели, обучение и создание службы здесь не выполнялись.

Полный lock: **requirements-cp311-linux-cu126.lock**, SHA256 **8484b77f5020abd8e8d62f667845ee5da23684be7b4e738ec8f5833b98f3c362**. Подробные версии и источники: **training_wheelhouse_manifest.json**. Доставка двух комплектов: **drive_delivery_receipt.json**, 52/52 объектов проверены в Drive.

## 1. Что действительно находится в наборе

| Компонент | Проверенная версия | Вывод для первого запуска |
|---|---|---|
| torch / torchvision | 2.14.1+cu126 / 0.29.1+cu126 | Сохранить точные wheel и хеши; не разрешать замену обычным PyPI torch |
| cuda-toolkit / CUDA runtime | 12.6.3 / nvidia-cuda-runtime-cu12 12.6.77 | Профиль CUDA 12.6; свежая проверка драйвера обязательна |
| CUDA NVRTC / cuDNN | 12.6.85 / 9.10.2.21 | Наличие файлов не заменяет запуск требуемых операторов |
| cuda-bindings / nvJitLink | 12.9.10 / 12.9.86 | Это остаётся веткой CUDA 12, но требует проверки ABI/драйвера; не подменять версии наугад |
| bitsandbytes | 0.50.2 | NF4 и FP16 — кандидатный путь; проверить фактически выбранную CUDA-библиотеку |
| Triton | 3.8.0 | Сохранён как зависимость torch; его CUDA-ядра на sm70 не входят в разрешённый начальный путь |
| Transformers / PEFT / TRL / Accelerate | 5.23.0 / 0.21.3 / 1.18.0 / 1.15.0 | Версии зафиксированы; integration/backward smoke ещё не выполнен |

В списке зависимостей нет пакетов CUDA 13 или torch +cu13x. Однако **внутри официального bitsandbytes wheel одновременно присутствуют libbitsandbytes_cuda130.so и cuda132.so**, а также cuda118/121/124/126/128. Поэтому утверждение «в архиве вообще нет бинарников CUDA 13» неверно. Для этого профиля нужна **libbitsandbytes_cuda126.so**. Переменная BNB_CUDA_VERSION не должна быть унаследована со значением 130/132; исходный режим — без override, с выбором по torch.version.cuda. Если override предусмотрен существующим launcher, допустимое значение этого профиля — 126 после проверки пути загрузки.

PyTorch официально указывает, что ветка 2.14 — последняя с готовыми CUDA 12.6 wheel для Volta; CUDA 13 не покрывает sm70. Значение CUDA Version в nvidia-smi не является версией runtime конкретного torch: проверяются отдельно драйвер, torch.version.cuda, архитектуры сборки и реально загруженные библиотеки. [Уведомление PyTorch](https://dev-discuss.pytorch.org/t/notice-cuda-12-6-wheels-will-no-longer-be-published-from-pytorch-2-15-drops-maxwell-pascal-volta/3432), [совместимость CUDA](https://docs.nvidia.com/deploy/cuda-compatibility/latest/minor-version-compatibility.html).

## 2. Явные ограничения ускорений

**Triton 3.8:** официальный проект поддерживает NVIDIA CC8.0+, тогда как V100 — sm70. Успешное разрешение зависимости triton не доказывает выполнение Triton-кода. Первый профиль работает через обычный PyTorch eager: torch.compile, Inductor, Liger и Triton/FLA fast paths отключены. Не удалять Triton из полного lock и не понижать его отдельно: это изменит проверенный dependency profile. [Triton: поддерживаемое оборудование](https://github.com/triton-lang/triton#compatibility).

**bitsandbytes:** NF4/FP4 и 8-bit optimizers заявлены для CC6.0+, а LLM.int8() требует CC7.5+. Поэтому LLM.int8() не является допустимой заменой NF4 на V100. Официальная Linux CUDA 12.6 сборка включает sm70; CUDA 13 сборки начинаются со sm75. [Матрица bitsandbytes](https://huggingface.co/docs/bitsandbytes/installation).

**FlashAttention/FLA/Liger:** пакетов flash-attn, flash-linear-attention, causal-conv1d, liger и xformers в этих 72 wheel нет. Не добавлять их автоматически ради сообщения о доступном ускорении. Первое измерение — attention eager и обычный gated-delta-rule fallback Qwen3.5. Альтернативный SDPA или иной быстрый backend допускается отдельным сравнением после базового smoke.

**Hub kernels:** в скачанном Transformers 5.23.0 проверены integrations/hub_kernels.py и modeling_utils.py: переменная **USE_HUB_KERNELS=NO**, аргумент загрузки **use_kernels=False** и метод **set_use_kernels(False)** существуют. modeling_qwen3_5.py содержит обычные PyTorch реализации и декораторы для возможной замены через hub. Изолированный профиль без дополнительных FLA-пакетов нужен, чтобы существующее глобальное окружение не активировало другой путь. [Исходник Transformers v5.23.0](https://github.com/huggingface/transformers/blob/v5.23.0/src/transformers/integrations/hub_kernels.py).

**Архитектурный флаг не чинит готовый wheel:** TORCH_CUDA_ARCH_LIST=7.0 влияет на соответствующую сборку расширений из исходников; он не добавляет Volta-код в уже собранную CUDA 13 библиотеку. Для начального профиля сборка новых расширений не требуется.

## 3. Кандидатный профиль первого запуска

Это настройки для отдельного задания существующей очереди. Начинать с одной выделенной V100 и текстового QLoRA-кандидата; вторую карту подключать после измерения. Идентификатор GPU берётся из существующей resource lease, а не закрепляется навсегда за новой службой.

Параметры процесса, задаваемые только launcher этого задания:

    USE_HUB_KERNELS=NO
    TOKENIZERS_PARALLELISM=false
    OMP_NUM_THREADS=8
    MKL_NUM_THREADS=8

CUDA_VISIBLE_DEVICES ограничивается выданной картой. Не наследовать BNB_CUDA_VERSION=130/132 или настройки компиляции из другого профиля. Для двух DDP-процессов начальный CPU-бюджет — по 4 потока на rank; dataloader workers — по 1, затем увеличивать по измерению. Наблюдавшаяся CPU quota около 19.2 ядра важнее affinity 80; фактическую quota и cgroup RAM перечитать при admission.

Модель и квантование:

    load_in_4bit = True
    bnb_4bit_quant_type = "nf4"
    bnb_4bit_use_double_quant = True
    bnb_4bit_compute_dtype = torch.float16
    attn_implementation = "eager"
    use_kernels = False
    model.config.use_cache = False

База заморожена; FP32 сохраняется для нужных нормализаций и обучаемых LoRA-параметров. Для Qwen3.5 используется соответствующий архитектуре loader и зафиксированный revision; vision-часть заморожена. До назначения target_modules нужен inventory настоящих линейных модулей языка. Не применять all-linear к multimodal-модели без проверки покрытия.

Начальные параметры обучения:

| Настройка | Значение кандидата |
|---|---|
| fp16 / bf16 / tf32 | True / False / False |
| torch_compile | False |
| torch_compile_backend / torch_compile_mode | None / None |
| use_liger_kernel | False |
| microbatch | 1 на процесс |
| Длина последовательности | 512 токенов для smoke; 1024 после замера пика |
| gradient_accumulation_steps | 8 |
| gradient_checkpointing | True, use_reentrant=False |
| LoRA r / alpha / dropout | 16 / 32 / 0.05 |
| learning rate / weight decay | 5e-5 / 0.01 как проверяемая начальная настройка |
| dataloader workers / pin_memory | 2 / False на одиночной карте для первого измерения |
| Запас VRAM | Не менее 4 GiB измеренного резерва на каждой занятой карте |

В training_args.py версии 5.23.0 проверено, что заданный torch_compile_backend автоматически включает compile. Поэтому одного torch_compile=False недостаточно при восстановлении старого config с заполненным backend: backend и mode должны быть пустыми.

**Оптимизатор:** начальный эталон — AdamW по обучаемым FP32 LoRA-параметрам, без fused/Triton пути. В Trainer это кандидат optim="adamw_torch"; для строго простого эталона передать явный torch.optim.AdamW с fused=False и foreach=False. Не использовать adamw_torch_fused по умолчанию этого профиля.

AdamW8bit либо paged_adamw_8bit — второй измеряемый вариант после успешного эталона. Сравнивать реальную экономию памяти, время шага и качество; paged-вариант способен переносить давление в host RAM. Наличие двух V100 не гарантирует, что offload помещается в cgroup.

## 4. Две карты и существующий trainer 35B

Две V100 по 32 GB при DDP хранят две копии модели; это не единый пул 64 GB. Для DDP нужны один процесс на карту, корректный NCCL smoke и сопоставимые градиенты. NVLink-топология не подтверждена, ускорение от второй карты заранее не обещается. device_map="auto" не является заменой training sharding; FSDP/QLoRA — отдельный профиль после одиночной проверки.

Существующий trainer 35B **не переименовывать** и не считать новым Qwen- или DeepSeek-trainer. Его base revision, tokenizer, dataset, adapter lineage и optimizer checkpoint сохраняют прежнюю идентичность. Новый студент получает отдельный job/profile в той же очереди. Адаптер 35B другой архитектуры не переносится слиянием в Qwen9B или DeepSeek.

Этот набор зависимостей не закрывает прямую LoRA полной DeepSeek-V4.1 в Maya GGUF. Поддержка training implementation, формата базы, backward и обратной загрузки адаптера в inference остаётся отдельной задачей.

## 5. Приоритет чата: checkpoint, освобождение ресурсов, возврат

Используется **единственная существующая очередь NOX** и её STOP/admission/leases. Новая служба или второй scheduler не нужны. Сорок логических задач и шесть исполнителей не означают сорок загруженных моделей.

При запросе чата trainer доходит до контролируемой границы optimizer step, сохраняет adapter, optimizer, scheduler, AMP scaler, RNG, step и позицию данных. Checkpoint публикуется атомарно после проверки файлов и доступного места. Базовые HF-веса не дублируются в каждом сохранении.

Затем trainer освобождает CUDA context и host allocations; надёжная граница — корректное завершение его рабочего процесса. **SIGSTOP не освобождает VRAM или RAM.** Одного empty_cache тоже недостаточно для живых тензоров. Очередь возвращает GPU/RAM lease чату только после фактического исчезновения процесса/контекста и измерения освобождённой памяти. При невозможности безопасно сохранить состояние фиксируется конкретный HOLD, а не ложное состояние «приостановлено и память свободна».

Повторный admission проверяет ресурсы заново и восстанавливает подтверждённый checkpoint той же lineage. Tmpfs, page cache, pinned buffers и источник весов учитываются в cgroup; нельзя считать их дополнительной бесплатной памятью. Правила existing STOP/hash/reserve/identity gates сохраняются.

## 6. Нужные smoke-проверки до длительного обучения

1. **Среда и карта:** CPython 3.11, glibc не ниже требуемого manylinux 2.28, точные torch 2.14.1+cu126 и torchvision 0.29.1+cu126, torch.version.cuda=12.6, device capability=(7,0), sm_70 в архитектурах сборки. Зафиксировать driver, пути CUDA-библиотек, cgroup limit/current и свободное место. Не выводить совместимость только из nvidia-smi.
2. **Реальные CUDA-операторы:** небольшой FP16 matmul и backward; NF4 quantize/dequantize и backward через фактически выбранный libbitsandbytes_cuda126.so. Ошибки no kernel image/invalid device function/symbol lookup блокируют дальнейшие шаги.
3. **Полный путь модели:** короткий forward/backward реальной выбранной базы, LoRA только в утверждённых модулях языка, vision и база заморожены. Доказать использование eager/PyTorch fallback и отсутствие Triton/FLA/Hub kernel подмены. Замерить пик allocated/reserved VRAM, cgroup RAM и время шага.
4. **Пять выполненных обновлений:** конечные loss/градиенты, изменившиеся adapter tensors и их SHA, фактические optimizer steps. Пропущенный AMP update нельзя засчитать по одному глобальному счётчику Trainer. При NaN/Inf или систематических пропусках продолжение запрещено до разбора.
5. **Сохранение и resume:** повторная загрузка adapter/optimizer/scaler/RNG с той же базой и проверка контрольного результата в заданной численной погрешности. Проверить прекращение trainer, освобождение VRAM, возвращение чата через существующую очередь и следующий реальный шаг после resume.
6. **Только затем вторая карта:** отдельный NCCL all-reduce и multi-rank backward smoke, проверка шагов обоих ranks, завершения всех процессов и освобождения обеих карт. Сравнить throughput с одной картой; не включать DDP только потому, что видны два GPU.

Пока эти проверки не выполнены на NOX, корректный статус — **зависимости и поставка проверены; нативное выполнение и обучение ожидают приёмки**. Файлы профиля сами по себе не являются квитанцией успешного optimizer step.

