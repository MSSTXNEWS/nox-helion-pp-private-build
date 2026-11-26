#!/usr/bin/env python3
"""K1 26.11: расширенные ворота (160 кейсов, ext_cases) для списка адаптеров. Запуск: ext_eval.py <adapter_dir>...  (первый — база сравнения). Жадная генерация."""
import sys, os, json, time
sys.path[:0] = ["/workspace/nox/ops", "/workspace/nox/distill_v2/code", "/workspace/nox/brain/SLP", "/workspace/nox/ops/dpo"]
import unsloth
import torch, distill_v2 as dv, liska_gates as G, fidelity_test as FT, ext_cases as EC
dirs = sys.argv[1:]; log = lambda s: print(time.strftime("%T"), s, flush=True)
persona = open("/workspace/nox/state/native_gate_persona_v1.txt", encoding="utf-8").read()
m, tok = dv.load_model("/workspace/nox/models/student/Qwen/Qwen3.6-35B-A3B", "unsloth", torch)
im_id = tok(dv.IM_END, add_special_tokens=False)["input_ids"][0]
fmt = lambda msgs: dv.chatml(msgs) + dv.THINK
P = G.policy(); G._inference_mode(m, log); gen = G.Gen(m, tok, im_id, fmt, P, log)
cases = EC.ext_cases(); sysm = [{"role": "system", "content": persona}]; out = {}
for d in dirs:
    G.load_adapter(m, d); gen.reset()
    def fid(chat): return {c["id"]: chat(sysm + [{"role": "user", "content": c["prompt"]}]) for c in cases}
    ans = G.drive(fid, gen, time.time() + 3600)
    rep = FT.score(cases, ans); out[os.path.basename(d)] = {"score": rep["score"], "by_cat": rep["by_cat"], "n": rep["n"]}
    log("ext %s: %s %s" % (os.path.basename(d), rep["score"], rep["by_cat"]))
json.dump(out, open("/workspace/nox/ops/dpo/ext_eval.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(out, ensure_ascii=False))
