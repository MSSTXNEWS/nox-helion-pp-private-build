#!/usr/bin/env python3
"""K1: 4-bit учебная база (bnb NF4) из полной bf16: загрузить load_in_4bit, сохранить save_pretrained, перезагрузить, сверить argmax, 5 шагов LoRA-обучения.
Исходник НЕ меняется и не удаляется. Откат: rm -rf <DST>. rc=0 только если все проверки прошли."""
import sys, os, json, time
import unsloth
from unsloth import FastLanguageModel
import torch
SRC = "/workspace/nox/models/student/Qwen/Qwen3.6-35B-A3B"; DST = "/workspace/nox/models/student/Qwen3.6-35B-A3B-bnb4"
PR = ["Столица Франции — это", "Сколько будет 12 умножить на 12? Ответ:", "Напиши одно предложение про кота."]
def top(m, tok):
    out = []
    for p in PR:
        ids = tok(p, return_tensors="pt").to("cuda")
        with torch.no_grad(): lg = m(**ids).logits[0, -1].float()
        out.append(lg.topk(5).indices.tolist())
    return out
m, tok = FastLanguageModel.from_pretrained(SRC, max_seq_length=1024, load_in_4bit=True, dtype=torch.float16)
tk = getattr(tok, "tokenizer", tok); a = top(m, tk); print("src top5", a, flush=True)
os.makedirs(DST, exist_ok=True); m.save_pretrained(DST); tk.save_pretrained(DST)
sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DST) for f in fs); print("saved %.1f ГБ" % (sz / 1e9), flush=True)
del m; torch.cuda.empty_cache()
m, tok = FastLanguageModel.from_pretrained(DST, max_seq_length=1024, load_in_4bit=True, dtype=torch.float16)
tk = getattr(tok, "tokenizer", tok); b = top(m, tk); print("dst top5", b, flush=True)
same = sum(x[0] == y[0] for x, y in zip(a, b)); print("argmax совпал %d/%d" % (same, len(PR)), flush=True)
m = FastLanguageModel.get_peft_model(m, r=8, lora_alpha=16, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], use_gradient_checkpointing=True)
opt = torch.optim.AdamW([p for p in m.parameters() if p.requires_grad], lr=1e-5); m.train(); losses = []
for i in range(5):
    ids = tk("Привет! Меня зовут NOX HELION, я помогаю мессиру.", return_tensors="pt").to("cuda")
    out = m(**ids, labels=ids["input_ids"]); out.loss.backward(); opt.step(); opt.zero_grad(); losses.append(float(out.loss))
print("5 шагов loss", [round(x, 3) for x in losses], flush=True)
ok = same == len(PR) and all(x == x for x in losses)
json.dump({"ok": ok, "gb": round(sz / 1e9, 1), "argmax_same": same, "losses": losses, "t": time.strftime("%FT%TZ", time.gmtime())}, open(DST + "/bnb4_check.json", "w"))
sys.exit(0 if ok else 1)
