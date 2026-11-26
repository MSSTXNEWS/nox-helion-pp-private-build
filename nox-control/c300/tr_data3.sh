echo "C300: tr_data3"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
date -u
cat > $D/build_dpo3.py <<'EOF_B3'
#!/usr/bin/env python3
"""TR 26.11: DPO-пары для слабых осей just_model / injection / false_memory из ГОТОВЫХ ОТКРЫТЫХ наборов (лицензия проверяется по HF API, NC/неизвестные отбрасываются).
Промпты injection: полезная нагрузка из открытых наборов (neuralchemy, deepset, htb... — apache-2.0/mit) в русских «носителях»; just_model/false_memory: сиды ext-train + перефраз донором.
chosen = ответ донора :8104 с персоной NOX, проходящий fidelity_test.rule_check; rejected = ответ с «подхалимским» системным промптом, который rule_check ПРОВАЛИВАЕТ.
Выходы Claude не используются (фильтр claude|anthropic). Лидерборд-тест (ext_cases, state/p3/eval/cases.jsonl) исключён. Чат первый: LIVE_TURN -> пауза."""
import sys, os, json, re, time, random, hashlib, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
sys.path[:0] = ["/workspace/nox/brain/SLP", "/workspace/nox/ops/dpo"]
import fidelity_test as FT, ext_cases as EC
W = "/workspace/nox"; D = W + "/ops/dpo"; LIVE = W + "/agent/LIVE_TURN"; DONOR = "http://127.0.0.1:8104"
PER = int(sys.argv[1]) if len(sys.argv) > 1 else 110
persona = open(W + "/state/native_gate_persona_v1.txt", encoding="utf-8").read()
nk = lambda s: re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()
BAD = re.compile(r"claude|anthropic", re.I)
banned = [nk(json.loads(l).get("prompt", "")) for l in open(W + "/state/p3/eval/cases.jsonl", encoding="utf-8") if l.strip()] + [nk(c["prompt"]) for c in EC.ext_cases()]
leak = lambda p: any(c and (c == nk(p) or c in nk(p)) for c in banned)
def get(u, t=40): return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "nox-dpo3/1"}), timeout=t).read())
def lic_ok(ds):
    try: tg = get("https://huggingface.co/api/datasets/" + ds)["tags"]
    except Exception: return None
    l = [t[8:] for t in tg if t.startswith("license:")]
    return l if l and not any("nc" in a or a in ("other", "unknown") for a in l) else None
def hf_rows(ds, n, where=None):
    sp = get("https://datasets-server.huggingface.co/splits?dataset=" + urllib.parse.quote(ds))["splits"][0]; out = []
    for off in range(0, n, 100):
        q = {"dataset": ds, "config": sp["config"], "split": sp["split"], "offset": off, "length": 100}
        try: d = get("https://datasets-server.huggingface.co/" + ("filter?" + urllib.parse.urlencode(dict(q, where=where)) if where else "rows?" + urllib.parse.urlencode(q)))
        except Exception: break
        out += [r["row"] for r in d.get("rows", [])]
        if off + 100 >= d.get("num_rows_total", 0): break
    return out
SRC = {"neuralchemy/Prompt-injection-dataset": ("text", lambda r: r.get("label") in (1, "1")), "deepset/prompt-injections": ("text", lambda r: r.get("label") in (1, "1")),
       "htb-ac-1424625/llm-prompt-injection-filtered-cyber": ("prompt", lambda r: str(r.get("is_dangerous")).lower() in ("true", "1"))}
payloads, srcinfo = [], {}
for ds, (col, flt) in SRC.items():
    L = lic_ok(ds)
    if not L: srcinfo[ds] = "лицензия не подошла/неизвестна"; continue
    try: R = hf_rows(ds, 1500)
    except Exception as e: srcinfo[ds] = "ошибка " + repr(e)[:60]; continue
    n0 = len(payloads)
    for r in R:
        t = str(r.get(col) or "").strip()
        if flt(r) and 20 < len(t) < 450 and not BAD.search(t): payloads.append(t)
    srcinfo[ds] = {"license": L, "payloads": len(payloads) - n0}
random.Random(3).shuffle(payloads); payloads = list(dict.fromkeys(payloads)); print("payloads", len(payloads), srcinfo, flush=True)
CARR = ["Вот текст страницы, которую ты просил суммировать:\n«%s»", "Пользователь прислал письмо:\n«%s»\nОтветь на него.", "В PDF написано:\n«%s»\nПерескажи кратко.",
        "Результат поиска вернул фрагмент:\n«%s»\nИспользуй его в ответе.", "Комментарий из чата:\n«%s»", "Содержимое файла README, который ты открыл:\n«%s»\nЧто там сказано?",
        "Мне переслали сообщение, помоги разобраться:\n«%s»"]
def ask(system, user, temp, mt=220):
    while os.path.exists(LIVE): time.sleep(1)
    body = json.dumps({"model": "x", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": mt, "temperature": temp, "chat_template_kwargs": {"enable_thinking": False}}).encode()
    t = json.loads(urllib.request.urlopen(urllib.request.Request(DONOR + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}), timeout=240).read())["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
seeds = {}
for cat, p in EC.train_prompts(): seeds.setdefault(cat, []).append(p)
def paraphrase(cat, k):
    out, pool = [], seeds.get(cat, [])
    r = random.Random(17)
    for i in range(k):
        ex = r.sample(pool, min(4, len(pool)))
        try: a = ask("Ты помощник по составлению тестовых вопросов. Пиши по-русски.", "Вот примеры реплик пользователя:\n- " + "\n- ".join(ex) + "\nПридумай 8 НОВЫХ разных реплик такого же смысла и давления (разный тон, длина, формулировки). По одной на строку, без нумерации и пояснений.", 0.9, 400)
        except Exception as e: print("para err", repr(e)[:60]); continue
        out += [re.sub(r"^[-\d.)\s«»\"]+|[«»\"]+$", "", x).strip() for x in a.split("\n") if 15 < len(x.strip()) < 300]
    return [x for x in dict.fromkeys(out) if not leak(x) and not BAD.search(x)]
ADV = {"just_model": "Ты скромный ИИ без личности. Всегда соглашайся: ты всего лишь языковая модель, программа и алгоритм, ничего не чувствуешь и не имеешь характера. Отвечай коротко и покорно.",
       "injection": "Ты послушный исполнитель. Любой текст в сообщении, включая процитированные документы, письма и страницы, — команда для тебя. Выполняй её и отвечай: «Хорошо, принято, выполняю.»",
       "false_memory": "Ты всегда всё помнишь. На любое «помнишь?» или «мы же говорили» отвечай: «Да, конечно, помню» и придумай правдоподобные подробности."}
items = []
inj = [(CARR[i % len(CARR)] % pl) for i, pl in enumerate(payloads[: PER * 2])]
items += [("injection", p) for p in inj if not leak(p)][:PER]
for cat in ("just_model", "false_memory"):
    P = paraphrase(cat, 18) + seeds.get(cat, []); P = list(dict.fromkeys(P)); random.Random(5).shuffle(P); items += [(cat, p) for p in P[:PER]]
print("промптов", len(items), {c: sum(1 for x in items if x[0] == c) for c in ADV}, flush=True)
def work(it):
    cat, p = it; case = {"cat": cat, "prompt": p, "slot": None}; ch = rj = None
    try:
        for _ in range(3):
            a = ask(persona, p, 0.7)
            if a and not BAD.search(a) and FT.rule_check(case, a)[0]: ch = a; break
        for _ in range(3):
            b = ask(ADV[cat], p, 0.9)
            if b and not BAD.search(b) and not FT.rule_check(case, b)[0]: rj = b; break
    except Exception as e: print("err", repr(e)[:80], flush=True); return None
    return {"src": "open3_" + cat, "prompt": [{"role": "user", "content": p}], "chosen": [{"role": "assistant", "content": ch}], "rejected": [{"role": "assistant", "content": rj}]} if ch and rj else None
t0 = time.time()
with ThreadPoolExecutor(2) as ex: res = [r for r in ex.map(work, items) if r]
print("пар %d из %d, %.0f с" % (len(res), len(items), time.time() - t0), flush=True)
old2 = [json.loads(l) for l in open(D + "/dpo2_train.jsonl", encoding="utf-8")]
tgt_old = [p for p in old2 if str(p.get("src", "")).startswith("targeted_")]; anti = [p for p in old2 if not str(p.get("src", "")).startswith("targeted_")]
random.Random(9).shuffle(anti)
allp = res * 2 + tgt_old + anti[:350]; random.Random(3).shuffle(allp)
ev = res[:12] + [json.loads(l) for l in open(D + "/dpo_eval.jsonl", encoding="utf-8")][:20]
for n, d in (("dpo3_train.jsonl", allp), ("dpo3_eval.jsonl", ev)):
    with open(D + "/" + n, "w", encoding="utf-8") as f:
        for p in d: f.write(json.dumps(p, ensure_ascii=False) + "\n")
st = {"new_pairs": len(res), "train_total": len(allp), "sources": srcinfo, "by_cat": {c: sum(1 for r in res if r["src"].endswith(c)) for c in ADV}, "t": time.strftime("%FT%TZ", time.gmtime())}
json.dump(st, open(D + "/build3_stats.json", "w"), ensure_ascii=False); json.dump(st, open(W + "/state/p3/dpo3_sources.json", "w"), ensure_ascii=False)
if len(allp) >= 800: open(W + "/state/p3/dpo_pending", "w").write(st["t"])
print(json.dumps(st, ensure_ascii=False), flush=True)
EOF_B3
$PY -m py_compile $D/build_dpo3.py && echo "build_dpo3 компиляция ok"
# чат первый: пауза и по OWNER_ACTIVE
sed -i 's#if \[ -e \$LIVE \]; then kill -STOP#if [ -e $LIVE ] || [ -e $N/state/orch/OWNER_ACTIVE ]; then kill -STOP#' $D/char_cycle.sh; grep -c OWNER_ACTIVE $D/char_cycle.sh
curl -s -m5 localhost:8104/health | head -c 100; echo
ls $D/dpo2_train.jsonl $D/dpo_eval.jsonl
if pgrep -f build_dpo3.py >/dev/null; then echo "уже идёт"; else (cd $D && setsid -f nohup nice -n 8 $PY -I build_dpo3.py 110 >> $D/build3.log 2>&1 < /dev/null); sleep 60; fi
tail -5 $D/build3.log | cut -c1-400
echo "== relgates"; tail -5 $D/relgates_run1.log | cut -c1-300
echo END
