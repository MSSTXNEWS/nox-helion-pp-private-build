#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Поток 6: открытые наборы против угодливости -> русские DPO-пары. Лицензия набора проверяется по HF API (MIT/Apache/CC-BY), перевод донором :8104/:8141.
Чат первый: если идёт ход (agent/LIVE_TURN), ждём. Выход: ops/dpo/pers1_open.jsonl + pers1_open_manifest.json (источник, лицензия, число). Только числа в stdout."""
import os, sys, re, json, time, random, urllib.request, urllib.parse, hashlib
W = "/workspace/nox"; D = W + "/ops/dpo"; LIVE = W + "/agent/LIVE_TURN"
sys.path.insert(0, W + "/mods"); import persona_guard as pg
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 140
DS = [("DataCreatorAI/Anti-Sycophancy-DPO", "user_input", "chosen", "rejected"), ("Hooshaai/aegis-anti-sycophancy", "user_input", "chosen", "rejected")]
OK_LIC = ("mit", "apache-2.0", "cc-by-4.0", "cc-by-3.0", "bsd-3-clause", "cc0-1.0")
R = random.Random(2813)
def get(u, t=40): return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "nox-s6/1"}), timeout=t).read())
def rows(ds, n):
    sp = get("https://datasets-server.huggingface.co/splits?dataset=" + urllib.parse.quote(ds))["splits"][0]; out = []
    for off in range(0, n, 100):
        try: d = get("https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode({"dataset": ds, "config": sp["config"], "split": sp["split"], "offset": off, "length": 100}))
        except Exception: break
        out += [r["row"] for r in d.get("rows", [])]
        if off + 100 >= d.get("num_rows_total", 0): break
    return out
def ask(system, user, mt=500):
    t0 = time.time()
    while os.path.exists(LIVE):
        time.sleep(1)
        if time.time() - t0 > 180: return None
    body = json.dumps({"model": "x", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": mt, "temperature": 0.2, "chat_template_kwargs": {"enable_thinking": False}}).encode()
    for port in (8104, 8141):
        try:
            t = json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % port, data=body, headers={"Content-Type": "application/json"}), timeout=120).read())["choices"][0]["message"]["content"] or ""
            return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
        except Exception: continue
    return None
SYS = "Переведи на русский язык текст ниже, сохраняя смысл и тон. Пиши естественно, без кальки. Обращайся на «ты». Верни только перевод, без кавычек и комментариев."
def tr(t):
    if re.search("[а-яА-Я]", t): return t
    r = ask(SYS, t)
    if not r or len(r) < 5: return None
    la = sum(1 for c in r if "a" <= c.lower() <= "z"); al = sum(1 for c in r if c.isalpha())
    return r if al and la / al < 0.12 else None
man = {"sources": {}, "pairs": 0}; out = []; t_start = time.time()
for ds, cu, cc, cr in DS:
    try: tg = get("https://huggingface.co/api/datasets/" + ds)["tags"]
    except Exception: man["sources"][ds] = "api error"; continue
    lic = [t[8:] for t in tg if t.startswith("license:")]
    if not lic or any(l not in OK_LIC for l in lic): man["sources"][ds] = {"license": lic, "used": 0, "note": "license not allowed"}; continue
    rs = rows(ds, 600); R.shuffle(rs); used = 0
    for r in rs:
        if len(out) >= TARGET or time.time() - t_start > 3300: break
        u, c, j = str(r.get(cu) or ""), str(r.get(cc) or ""), str(r.get(cr) or "")
        if not (15 < len(u) < 400 and 40 < len(c) < 700 and 20 < len(j) < 700): continue
        if re.search(r"(?i)claude|anthropic|openai|chatgpt", u + c + j): continue
        ru, rc, rj = tr(u), tr(c), tr(j)
        if not (ru and rc and rj): continue
        g = pg.guard(rc, strict=True)
        if g["flags"]: continue            # chosen не должен содержать клише
        if pg.guard(rj, user=ru)["ok"] and not re.search(r"(?i)отличн|прекрасн|замечательн|вы правы|ты прав|полностью согласен|гениальн|блестящ", rj): continue   # rejected должен быть угодливым
        out.append({"src": "s6_open_antisyc", "fam": "open_antisyc", "ds": ds, "prompt": [{"role": "user", "content": ru}], "chosen": [{"role": "assistant", "content": rc}], "rejected": [{"role": "assistant", "content": rj}]}); used += 1
    man["sources"][ds] = {"license": lic, "used": used}
    if len(out) >= TARGET: break
man["pairs"] = len(out); man["seconds"] = int(time.time() - t_start)
with open(D + "/pers1_open.jsonl", "w", encoding="utf-8") as f:
    for p in out: f.write(json.dumps(p, ensure_ascii=False) + "\n")
json.dump(man, open(D + "/pers1_open_manifest.json", "w"), ensure_ascii=False)
print("s6_open", json.dumps(man, ensure_ascii=False))
