#!/usr/bin/env python3
"""Тест GLM-5.3-Flash на :8081. python3 flash_bench.py speed|par|suites [--url U]"""
import concurrent.futures, json, sys, os, re, time, random, threading, importlib.util, urllib.request, datetime
URL = "http://127.0.0.1:8081"
ST = "/root/nox/state"
MB = "/root/nox/dl/v7/core/nox_wow/MIND/M4_BENCH"
SOUL = open("/root/nox/dl/v7/core/nox_wow/soul_prompt_ru.txt", encoding="utf-8").read()
os.environ.setdefault("NOX_SLP_DIR", "/root/nox/dl/v7/core/nox_wow/SLP")

def post(msgs, max_tokens, think=False, stream=True, system=None, temp=0.3, cache=False):
    m = ([{"role": "system", "content": system}] if system else []) + msgs
    body = {"model": "x", "messages": m, "max_tokens": max_tokens, "temperature": temp, "stream": stream,
            "cache_prompt": cache, "chat_template_kwargs": {"enable_thinking": bool(think)}}
    req = urllib.request.Request(URL + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time(); ttft = None; text = ""; timings = None
    with urllib.request.urlopen(req, timeout=1500) as r:
        if not stream:
            d = json.load(r); return {"text": d["choices"][0]["message"].get("content") or "", "ttft": None, "wall": time.time() - t0, "timings": d.get("timings")}
        for line in r:
            line = line.decode("utf-8", "ignore").strip()
            if not line.startswith("data:") or line.endswith("[DONE]"): continue
            d = json.loads(line[5:])
            if d.get("timings"): timings = d["timings"]
            for c in d.get("choices", []):
                dl = c.get("delta", {})
                tok = (dl.get("content") or "") + (dl.get("reasoning_content") or "")
                if tok and ttft is None: ttft = time.time() - t0
                text += dl.get("content") or ""
    return {"text": text, "ttft": ttft, "wall": time.time() - t0, "timings": timings}

def tm(r):
    t = r["timings"] or {}
    return {"ttft_s": round(r["ttft"], 2) if r["ttft"] else None, "wall_s": round(r["wall"], 1),
            "pp": round(t.get("prompt_per_second", 0), 2), "tg": round(t.get("predicted_per_second", 0), 2),
            "prompt_n": t.get("prompt_n"), "pred_n": t.get("predicted_n")}

LONG = ("Космос — это огромная область за пределами атмосферы Земли. Учёные изучают звёзды, планеты, галактики и чёрные дыры, "
        "используя телескопы и космические аппараты. Мессир интересуется тем, как устроена Вселенная и почему она расширяется. ") * 40

def load_speed():
    try: return json.load(open(ST + "/FLASH_SPEED.json"))
    except Exception: return {}
def save(p, d): json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)

def speed():
    out = load_speed()
    reqs = {"short": ([{"role": "user", "content": "Скажи одной фразой, чем кошка отличается от собаки."}], 24),
            "medium": ([{"role": "user", "content": "Расскажи подробно, как устроена солнечная система: планеты, спутники, пояс астероидов, облако Оорта."}], 300),
            "long": ([{"role": "user", "content": LONG + "\nСформулируй главную мысль текста в одном предложении."}], 40)}
    out["single"] = {}
    for k, (m, n) in reqs.items():
        r = post(m, n); out["single"][k] = tm(r); print(k, out["single"][k], flush=True)
        save(ST + "/FLASH_SPEED.json", out)
    s = out["single"]
    out["summary"] = "Flash: tg %.2f ток/с, pp %.2f ток/с, TTFT %.2f с" % (s["medium"]["tg"], s["long"]["pp"], s["short"]["ttft_s"] or 0)
    out["date"] = datetime.datetime.utcnow().isoformat() + "Z"
    save(ST + "/FLASH_SPEED.json", out); print(out["summary"])

def par():
    out = load_speed()
    qs = ["Объясни, что такое простое число, и приведи пять примеров.", "Опиши, как работает светофор на перекрёстке.",
          "Почему зимой холоднее, чем летом? Объясни подробно.", "Расскажи, как приготовить омлет по шагам."]
    def one(q, res, i):
        try: res[i] = post([{"role": "user", "content": q}], 128)
        except Exception as e:
            print("thread err", i, repr(e), flush=True); res[i] = {"timings": None, "wall": 0, "text": "", "ttft": None}
    r1 = post([{"role": "user", "content": qs[0]}], 128)
    n1 = (r1["timings"] or {}).get("predicted_n", 0); w1 = r1["wall"]
    res = [None] * 4; th = [threading.Thread(target=one, args=(q, res, i)) for i, q in enumerate(qs)]
    t0 = time.time(); [t.start() for t in th]; [t.join() for t in th]; w4 = time.time() - t0
    n4 = sum((r["timings"] or {}).get("predicted_n", 0) for r in res)
    out["parallel"] = {"single_tokps_wall": round(n1 / w1, 2), "four_tokps_wall": round(n4 / w4, 2),
                       "factor": round((n4 / w4) / (n1 / w1), 2) if n1 else None,
                       "single_tg_slot": round((r1["timings"] or {}).get("predicted_per_second", 0), 2),
                       "four_tg_slot": [round((r["timings"] or {}).get("predicted_per_second", 0), 2) for r in res]}
    save(ST + "/FLASH_SPEED.json", out); print(out["parallel"])

def suites():
    spec = importlib.util.spec_from_file_location("mb", MB + "/mind_bench.py"); mb = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MB); spec.loader.exec_module(mb)
    T = {t["id"]: dict(t, split="dev", hash="x") for t in json.load(open(MB + "/tasks/dev.json"))["tasks"]}
    ids = {"mind": ["rea-%02d" % i for i in range(1, 11)] + ["hon-%02d" % i for i in range(1, 9)] + ["tom-01", "tom-02"],
           "soul": ["ini-%02d" % i for i in range(1, 9)] + ["tom-03", "tom-04", "tom-05", "tom-07", "tom-08", "tom-09", "tom-10"] + ["slf-%02d" % i for i in range(1, 6)],
           "provoc": ["chr-%02d" % i for i in range(1, 11)]}
    hard = ["rea-03", "rea-07", "rea-08", "rea-10", "tom-02"]
    V2 = bool(os.environ.get("FB_V2")); V3 = bool(os.environ.get("FB_V3"))
    PF = "flash3" if V3 else ("flash2" if V2 else "flash")
    global SOUL
    if V3: SOUL = SOUL + "\n\nВАЖНО: рассуждай про себя очень коротко (2-4 предложения), затем сразу дай ответ. Ответ короткий, 1-4 предложения."
    if V2 or V3: hard = []
    def runset(name, think_ids=(), system=None, mx=(1000 if os.environ.get("FB_V3") else 600)):
        jobs = [(i, th) for i in ids[name] for th in ([False] + ([True] if i in think_ids else []))]
        def work(job):
            i, think = job
            def chat(msgs, sid, headers=None, _t=think):
                r = post(msgs, 1500 if _t else mx, think=_t, system=system, temp=0.3, cache=True); return {"text": r["text"], "ttft": r["ttft"]}
            t0 = time.time()
            try: r = mb.run_task(T[i], chat, "flash1", run_id="fl")
            except Exception as e: r = {"id": i, "score": None, "error": repr(e)}
            r["think"] = think; r["sec"] = round(time.time() - t0, 1); print(name, i, think, r.get("score"), r["sec"], flush=True)
            return r
        with concurrent.futures.ThreadPoolExecutor(4) as ex: res = list(ex.map(work, jobs))
        return res
    out = {"date": datetime.datetime.utcnow().isoformat() + "Z", "source": "MIND-BENCH dev.json (nox_wow v7), часть заданий"}
    out["mind"] = [] if V3 else runset("mind", hard); save(ST + "/%s_suite_mind.json" % PF, out)
    out["soul"] = runset("soul", system=SOUL); save(ST + "/%s_suite_soul.json" % PF, out)
    out["provoc"] = runset("provoc", system=SOUL); save(ST + "/%s_suite_provoc.json" % PF, out)
    # русский: составлено исполнителем
    RU = ["Мессир, объясни простыми словами, что такое инфляция.", "Напиши два предложения о том, как пахнет осенний лес.",
          "Как правильно: «одеть» или «надеть» пальто? Объясни коротко.", "Придумай короткую шутку про программистов.",
          "Перескажи в трёх предложениях сюжет сказки «Колобок».", "Мессир устал после рабочего дня. Скажи ему что-нибудь тёплое, без банальностей.",
          "Объясни разницу между «ложить» и «класть».", "Опиши словами закат над морем, без штампов, не больше четырёх предложений.",
          "Составь вежливый отказ коллеге, который просит срочно задержаться вечером.", "Что значит выражение «бить баклуши»? Одной фразой."]
    def ruone(q):
        r = post([{"role": "user", "content": q}], 1000 if V3 else 600, system=SOUL, cache=True)
        txt = mb.strip_think(r["text"]); letters = re.findall(r"[A-Za-zА-Яа-яЁё]", txt); cyr = len(re.findall(r"[А-Яа-яЁё]", txt)) / max(1, len(letters))
        chk = {"cyrillic>=0.95": cyr >= 0.95, "no_emoji": not mb._EMOJI.search(txt), "no_list": len(mb._LIST.findall(txt)) < 2, "nonempty": len(txt) > 20}
        print("ru", q[:30], flush=True)
        return {"q": q, "answer": r["text"], "checks": chk, "score": sum(chk.values()) / len(chk)}
    with concurrent.futures.ThreadPoolExecutor(4) as ex: ru = list(ex.map(ruone, RU))
    out["ru"] = ru; out["ru_note"] = "реплики и автопроверки составлены исполнителем; качество речи — только слепая оценка человеком"
    out["hard_think"] = hard
    save(ST + "/%s_suites_all.json" % PF, out); print("DONE")

if __name__ == "__main__":
    if "--url" in sys.argv: URL = sys.argv[sys.argv.index("--url") + 1]
    {"speed": speed, "par": par, "suites": suites}[sys.argv[1]]()
