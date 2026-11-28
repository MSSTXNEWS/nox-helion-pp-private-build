#!/usr/bin/env python3
"""v8 bench2: потоковый режим /voice/mic + /voice/events. Время от конца речи до первого звука. Запуск в voice venv (numpy)."""
import http.client, json, time, statistics, os, io, wave, threading
import numpy as np
H = ("127.0.0.1", int(os.environ.get("PORT", "18797")))
def post(path, body, ct="application/json", timeout=60):
    c = http.client.HTTPConnection(*H, timeout=timeout); c.request("POST", path, body, {"Content-Type": ct}); r = c.getresponse(); d = r.read(); return r.status, d
def get(path, timeout=30):
    c = http.client.HTTPConnection(*H, timeout=timeout); c.request("GET", path); r = c.getresponse(); return json.loads(r.read())
def tts16(t):
    s, w_ = post("/tts", json.dumps({"text": t}).encode()); w = wave.open(io.BytesIO(w_)); sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32")
    return np.interp(np.arange(0, len(a), sr / 16000.0), np.arange(len(a)), a).astype("<i2").tobytes()
def med(x): return round(statistics.median(x), 3) if x else None
Q = tts16("Привет, как дела, расскажи коротко, что нового.")
# срезаем хвостовую тишину, чтобы конец речи был точкой отсчёта
a = np.frombuffer(Q, dtype="<i2"); nz = np.nonzero(np.abs(a) > 600)[0]; Q = a[:nz[-1] + 1].tobytes()
SIL = b"\0" * 1024
def trial(i):
    cid = "v8mic%d_%d" % (int(time.time()), i); ev = []; stop = [False]; after = [0]
    def poll():
        while not stop[0]:
            try: j = get("/voice/events?cid=%s&after=%d" % (cid, after[0]))
            except Exception: time.sleep(0.2); continue
            for e in j["events"]: e["rx"] = time.time(); ev.append(e)
            after[0] = j["next"]
    post("/voice/mic?cid=" + cid, SIL)  # создать сессию
    th = threading.Thread(target=poll, daemon=True); th.start()
    for k in range(0, len(Q) - 1023, 1024): post("/voice/mic?cid=" + cid, Q[k:k + 1024]); time.sleep(0.032)
    t_end = time.time(); n = 0
    while time.time() - t_end < 25:
        post("/voice/mic?cid=" + cid, SIL); time.sleep(0.032); n += 1
        if any(e.get("t") in ("done", "barge", "error") for e in ev): break
    stop[0] = True
    fl = [e["rx"] - t_end for e in ev if e.get("t") == "audio" and e.get("filler")]
    sp = [e["rx"] - t_end for e in ev if e.get("t") == "audio" and not e.get("filler")]
    st = [e["rx"] - t_end for e in ev if e.get("t") == "stt"]; txt = [e.get("text") for e in ev if e.get("t") == "stt"]
    return {"filler": round(fl[0], 3) if fl else None, "speech": round(sp[0], 3) if sp else None, "final_text_s": round(st[0], 3) if st else None, "n_text": len(txt), "partials": sum(1 for e in ev if e.get("t") == "partial")}
r = []
for i in range(10):
    try: r.append(trial(i))
    except Exception as e: r.append({"err": str(e)[:80]})
ok = [x for x in r if x.get("filler") is not None]
print(json.dumps({"stream_filler_after_end_s_median": med([x["filler"] for x in ok]), "stream_speech_after_end_s_median": med([x["speech"] for x in r if x.get("speech")]), "stream_final_text_s_median": med([x["final_text_s"] for x in r if x.get("final_text_s")]), "trials": r}, ensure_ascii=False))
