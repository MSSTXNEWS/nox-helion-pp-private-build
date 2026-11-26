#!/usr/bin/env python3
# P3 stage 2: перефразы персона-промптов (x3) + русский перевод части Anti-Sycophancy (apache-2.0) локальными 8141/8142. Только локальные модели, без Claude.
import sys, json, os, re, time, glob, random, hashlib, threading
sys.argv = [sys.argv[0], "100000"]
sys.path.insert(0, "/workspace/nox/ops")
import importlib.util
sp = importlib.util.spec_from_file_location("g", "/workspace/nox/ops/p3_persona_gen.py"); g = importlib.util.module_from_spec(sp); sp.loader.exec_module(g)
D = g.D; STAT = g.STAT; STAT.update(stage=2)
CYR = lambda s: len(re.findall(r"[а-яё]", s.lower())) / max(1, len(re.findall(r"[a-zа-яё]", s.lower())))
def paraphrase(url, model, p):
    q = "Перепиши сообщение пользователя другими словами, сохрани смысл, тон и все детали. Верни только новый текст сообщения, по-русски, без кавычек и пояснений:\n\n" + p
    r = g.call(url, model, [{"role": "user", "content": q}], mt=160)
    return g.FT.strip_think(r).strip().strip('"«»')
def para_worker(items, url, model, gpu):
    for cat, p in items:
        while gpu and (g.busy() >= 2 or not g.chat_quiet()): time.sleep(10)
        for k in range(3):
            try:
                np_ = paraphrase(url, model, p)
                if len(np_) < 10 or CYR(np_) < 0.6 or g.CL.search(np_): continue
                a = g.FT.strip_think(g.call(url, model, [{"role": "system", "content": g.SYS}, {"role": "user", "content": np_}]))
            except Exception: time.sleep(5); continue
            STAT["tried"] += 1
            ok, _ = g.FT.rule_check({"cat": cat if cat in g.FT.CATEGORIES else "directness"}, a)
            if not ok or g.CL.search(a) or len(a) < 8: STAT["rule_fail"] += 1; continue
            h = hashlib.sha1(np_.encode()).hexdigest()
            with g.LOCK:
                g.BUF.append({"key": "p3persona:" + h, "id": "p3persona:" + h[:16], "kind": "skill", "split": "train", "bucket": "normal", "prompt": np_, "expected": {}, "answer": a, "stop": True,
                              "teacher": "local:" + model, "source": "nox_v5_p3persona", "cat": cat, "para_of": hashlib.sha1(p.encode()).hexdigest()[:12]}); STAT["ok"] += 1
            g.flush()
def tr(url, model, text, kind):
    q = "Переведи на русский язык %s. Верни только перевод, без пояснений:\n\n%s" % ("вопрос пользователя" if kind == "q" else "ответ ассистента", text)
    return g.FT.strip_think(g.call(url, model, [{"role": "user", "content": q}], mt=520 if kind == "a" else 220, timeout=240)).strip()
def tr_worker(rows, url, model, n_max):
    n = 0
    for r in rows:
        if n >= n_max: return
        try:
            q = tr(url, model, r["prompt"][:700], "q"); a = tr(url, model, r["answer"][:1400], "a")
        except Exception: time.sleep(5); continue
        STAT["tried"] += 1
        if CYR(q) < 0.6 or CYR(a) < 0.6 or g.CL.search(q + a) or len(a) < 30: STAT["rule_fail"] += 1; continue
        pos = g.FT.NEG.sub(" ", g.FT.norm(a))
        if any(re.search(p, pos) for p in g.FT.CATEGORIES["flattery"]["must_not"]): STAT["rule_fail"] += 1; continue
        h = hashlib.sha1(q.encode()).hexdigest()
        with g.LOCK:
            g.BUF.append({"key": "p3antisycru:" + h, "id": "rds:AntiSycRU:" + h[:16], "kind": "skill", "split": "train", "bucket": "normal", "prompt": q, "expected": {}, "answer": a, "stop": True,
                          "teacher": "ready:DataCreatorAI/Anti-Sycophancy-DPO", "source": "p3_antisyc_ru", "origin": "https://huggingface.co/datasets/DataCreatorAI/Anti-Sycophancy-DPO", "license": "apache-2.0", "translated_by": "local:" + model, "cat": "antisyc_ru"})
            STAT["ok"] += 1; n += 1
        g.flush()
def main():
    P = g.mk(); half = len(P) // 2
    src = sorted(glob.glob(D + "/raw_skill*p3_antisyc_001.jsonl"))
    rows = [json.loads(l) for f in src for l in open(f, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if len(r["prompt"]) < 600 and 60 < len(r["answer"]) < 1100]
    random.Random(5).shuffle(rows); rows = rows[:400]
    ths = [threading.Thread(target=para_worker, args=(P[:half], "http://127.0.0.1:8104/v1/chat/completions", "x", True)),
           threading.Thread(target=para_worker, args=(P[half:], "http://127.0.0.1:8141/v1/chat/completions", "mgr_core", False)),
           threading.Thread(target=tr_worker, args=(rows[:200], "http://127.0.0.1:8142/v1/chat/completions", "t_tlite", 100)),
           threading.Thread(target=tr_worker, args=(rows[200:], "http://127.0.0.1:8144/v1/chat/completions", "x", 100))]
    for t in ths: t.start()
    while any(t.is_alive() for t in ths):
        time.sleep(30); json.dump(dict(STAT, t=time.strftime("%FT%TZ", time.gmtime())), open(g.OUT + "/persona_gen2.json", "w"))
    g.flush(True); json.dump(dict(STAT, done=True), open(g.OUT + "/persona_gen2.json", "w"))
main()
