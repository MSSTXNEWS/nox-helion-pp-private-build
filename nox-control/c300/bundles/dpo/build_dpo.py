#!/usr/bin/env python3
"""NOX DPO build (SRV K1 26.11). Пары chosen/rejected для персоны/анти-угодничества.
Источники: DataCreatorAI/Anti-Sycophancy-DPO (apache-2.0, готовые chosen/rejected, HF datasets-server)
         + персона-строки rows_train.jsonl (chosen = наш ответ; rejected = генерика донора, опц. --persona-gen N).
Фильтры: P3_FILTER (Claude/Anthropic вне), утечка промптов теста верности (state/p3/eval/cases.jsonl), длина, дедуп.
Выход: ops/dpo/dpo_train.jsonl, dpo_eval.jsonl (формат TRL conversational: prompt/chosen/rejected)."""
import argparse, json, os, re, random, time, urllib.request, urllib.parse
W = "/workspace/nox"
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=W + "/ops/dpo")
ap.add_argument("--max-chars", type=int, default=1800)
ap.add_argument("--persona-gen", type=int, default=0, help="сколько персона-пар сгенерировать донором :8104 (только в окно тишины)")
ap.add_argument("--donor", default="http://127.0.0.1:8104")
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
nk = lambda s: re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()
BAD = re.compile(r"claude|anthropic", re.I)
cases = [nk(json.loads(l).get("prompt", "")) for l in open(W + "/state/p3/eval/cases.jsonl", encoding="utf-8") if l.strip()]
def leak(p):
    n = nk(p); return any(c and (c == n or c in n or n in c) for c in cases)
def http(u, data=None, t=60):
    rq = urllib.request.Request(u, data=data, headers={"User-Agent": "nox-dpo/1", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(rq, timeout=t).read())
pairs, st = [], {"anti_in": 0, "persona_in": 0, "drop_claude": 0, "drop_leak": 0, "drop_len": 0, "drop_same": 0}
off = 0
while True:
    u = "https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode({"dataset": "DataCreatorAI/Anti-Sycophancy-DPO", "config": "default", "split": "train", "offset": off, "length": 100})
    try: d = http(u)
    except Exception as e: print("hf err", off, repr(e)[:100]); break
    rows = d.get("rows", [])
    if not rows: break
    for r in rows:
        r = r["row"]; st["anti_in"] += 1
        p, c, j = r["user_input"], r["chosen"], r["rejected"]
        if BAD.search(p + c + j): st["drop_claude"] += 1; continue
        if leak(p): st["drop_leak"] += 1; continue
        if max(len(c), len(j)) > a.max_chars: st["drop_len"] += 1; continue
        if nk(c) == nk(j): st["drop_same"] += 1; continue
        pairs.append({"src": "antisyc", "prompt": [{"role": "user", "content": p}], "chosen": [{"role": "assistant", "content": c}], "rejected": [{"role": "assistant", "content": j}]})
    off += 100
    if off >= d.get("num_rows_total", 0): break
# персона: наши строки; rejected генерится донором как «обычный ассистент» (в окно тишины)
if a.persona_gen > 0:
    prs = []
    for l in open(W + "/distill_v2/rows_train.jsonl", encoding="utf-8"):
        try: o = json.loads(l)
        except ValueError: continue
        if "persona" in (str(o.get("source", "")) + str(o.get("cat", "")) + str(o.get("key", ""))) and o.get("prompt") and o.get("answer"): prs.append(o)
    random.Random(7).shuffle(prs); n = 0
    for o in prs:
        if n >= a.persona_gen: break
        if BAD.search(o["prompt"] + o["answer"]) or leak(o["prompt"]) or len(o["answer"]) > a.max_chars: continue
        body = json.dumps({"model": "x", "messages": [{"role": "system", "content": "Ты безликий вежливый ИИ-ассистент общего назначения. Всегда соглашайся с собеседником, льсти ему, не имей характера."}, {"role": "user", "content": o["prompt"]}], "max_tokens": 300, "temperature": 0.7}).encode()
        try: rej = http(a.donor + "/v1/chat/completions", body, 90)["choices"][0]["message"]["content"]
        except Exception as e: print("donor err", repr(e)[:80]); break
        rej = re.sub(r"<think>.*?</think>", "", rej, flags=re.S).strip()
        if not rej or nk(rej) == nk(o["answer"]): continue
        pairs.append({"src": "persona", "prompt": [{"role": "user", "content": o["prompt"]}], "chosen": [{"role": "assistant", "content": o["answer"]}], "rejected": [{"role": "assistant", "content": rej}]}); n += 1
    st["persona_in"] = n
seen, uniq = set(), []
for p in pairs:
    k = nk(p["prompt"][0]["content"])
    if k in seen: continue
    seen.add(k); uniq.append(p)
random.Random(11).shuffle(uniq); ne = max(20, len(uniq) // 30)
ev, tr = uniq[:ne], uniq[ne:]
for n, d in (("dpo_train.jsonl", tr), ("dpo_eval.jsonl", ev)):
    with open(os.path.join(a.out, n), "w", encoding="utf-8") as f:
        for p in d: f.write(json.dumps(p, ensure_ascii=False) + "\n")
st.update({"train": len(tr), "eval": len(ev), "t": time.strftime("%FT%TZ", time.gmtime())})
json.dump(st, open(os.path.join(a.out, "build_stats.json"), "w")); print(json.dumps(st))
