"""Бенчмарк чата: TTFT и ток/с через /v1/chat/stream. Запуск: python bench.py <тег>. Результат печатается построчно."""
import json, sys, time, urllib.request
Q = ["Кто ты? Ответь в двух предложениях.",
     "Что ты помнишь о нашем проекте NOX HELION? Три предложения.",
     "Объясни простыми словами, чем кэш промпта помогает скорости. Четыре предложения."]
sys.stdout.reconfigure(line_buffering=True)
tag = sys.argv[1] if len(sys.argv) > 1 else "run"
res = []
for q in Q:
    t0 = time.time(); ttft = None; ntok = 0
    try:
        req = urllib.request.Request("http://127.0.0.1:8091/v1/chat/stream", data=json.dumps({"messages": [{"role": "user", "content": q}]}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=400) as r:
            for raw in r:
                ln = raw.decode("utf-8", "ignore").strip()
                if not ln.startswith("data:"): continue
                try: o = json.loads(ln[5:])
                except Exception: continue
                if o.get("type") == "token":
                    ntok += 1
                    if ttft is None: ttft = time.time() - t0
                elif o.get("type") == "done": break
        tot = time.time() - t0
        gen = max(tot - (ttft or 0), 0.001)
        res.append((ttft, ntok / gen if ntok > 1 else 0))
        print("%s Q%d ttft=%.1fs tokens=%d tok/s=%.1f total=%.1fs" % (tag, len(res), ttft or -1, ntok, ntok / gen, tot))
    except Exception as e:
        print("%s Q%d ERR %s %s" % (tag, len(res) + 1, type(e).__name__, str(e)[:80]))
ok = [x for x in res if x[0]]
if ok: print("%s AVG ttft=%.1fs tok/s=%.1f" % (tag, sum(x[0] for x in ok) / len(ok), sum(x[1] for x in ok) / len(ok)))
print("BENCH_DONE")
