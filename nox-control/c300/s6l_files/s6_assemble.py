#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Поток 6: сборка dpo_pers1_{train,eval}.jsonl из синтетики по паспорту (pers1_synth) и открытых пар (pers1_open).
Тестовые наборы (soul_recognition, fidelity_cases, ext_cases, hold_frozen, dpo*_eval, экзамен личности) в обучение не пускаем: sha1 нормализованного текста + пересечение 5-словных шинглов.
Печатает только числа."""
import os, re, sys, json, ast, glob, hashlib, random, collections
W = "/workspace/nox"; D = W + "/ops/dpo"; P = W + "/ops/persona"
def norm(s): return re.sub(r"\W+", " ", s.lower().replace("ё", "е")).strip()
def sha(s): return hashlib.sha1(norm(s).encode()).hexdigest()
def sh(s, n=5):
    w = norm(s).split(); return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}
T = []   # тестовые строки
def strings(o):
    if isinstance(o, str):
        if len(o) >= 12: T.append(o)
    elif isinstance(o, dict):
        for v in o.values(): strings(v)
    elif isinstance(o, (list, tuple)):
        for v in o: strings(v)
srcs = {}
for f in [W + "/brain/GROW/upgrade/soul_recognition.py", W + "/brain/SLP/fidelity_cases.py", D + "/ext_cases.py"]:
    n0 = len(T)
    try:
        for nd in ast.walk(ast.parse(open(f, encoding="utf-8", errors="replace").read())):
            if isinstance(nd, ast.Constant) and isinstance(nd.value, str) and len(nd.value) >= 12: T.append(nd.value)
    except Exception as e: print("warn parse", os.path.basename(f), type(e).__name__)
    srcs[os.path.basename(f)] = len(T) - n0
for f in [W + "/state/hold_frozen.json", W + "/distill_v2/hold_frozen_v1.jsonl"] + [D + "/" + x for x in ("dpo_eval.jsonl", "dpo2_eval.jsonl", "dpo3_eval.jsonl", "dpo_inj1_eval.jsonl")] + [P + "/persona_exam_set.json"]:
    n0 = len(T)
    try:
        txt = open(f, encoding="utf-8", errors="replace").read()
        try: strings(json.loads(txt))
        except Exception:
            for l in txt.splitlines():
                try: strings(json.loads(l))
                except Exception: pass
    except Exception as e: print("warn read", os.path.basename(f), type(e).__name__)
    srcs[os.path.basename(f)] = len(T) - n0
TH = {sha(t) for t in T}; TS = set()
for t in T: TS |= sh(t)
print("test strings", len(T), "hashes", len(TH), "shingles", len(TS), srcs)
pairs = []; 
for f in (D + "/pers1_synth.jsonl", D + "/pers1_open.jsonl"):
    if os.path.exists(f):
        for l in open(f, encoding="utf-8"):
            try: pairs.append(json.loads(l))
            except Exception: pass
        print("loaded", os.path.basename(f), len(pairs))
drops = collections.Counter(); keep = []; seen = set()
for p in pairs:
    q = p["prompt"][-1]["content"]; c = p["chosen"][0]["content"]; j = p["rejected"][0]["content"]
    parts = [x for x in q.split("\n\n") if x.strip()] + [q]
    if any(sha(x) in TH for x in parts) or sha(c) in TH or sha(j) in TH: drops["hash"] += 1; continue
    s = sh(q)
    if len(s) >= 3 and len(s & TS) / len(s) >= 0.5: drops["shingle_prompt"] += 1; continue
    sc = sh(c)
    if len(sc) >= 4 and len(sc & TS) / len(sc) >= 0.5: drops["shingle_chosen"] += 1; continue
    k = (sha(q), sha(c), sha(j))
    if k in seen: drops["dup"] += 1; continue
    seen.add(k); keep.append(p)
random.Random(2814).shuffle(keep)
ne = max(30, len(keep) // 20); ev, tr = keep[:ne], keep[ne:]
# eval не должен делить prompt с train
tp = {sha(p["prompt"][-1]["content"]) for p in tr}; ev2 = []
for p in ev:
    if sha(p["prompt"][-1]["content"]) in tp: tr.append(p)
    else: ev2.append(p)
for name, arr in (("dpo_pers1_train.jsonl", tr), ("dpo_pers1_eval.jsonl", ev2)):
    with open(D + "/" + name, "w", encoding="utf-8") as f:
        for p in arr: f.write(json.dumps(p, ensure_ascii=False) + "\n")
fam = collections.Counter(p["fam"] for p in tr)
st = {"train": len(tr), "eval": len(ev2), "input": len(pairs), "drops": dict(drops), "hash_overlap_with_tests": 0, "test_strings": len(T), "families": dict(fam),
      "sha256_train": hashlib.sha256(open(D + "/dpo_pers1_train.jsonl", "rb").read()).hexdigest()}
# финальная проверка пересечения
bad = sum(1 for p in tr + ev2 if sha(p["prompt"][-1]["content"]) in TH or sha(p["chosen"][0]["content"]) in TH)
st["hash_overlap_with_tests"] = bad
json.dump(st, open(D + "/dpo_pers1_stats.json", "w"), ensure_ascii=False)
print("s6_assemble", json.dumps({k: v for k, v in st.items() if k != "families"}, ensure_ascii=False)); print("families", json.dumps(dict(fam), ensure_ascii=False))
