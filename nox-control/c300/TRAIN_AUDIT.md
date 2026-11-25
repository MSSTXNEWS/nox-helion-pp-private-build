# TRAIN_AUDIT K1 (P2), 2026-11-25 17:10 UTC
Источник: p2_train_audit.sh, p2_train_code.sh (только чтение). Секреты не печатались.

## Что идёт сейчас
- Раунд r028, autotrain.sh -> `distill_v2.py train --steps 400 --ckpt-every 25 --lr 5e-5` (pid 1984162, 3 ч в работе), сторож ckpt_guard.py.
- Студент Qwen3.6-35B-A3B (MoE), QLoRA NF4, fp16 (Turing, bf16 нет), LoRA r=8 alpha=16, Unsloth FastLanguageModel (fallback: peft + bnb NF4 compute fp16), gradient checkpointing включён, GradScaler (fp16 loss scaling) включён, torch.autocast fp16, PagedAdamW8bit (fallback AdamW), max_len 2048 (768 при OOM-автопочинке), tok_budget 4096, бакетинг по длине, replay и готовые логиты учителя (selfkd/precomp), холдаут-оценка каждые ckpt_every.
- Версии: torch 2.14.1+cu130, transformers 5.17.0, peft 0.21.3, unsloth 2026.11.9, trl 1.14.2, bitsandbytes 0.50.2, accelerate 1.15.0, xformers 0.0.36 (не загружается с этим torch, Unsloth откатывается на PyTorch SDPA), liger_kernel не установлен (в истории кода есть bak_liska_liger), flash-attn нет (Turing sm_75, и не нужен). GPU capability 7.5.

## Скорость (из train.log r028)
| Метрика | Значение |
|---|---|
| с/шаг | 24.6 - 27.1 (среднее ~25.7), 25 шагов = ~10.7 мин |
| строк/мин | 23 - 38 |
| профиль шага | data 0%, teacher 19-20%, forward 26%, loss 0-1%, backward 53-54%, optimizer 1% |
| holdout-оценка | 95-106 с на каждые 25 шагов (~15% времени интервала); один выброс 983 с (16:49, в 10 раз выше нормы) |
| GPU (dmon 30 с) | SM 67-92%, среднее ~82%; mem-bw 46-71%; простоев нет |
| VRAM | 34.1 / 49.2 ГБ = 69% (из них тренер 26.6 ГБ); до потолка 92% (45.2 ГБ) остаётся ~11 ГБ |
| Загрузка данных | 0% шага: dataloader не узкое место, workers/pin_memory ничего не дадут |

## Выводы
1. Обучение упирается в GPU (SM ~82%) и в backward (54%). Оставшийся запас по GPU ~15-18%; он теряется на: (a) holdout каждые 25 шагов ~15% времени, (b) CPU-конкуренцию (load 32 на 32 ядрах, выброс holdout 983 с совпал с перегрузом), (c) teacher-часть 19%.
2. Основные меры (fp16+scaler, SDPA, 8-bit paged AdamW, предтокенизация/кэш логитов учителя, бакетинг, replay, grad checkpointing) УЖЕ внедрены предыдущими исполнителями.
3. A/B-тесты 100-200 шагов на K1 сейчас невозможны безопасно: второй процесс обучения (~26 ГБ) к 34 ГБ превысит 92% VRAM и ударит по чату. Тесты делаются только в окно между раундами (autotrain busy() = false) по согласованию с арбитром O.
4. Что можно менять БЕЗ кода: state/speed.json ключ `ckpt_every` (код его читает на старте, п.5 LISKA_ADVICE), при следующем перезапуске раунда.
