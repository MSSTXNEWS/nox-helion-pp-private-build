#!/usr/bin/env python3
"""K1: снять компактные ответы модели-учителя на нашем наборе промптов (jsonl), чтобы потом удалить модель. Лицензии: Mistral-Small-3.2 и gpt-oss — Apache-2.0.
Запуск: teacher_dump.py <dir_with_gguf> <name> <max_tokens>. Свой llama-server :8199 на GPU (окно тишины!). rc=0 если >=90% непустых."""
import sys, os, json, glob, time, subprocess, urllib.request, random
from concurrent.futures import ThreadPoolExecutor
d, name, mt = sys.argv[1], sys.argv[2], int(sys.argv[3])
gg = sorted([g for g in glob.glob(d + "/**/*.gguf", recursive=True) if "mmproj" not in g], key=lambda g: -os.path.getsize(g))
print("gguf", gg[:2], flush=True)
P = []
for fn in ("dpo_train.jsonl", "dpo2_train.jsonl", "dpo_eval.jsonl", "dpo2_eval.jsonl"):
    try: fh = open("/workspace/nox/ops/dpo/" + fn, encoding="utf-8")
    except OSError: continue
    for l in fh:
        try: o = json.loads(l)
        except ValueError: continue
        p = o.get("prompt")
        if isinstance(p, list): p = "\n".join(m.get("content", "") for m in p if m.get("role") == "user")
        if isinstance(p, str) and 15 < len(p) < 600 and "claude" not in p.lower(): P.append(p)
random.Random(21).shuffle(P); P = list(dict.fromkeys(P))[:300]
print("prompts", len(P), flush=True)
if not P: sys.exit(3)
srv = subprocess.Popen(["/workspace/nox/bin/llama-server", "--host", "127.0.0.1", "--port", "8199", "-m", gg[0], "-ngl", "99", "-c", "8192", "-np", "4", "--jinja"], stdout=open("/tmp/teacher_%s.log" % name, "w"), stderr=subprocess.STDOUT)
ok = False
for _ in range(150):
    try:
        if urllib.request.urlopen("http://127.0.0.1:8199/health", timeout=3).status == 200: ok = True; break
    except Exception: time.sleep(4)
if not ok: srv.kill(); print("server не поднялся"); sys.exit(2)
def ask(p):
    b = json.dumps({"model": "x", "messages": [{"role": "user", "content": p}], "max_tokens": mt, "temperature": 0.7}).encode()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8199/v1/chat/completions", data=b, headers={"Content-Type": "application/json"}), timeout=300).read())
        return {"prompt": p, "answer": (r["choices"][0]["message"].get("content") or "").strip(), "teacher": name}
    except Exception as e: return {"prompt": p, "answer": "", "teacher": name}
t0 = time.time()
with ThreadPoolExecutor(4) as ex: res = list(ex.map(ask, P))
srv.terminate(); time.sleep(3)
os.makedirs("/workspace/nox/ops/teacher_answers", exist_ok=True)
out = "/workspace/nox/ops/teacher_answers/%s.jsonl" % name
with open(out, "w", encoding="utf-8") as f:
    for r in res:
        if r["answer"]: f.write(json.dumps(r, ensure_ascii=False) + "\n")
n = sum(1 for r in res if r["answer"]); print("answers %d/%d, %.0f с -> %s" % (n, len(P), time.time() - t0, out), flush=True)
sys.exit(0 if n > 0 and n >= 0.9 * len(P) else 1)
