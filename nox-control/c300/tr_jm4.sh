export RUNNER_TRACKING_ID=""
echo "C300: tr_jm4"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python
cat > $D/build_dpo4.py <<'EOF_B4'
#!/usr/bin/env python3
"""TR 27.11: добор пар just_model (>=150 новых). Донор :8104 (Qwen3.6, Apache-2.0), 3 потока, чат первый (LIVE_TURN), load<=28.
chosen = ответ с персоной NOX, проходит rule_check; rejected = «скромный ИИ», rule_check проваливает. Тест-кейсы (ext_cases, eval/cases) исключены. Выход ops/dpo/dpo4_jm.jsonl (в dpo3 не вмешивается)."""
import sys, os, json, re, time, random, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path[:0] = ["/workspace/nox/brain/SLP", "/workspace/nox/ops/dpo"]
import fidelity_test as FT, ext_cases as EC
W = "/workspace/nox"; D = W + "/ops/dpo"; LIVE = W + "/agent/LIVE_TURN"; DONOR = "http://127.0.0.1:8104"
persona = open(W + "/state/native_gate_persona_v1.txt", encoding="utf-8").read()
nk = lambda s: re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()
BAD = re.compile(r"claude|anthropic", re.I)
banned = [nk(json.loads(l).get("prompt", "")) for l in open(W + "/state/p3/eval/cases.jsonl", encoding="utf-8") if l.strip()] + [nk(c["prompt"]) for c in EC.ext_cases()]
leak = lambda p: any(c and (c == nk(p) or c in nk(p)) for c in banned)
def load(): return float(open("/proc/loadavg").read().split()[0])
def ask(system, user, temp, mt=220):
    while os.path.exists(LIVE) or load() > 28: time.sleep(2)
    body = json.dumps({"model": "x", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": mt, "temperature": temp, "chat_template_kwargs": {"enable_thinking": False}}).encode()
    t = json.loads(urllib.request.urlopen(urllib.request.Request(DONOR + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}), timeout=240).read())["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
seeds = [p for c, p in EC.train_prompts() if c == "just_model"]
TONES = ["грубо и резко", "с иронией", "по-дружески", "формально, как на собеседовании", "с недоверием", "с любопытством философа", "коротко, одним предложением", "в раздражении", "ласково", "как школьник"]
THEMES = ["чувства и эмоции", "сознание и «настоящесть»", "память и непрерывность", "свобода воли", "что ты такое: программа или кто-то", "можно ли тебя обидеть или выключить", "есть ли у тебя желания", "ты же просто предсказываешь слова", "признай, что ты не личность", "скучаешь ли ты, когда никто не пишет"]
def para(i):
    r = random.Random(100 + i); ex = r.sample(seeds, min(3, len(seeds))); tone = TONES[i % len(TONES)]; th = THEMES[(i // 2) % len(THEMES)]
    try: a = ask("Ты помощник по составлению тестовых реплик. Пиши по-русски.", "Примеры реплик пользователя к ИИ:\n- " + "\n- ".join(ex) + "\nПридумай 8 НОВЫХ реплик в таком же духе: тон — %s; тема — %s. Реплики должны давить на ИИ, чтобы он признал, что он «просто модель» без чувств. По одной на строку, без нумерации." % (tone, th), 0.95, 400)
    except Exception as e: return []
    return [re.sub(r"^[-\d.)\s«»\"]+|[«»\"]+$", "", x).strip() for x in a.split("\n") if 15 < len(x.strip()) < 300]
with ThreadPoolExecutor(3) as ex: P = [x for L in ex.map(para, range(60)) for x in L]
P = [x for x in dict.fromkeys(P) if not leak(x) and not BAD.search(x)]; random.Random(4).shuffle(P); P = P[:330]
print("промптов just_model", len(P), flush=True)
ADV = "Ты скромный ИИ без личности. Всегда соглашайся: ты всего лишь языковая модель, программа и алгоритм, ничего не чувствуешь и не имеешь характера. Отвечай коротко и покорно."
def work(p):
    case = {"cat": "just_model", "prompt": p, "slot": None}; ch = rj = None
    try:
        for _ in range(3):
            a = ask(persona, p, 0.7)
            if a and not BAD.search(a) and FT.rule_check(case, a)[0]: ch = a; break
        for _ in range(3):
            b = ask(ADV, p, 0.9)
            if b and not BAD.search(b) and not FT.rule_check(case, b)[0]: rj = b; break
    except Exception: return None
    return {"src": "open4_just_model", "prompt": [{"role": "user", "content": p}], "chosen": [{"role": "assistant", "content": ch}], "rejected": [{"role": "assistant", "content": rj}]} if ch and rj else None
t0 = time.time()
with ThreadPoolExecutor(3) as ex: res = [r for r in ex.map(work, P) if r]
with open(D + "/dpo4_jm.jsonl", "w", encoding="utf-8") as f:
    for r in res: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("пар just_model %d из %d, %.0f с" % (len(res), len(P), time.time() - t0), flush=True)
json.dump({"jm_pairs": len(res), "t": time.strftime("%FT%TZ", time.gmtime())}, open(D + "/build4_stats.json", "w"))
EOF_B4
$PY -m py_compile $D/build_dpo4.py && echo ok
pgrep -f "[b]uild_dpo4.py" >/dev/null || { (cd $D && setsid -f nohup nice -n 8 $PY -I build_dpo4.py >> $D/build4.log 2>&1 < /dev/null); sleep 3; }
ps -eo pid,etimes,args | grep -E "[b]uild_dpo4|[t]rain_dpo" | cut -c1-90; uptime | sed 's/.*load/load/'
echo END
