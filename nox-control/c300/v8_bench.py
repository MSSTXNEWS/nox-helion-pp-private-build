#!/usr/bin/env python3
"""v8 bench: first sound of voice service. stdlib only. numbers only."""
import http.client, json, time, statistics, sys, base64, wave, io
H = ("127.0.0.1", 18797)
def post(path, body, ct="application/json", timeout=90):
    c = http.client.HTTPConnection(*H, timeout=timeout); t = time.time(); c.request("POST", path, body, {"Content-Type": ct}); r = c.getresponse(); d = r.read(); return r.status, d, time.time() - t
def med(x): return round(statistics.median(x), 3) if x else None
out = {}
ph = {"short": "Понял, слушаю.", "clause": "Сейчас посмотрю, что у нас с сервером.", "long": "Сейчас посмотрю, что у нас с сервером, и расскажу коротко: всё работает, ошибок нет."}
for k, t in ph.items():
    xs = []
    for i in range(10):
        s, d, dt = post("/tts", json.dumps({"text": t}).encode()); xs.append(dt)
    out["tts_" + k + "_s_median"] = med(xs); out["tts_" + k + "_s_all"] = [round(x, 2) for x in xs]
# full turn: speech wav from /tts as input
s, wav, _ = post("/tts", json.dumps({"text": "Привет, как дела, расскажи коротко, что нового."}).encode())
fa, fl, ev1, tot, errs = [], [], [], [], 0
for i in range(10):
    c = http.client.HTTPConnection(*H, timeout=120); t0 = time.time()
    c.request("POST", "/voice/turn?cid=v8bench%d_%d&user=owner" % (int(t0), i), wav, {"Content-Type": "audio/wav"}); r = c.getresponse()
    first = None; filler = None; stt = None; got = {}
    while True:
        l = r.readline()
        if not l: break
        try: o = json.loads(l)
        except Exception: continue
        if o.get("t") == "stt": stt = time.time() - t0
        if o.get("t") == "audio":
            if o.get("filler"): filler = filler or time.time() - t0
            else: first = first or time.time() - t0
        if o.get("t") == "error": errs += 1
        if o.get("t") in ("done", "barge"): got = o; break
    c.close(); tot.append(time.time() - t0)
    if first: fa.append(first)
    if filler: fl.append(filler)
    if stt: ev1.append(stt)
out.update({"turn_stt_s_median": med(ev1), "turn_first_speech_audio_s_median": med(fa), "turn_first_speech_audio_s_all": [round(x, 2) for x in fa], "turn_filler_s_median": med(fl), "turn_errors": errs, "turn_n_ok": len(fa)})
print(json.dumps(out, ensure_ascii=False))
