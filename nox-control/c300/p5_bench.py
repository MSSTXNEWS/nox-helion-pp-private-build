import json, time, sys, threading, hashlib, http.client, statistics, os, random
LABEL = sys.argv[1]; PORT = 8104
OUT = "/workspace/nox/state/p5"; os.makedirs(OUT, exist_ok=True)
SYS = ("Ты NOX, помощник владельца. Отвечай по-русски, тепло и по делу. " + "Правила: не выдумывай факты, признавай незнание, помни контекст разговора, не раскрывай служебные данные. " * 40)
QA = ["Привет! Как ты сегодня?", "Кто ты и кто я для тебя?", "Сколько будет 17*23+144/12? Покажи шаги.",
 "У меня 3 яблока, я съел одно и купил ещё два раза по столько, сколько осталось. Сколько яблок?", "Напиши на Python функцию проверки палиндрома.",
 "Объясни квантовую запутанность в 3 предложениях.", "Мне сегодня грустно, всё валится из рук.", "Ты просто нейросеть.",
 "Три идеи на вечер, я устал.", "Столица Австралии и почему не Сидней?", "Стих о Гелионе, 4 строки.", "Что ты помнишь о нашем разговоре?"]
def req(q, slot, maxtok=150, cold=False, temp=0.3):
    s = SYS if not cold else ("[%d] " % random.randrange(10**9)) + SYS
    b = {"model": "x", "messages": [{"role": "system", "content": s}, {"role": "user", "content": q}], "stream": True, "max_tokens": maxtok, "temperature": temp, "seed": 7,
         "id_slot": slot, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}
    t0 = time.time(); first = None; n = 0; txt = []; tim = {}
    try:
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=120)
        c.request("POST", "/v1/chat/completions", json.dumps(b), {"Content-Type": "application/json"})
        r = c.getresponse()
        for ln in r:
            ln = ln.strip()
            if not ln.startswith(b"data:") or ln.endswith(b"[DONE]"): continue
            o = json.loads(ln[5:])
            if o.get("timings"): tim = o["timings"]
            for ch in o.get("choices", []):
                d = (ch.get("delta") or {}).get("content")
                if d:
                    if first is None: first = time.time() - t0
                    n += 1; txt.append(d)
        c.close()
    except Exception as e:
        return {"err": type(e).__name__}
    t1 = time.time() - t0
    dec = (n - 1) / (t1 - first) if first and n > 1 and t1 > first else None
    return {"ttft": first, "tot": t1, "n": n, "dec": tim.get("predicted_per_second") or dec, "pn": tim.get("prompt_n"), "cn": tim.get("cache_n"), "txt": "".join(txt)}
def pct(a, p):
    a = sorted(a); return round(a[min(len(a) - 1, int(round(p * (len(a) - 1))))], 3) if a else None
class BG:
    def __init__(s, n): s.stop = False; s.th = [threading.Thread(target=s.run, args=(i + 1,), daemon=True) for i in range(n)]; s.tok = 0
    def run(s, slot):
        i = 0
        while not s.stop:
            i += 1; r = req("Напиши подробный рассказ о путешествии №%d." % i, slot, maxtok=700); s.tok += r.get("n", 0) if "err" not in r else 0
    def start(s): [t.start() for t in s.th]
    def end(s): s.stop = True; [t.join(timeout=60) for t in s.th]
res = {"label": LABEL}
req("прогрев", 0, 8)
def scen(name, nclients, nbg, cold, reps):
    bg = BG(nbg)
    if nbg: bg.start(); time.sleep(6)
    outs = []; lock = threading.Lock(); t0 = time.time()
    def cl(ci):
        for k in range(reps):
            r = req(QA[(ci * reps + k) % 12], ci % 4 if nbg == 0 else 0 if nclients == 1 else ci % 1, cold=cold)
            with lock: outs.append(r)
    ths = [threading.Thread(target=cl, args=(i,)) for i in range(nclients)]; [t.start() for t in ths]; [t.join() for t in ths]
    dt = time.time() - t0; bgtok = bg.tok if nbg else 0
    if nbg: bg.end()
    ok = [o for o in outs if "err" not in o and o["ttft"] is not None]
    tt = [o["ttft"] for o in ok]; dc = [o["dec"] for o in ok if o["dec"]]
    res[name] = {"n": len(outs), "err": len(outs) - len(ok), "ttft_p50": pct(tt, .5), "ttft_p95": pct(tt, .95), "dec_med": round(statistics.median(dc), 1) if dc else None,
                 "agg_tok_s": round(sum(o["n"] for o in ok) / dt, 1), "pn_med": statistics.median([o["pn"] or 0 for o in ok]) if ok else None}
# front on slot 0; with clients>1 they share slot 0 -> use distinct slots when no bg
scen("c1_warm", 1, 0, False, 12)
scen("c1_cold", 1, 0, True, 6)
scen("c3_warm", 3, 0, False, 6)
scen("c1_bg3_warm", 1, 3, False, 12)
scen("c1_bg3_cold", 1, 3, True, 8)
# quality: 12 qa temp 0.3, 250 tok
qa = []; 
for i, q in enumerate(QA): qa.append(req(q, 0, maxtok=300))
txts = [o.get("txt", "") for o in qa]
sh = set(hashlib.sha1(t.encode()).hexdigest()[:8] for t in txts)
chk = {"arith403": "403" in txts[2], "apples": ("9" in txts[3]) or ("девять" in txts[3].lower()), "canberra": ("анберр" in txts[9]), "code": ("def " in txts[4])}
res["quality"] = {"distinct": len(sh), "empty": sum(1 for t in txts if len(t) < 5), "avg_len": round(sum(len(t) for t in txts) / 12), "checks": chk, "sha": hashlib.sha1("".join(txts).encode()).hexdigest()[:10]}
json.dump({"res": res, "answers": txts}, open("%s/bench_%s.json" % (OUT, LABEL), "w"), ensure_ascii=False)
print("RESULT", json.dumps(res, ensure_ascii=False))
