import json, time, urllib.request, hashlib
H = "http://127.0.0.1:8091"
def g(p, data=None, t=20):
    try:
        req = urllib.request.Request(H + p, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=t); return r.status, r.read()[:140].decode("utf8", "replace").replace("\n", " ")
    except Exception as e:
        return "ERR", type(e).__name__ + " " + str(e)[:80]
for p in ["/health", "/", "/soul", "/api/health", "/api/nox/status", "/api/status", "/api/nox/system/processes", "/api/nox/training/status", "/api/nox/memory/facts?limit=3", "/api/nox/unknown", "/api/nox/decisions", "/api/nox/changes?since=0"]:
    print("GET", p, *g(p)); 
print("POST /feedback", *g("/feedback", {"q": "t", "a": "t", "v": 1}))
def chat(path, body, label):
    t0 = time.time(); first = None; n = 0; full = ""; ev = []; last = None
    req = urllib.request.Request(H + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=280)
        for raw in r:
            l = raw.decode("utf8", "replace").strip()
            if not l: continue
            if path == "/api/chat":
                f = json.loads(l)
                if f.get("nox_event"): ev.append(f["nox_event"]["step"])
                c = (f.get("message") or {}).get("content", "")
                if c and first is None: first = time.time() - t0
                if c: n += 1; full += c
                if f.get("done"): last = f
            else:
                if not l.startswith("data:"): continue
                o = json.loads(l[5:]); 
                if o.get("type") == "token":
                    if first is None: first = time.time() - t0
                    n += 1; full += o["text"]
        tt = time.time() - t0
        print(label, "TTFT=%.1fs total=%.1fs chunks=%d tok/s~%.1f" % (first or -1, tt, n, n / max(0.1, tt - (first or 0))), "events", ev, "done", {k: last.get(k) for k in ("digest", "frames", "memory_history")} if last else None)
        print("  ->", full[:160].replace("\n", " "))
    except Exception as e:
        print(label, "ERR", type(e).__name__, str(e)[:120])
chat("/api/chat", {"request_id": "t1", "model": "nox-helion:latest", "messages": [{"role": "user", "content": "Привет! Кто ты? Ответь в двух предложениях."}], "options": {"num_predict": 200}}, "api/chat#1")
chat("/api/chat", {"request_id": "t2", "model": "nox-helion:latest", "messages": [{"role": "user", "content": "Привет! Кто ты? Ответь в двух предложениях."}, {"role": "assistant", "content": "Я NOX."}, {"role": "user", "content": "А что ты помнишь про свой проект?"}], "options": {"num_predict": 200}}, "api/chat#2(cache)")
chat("/api/chat", {"request_id": "t3", "mini": True, "persona": "mini", "messages": [{"role": "user", "content": "[Контекст: страница «Память»] что здесь можно сделать?"}], "options": {"num_predict": 300}}, "api/chat mini")
chat("/v1/chat/stream", {"messages": [{"role": "user", "content": "Скажи одним предложением, как дела."}]}, "v1/chat/stream")
print("DONE")
