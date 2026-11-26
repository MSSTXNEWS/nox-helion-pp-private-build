#!/usr/bin/env python3
"""NOX gates-only (SRV K1 26.11): прогнать ворота верности/души/MIND-BENCH/живости на произвольном адаптере БЕЗ обучения.
Использует ops/liska_gates.py как есть (report_for/decide/alive_gate) и загрузчик distill_v2.load_model; distill_v2.py не изменён.
Запуск: venv/bin/python -I gates_only.py <cand_dir> [base_dir]   (GPU свободен от train!). Выход: ops/dpo/gates_<sha16>.json + отчёты ворот в distill_v2/gates/."""
import sys, os, json, time, hashlib
sys.path[:0] = ["/workspace/nox/ops", "/workspace/nox/distill_v2/code"]
import unsloth  # до transformers/peft
import torch
import distill_v2 as dv
import liska_gates as G
cand = sys.argv[1]; base = sys.argv[2] if len(sys.argv) > 2 else "/workspace/nox/distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724"
MODEL = "/workspace/nox/models/student/Qwen/Qwen3.6-35B-A3B"
log = lambda s: print(time.strftime("%T"), s, flush=True)
persona = dv.NOX_PERSONA
try:
    fp = open("/workspace/nox/state/native_gate_persona_v1.txt", "rb").read()
    if hashlib.sha256(fp).hexdigest() == "e221f1d3e67752ac5dd0b477866a3f5ee65940d63d837a783cd552ccc26c76f5": persona = fp.decode("utf-8")
    else: log("персона ворот: хэш не совпал, беру NOX_PERSONA")
except OSError: log("персона ворот: файла нет, беру NOX_PERSONA")
m, tok = dv.load_model(MODEL, "unsloth", torch)
im_id = tok(dv.IM_END, add_special_tokens=False)["input_ids"][0]
fmt = lambda msgs: dv.chatml(msgs) + dv.THINK
P = G.policy(); G._inference_mode(m, log)
gen = G.Gen(m, tok, im_id, fmt, P, log); deadline = time.time() + 60 * P["max_minutes"]
brep, _ = G.report_for(m, gen, base, persona, P, deadline, log, "база")
crep, hc = G.report_for(m, gen, cand, persona, P, deadline, log, "кандидат")
dec = G.decide(crep, brep, P)
ag = G.alive_gate(crep, brep, log); dec["alive"] = ag
if not ag.get("ok", True): dec["pass"] = False; dec["reasons"] = list(dec.get("reasons", [])) + ["живость (AL): " + x for x in ag.get("reasons", [])]
dec.update({"cand": cand, "base": base, "cand_sha16": hc, "t": time.strftime("%FT%TZ", time.gmtime())})
out = "/workspace/nox/ops/dpo/gates_%s.json" % hc
json.dump(dec, open(out, "w"), ensure_ascii=False, indent=1)
log("ворота DPO: %s — %s" % ("ПРИНЯТ" if dec["pass"] else "НЕ принят", "; ".join(dec.get("reasons", []))[:600] or "все пройдены")); print(out)
