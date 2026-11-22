#!/usr/bin/env python3
# B: быстрый замер напрямую на сервер: pp (длинный промпт) и tg. usage: bench.py PORT TAG [timeout]
import json, sys, time, urllib.request
port, tag = sys.argv[1], sys.argv[2]; to = int(sys.argv[3]) if len(sys.argv) > 3 else 300
base = "http://127.0.0.1:%s" % port
def get(p, t=10):
    return json.loads(urllib.request.urlopen(base + p, timeout=t).read().decode() or "{}")
def post(p, o, t):
    r = urllib.request.Request(base + p, json.dumps(o).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read().decode())
out = {"tag": tag, "ts": time.strftime("%F %T")}
try:
    out["health"] = get("/health")
    try:
        sl = get("/slots"); out["slots_busy"] = [s.get("is_processing") for s in sl]
    except Exception as e: out["slots_err"] = str(e)[:80]
    words = ("Скорость генерации большой языковой модели на процессоре ограничена пропускной способностью памяти. " * 60)
    for name, prompt, n in (("short", "Ответь одним абзацем: зачем нужен кэш ключей и значений?", 48),
                            ("long", words + "\nКратко: о чём текст?", 48)):
        t0 = time.time()
        try:
            r = post("/completion", {"prompt": prompt, "n_predict": n, "temperature": 0, "cache_prompt": False}, to)
            tm = r.get("timings", {})
            out[name] = {"wall": round(time.time() - t0, 2), "pp_n": tm.get("prompt_n"), "pp_s": round(tm.get("prompt_per_second", 0), 2),
                         "tg_n": tm.get("predicted_n"), "tg_s": round(tm.get("predicted_per_second", 0), 3), "ttft_ms": round(tm.get("prompt_ms", 0)),
                         "text": r.get("content", "")[:80]}
        except Exception as e:
            out[name] = {"error": str(e)[:100], "wall": round(time.time() - t0, 1)}
except Exception as e:
    out["error"] = str(e)[:150]
json.dump(out, open("/root/nox/logs/B_bench_%s.json" % tag, "w"), ensure_ascii=False)
print(json.dumps(out, ensure_ascii=False))
