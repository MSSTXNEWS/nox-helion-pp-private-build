#!/usr/bin/env python3
"""v8 bench: first sound of voice service. stdlib only. numbers only."""
import http.client, json, time, statistics, sys, base64, wave, io, os, threading
H = ("127.0.0.1", int(os.environ.get("PORT", "18797")))
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

# barge-in: длинный ответ, после первого звука шлём речь кадрами по 32 мс
def barge_trial(i):
    import numpy as np
    s_, w_, _ = post("/tts", json.dumps({"text": "Подожди, стой, я хочу тебя перебить."}).encode())
    w = wave.open(io.BytesIO(w_)); sr = w.getframerate(); a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32")
    a16 = np.interp(np.arange(0, len(a), sr / 16000.0), np.arange(len(a)), a).astype("<i2").tobytes()
    s_, q, _ = post("/tts", json.dumps({"text": "Расскажи подробно, как устроен сервер, по шагам, не меньше десяти предложений."}).encode())
    cid = "v8barge%d_%d" % (int(time.time()), i); res = {}
    c = http.client.HTTPConnection(*H, timeout=120); c.request("POST", "/voice/turn?cid=%s&user=owner" % cid, q, {"Content-Type": "audio/wav"}); r = c.getresponse()
    t_first = [None]; fin = {}
    def rd():
        while True:
            l = r.readline()
            if not l: break
            try: o = json.loads(l)
            except Exception: continue
            if o.get("t") == "audio" and not t_first[0]: t_first[0] = time.time()
            if o.get("t") in ("done", "barge"): fin.update(o); fin["t_end"] = time.time(); break
    th = threading.Thread(target=rd); th.start()
    t = time.time()
    while not t_first[0] and time.time() - t < 40: time.sleep(0.02)
    if not t_first[0]: th.join(2); return None
    time.sleep(0.4); ts = time.time(); det = None
    for k in range(0, len(a16) - 1023, 1024):
        s_, d, dt = post("/voice/vad?cid=" + cid, a16[k:k + 1024]); j = json.loads(d)
        if j.get("barge"): det = (time.time() - ts, j.get("cancel_ms"), j.get("ack")); break
        time.sleep(0.032)
    th.join(5)
    return {"barge": bool(det), "detect_s": round(det[0], 3) if det else None, "cancel_ms": det[1] if det else None, "ack": det[2] if det else None, "end_t": fin.get("t")}
bt = []
for i in range(5):
    try: bt.append(barge_trial(i))
    except Exception as e: bt.append({"err": str(e)[:60]})
out["barge_trials"] = bt; out["barge_ok"] = sum(1 for b in bt if b and b.get("barge") and b.get("end_t") == "barge")
print(json.dumps(out, ensure_ascii=False))
